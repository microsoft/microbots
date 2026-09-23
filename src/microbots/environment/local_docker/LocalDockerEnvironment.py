import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional

import docker
import requests

from microbots.environment.Environment import CmdReturn, Environment
from microbots.constants import DOCKER_WORKING_DIR, WORKING_DIR, PermissionLabels
from microbots.extras.mount import Mount

logger = logging.getLogger(__name__)


class LocalDockerEnvironment(Environment):
    def __init__(
        self,
        port: int,
        folder_to_mount: Optional[Mount] = None,
        image: str = "kavyasree261002/shell_server:latest",
    ):

        self.image = image
        self.folder_to_mount = folder_to_mount
        self.overlay_mount = False
        self.container = None
        self.client = docker.from_env()
        self.port = port  # required host port
        self.container_port = 8080
        self.deleted = False
        self.working_dir = None
        self._create_working_dir()
        self.start()

    def __del__(self):
        if hasattr(self, 'deleted') and not self.deleted:
            self.stop()

    def _create_working_dir(self, retries=3, delay=2):
        working_dir = WORKING_DIR + "_" + os.urandom(4).hex()
        if not os.path.exists(working_dir):
            os.makedirs(working_dir)
            self.working_dir = working_dir
            logger.info("🗂️  Created working directory at %s", self.working_dir)
        else:
            logger.info("🗂️  Working directory already exists at %s. Retrying with a new path...", working_dir)
            if retries > 0:
                time.sleep(delay)
                self._create_working_dir(retries - 1, delay * 2)
            else:
                raise Exception(f"Failed to create a unique working directory after multiple attempts. Try cleaning up old working directories from {WORKING_DIR}.")

    def start(self):
        mode_map = {"READ_ONLY": "ro", "READ_WRITE": "rw"}
        volumes_config = {self.working_dir: {"bind": DOCKER_WORKING_DIR, "mode": "rw"}}
        if self.folder_to_mount:
            if self.folder_to_mount.permission == PermissionLabels.READ_ONLY:
                volumes_config[self.folder_to_mount.host_path_info.abs_path] = {
                    "bind": f"/ro/{os.path.basename(self.folder_to_mount.sandbox_path)}",
                    "mode": mode_map[self.folder_to_mount.permission],
                }
                logger.info(
                    "📦 Volume mapping: %s → /ro/%s",
                    self.folder_to_mount.host_path_info.abs_path,
                    os.path.basename(self.folder_to_mount.sandbox_path),
                )
            else:
                volumes_config[self.folder_to_mount.host_path_info.abs_path] = {
                    "bind": self.folder_to_mount.sandbox_path,
                    "mode": mode_map[self.folder_to_mount.permission],
                }
                logger.debug(
                    "📦 Volume mapping: %s → %s",
                    self.folder_to_mount.host_path_info.abs_path,
                    self.folder_to_mount.sandbox_path,
                )

        # Bind to loopback only: the shell server has no authentication, so it
        # must never be reachable from the network.
        port_mapping = {f"{self.container_port}/tcp": ("127.0.0.1", self.port)}

        self.container = self.client.containers.run(
            self.image,
            volumes=volumes_config,
            ports=port_mapping,
            detach=True,
            working_dir="/app",
            # SYS_ADMIN is the narrowest grant that allows the overlayfs mount;
            # the docker-default AppArmor profile denies mount regardless of caps.
            cap_add=["SYS_ADMIN"],
            security_opt=["no-new-privileges:true", "apparmor=unconfined"],
            environment={
                "BOT_PORT": str(self.container_port),
                "BOT_WORKDIR": DOCKER_WORKING_DIR,
                **self._host_identity(),
            },
        )
        logger.info(
            "🚀 Started container %s with image %s on host port %s",
            self.container.id[:12],
            self.image,
            self.port,
        )
        time.sleep(2)  # Give some time for the server to start

        if self.folder_to_mount and self.folder_to_mount.permission == PermissionLabels.READ_ONLY:
            self._setup_overlay_mount()

        if self.folder_to_mount:
            self.execute(f"cd {self.folder_to_mount.sandbox_path}")
        else:
            self.execute("cd /")

    @staticmethod
    def _host_identity() -> dict:
        """Run the bot's shell under the host uid so anything it writes to the
        bind-mounted working directory stays removable by the host user."""
        if not hasattr(os, "getuid") or os.getuid() == 0:
            return {}
        return {"AGENT_UID": str(os.getuid()), "AGENT_GID": str(os.getgid())}

    @property
    def _overlay_dir(self) -> str:
        path_name = os.path.basename(self.folder_to_mount.sandbox_path)
        return f"{DOCKER_WORKING_DIR}/overlay/{path_name}"

    def _setup_overlay_mount(self):
        """Stack a writable layer over the READ_ONLY mount so the bot can edit
        without the host's tree ever changing.

        Runs on the root control channel: the bot's own shell holds no
        capabilities and cannot mount or unmount anything.
        """
        # NOTE: Don't use this for any other read-only mounts except the main code folder.
        path_name = os.path.basename(self.folder_to_mount.sandbox_path)
        sandbox_path = shlex.quote(self.folder_to_mount.sandbox_path)
        overlay = shlex.quote(self._overlay_dir)

        ret: CmdReturn = self.execute_privileged(
            f"mkdir -p {sandbox_path} {overlay}/upper {overlay}/work && "
            f"mount -t overlay overlay "
            f"-o lowerdir=/ro/{path_name}/,upperdir={overlay}/upper/,workdir={overlay}/work/ "
            f"{sandbox_path}"
        )
        if ret.return_code != 0:
            raise RuntimeError(
                f"Failed to set up overlay mount for {path_name}: {ret.stderr}"
            )
        self.overlay_mount = True

        # The merged root inherits the lower directory's owner, which may not be
        # the bot, leaving it unable to create files at the top level.
        identity = self._host_identity()
        if identity:
            self.execute_privileged(
                f"chown {identity['AGENT_UID']}:{identity['AGENT_GID']} {sandbox_path}"
            )

        logger.info(
            "🔒 Set up overlay mount for read-only directory at %s",
            self.folder_to_mount.sandbox_path,
        )

    def _teardown_overlay_mount(self):
        """Unmount and remove the overlay before the container goes away.

        The kernel creates ``work/`` root-owned and mode 0700, so the host user
        cannot clean it up afterwards - it has to go through the root channel.
        """
        sandbox_path = shlex.quote(self.folder_to_mount.sandbox_path)
        overlay = shlex.quote(self._overlay_dir)
        try:
            ret: CmdReturn = self.execute_privileged(f"umount -l {sandbox_path}")
            if ret.return_code != 0:
                logger.error("❌  Failed to unmount overlay: %s", ret.stderr)
            else:
                logger.info("✅  Unmounted overlay at %s", self.folder_to_mount.sandbox_path)

            ret = self.execute_privileged(f"rm -rf {sandbox_path} {overlay}")
            if ret.return_code != 0:
                logger.error("❌  Failed to remove overlay directories: %s", ret.stderr)
            else:
                logger.info("🗑️  Removed overlay directories for %s", self._overlay_dir)
        except Exception as e:
            logger.error("❌  Failed to teardown overlay mount: %s", e)
        finally:
            self.overlay_mount = False

    def get_ipv4_address(self) -> str:
        """Return the container's IPv4 address on the Docker bridge network."""
        if not self.container:
            raise RuntimeError("No active container to get IP address from")

        self.container.reload()
        networks = self.container.attrs["NetworkSettings"]["Networks"]
        container_ip = next(iter(networks.values()))["IPAddress"]
        if not container_ip:
            raise RuntimeError("Could not determine container IP address")
        return container_ip

    def stop(self):
        """Stop and remove the container"""
        if self.container:
            if self.overlay_mount:
                self._teardown_overlay_mount()

            self.container.stop()
            self.container.remove()
            self.container = None

        # Remove working directory
        if os.path.exists(self.working_dir):
            try:
                import shutil

                shutil.rmtree(self.working_dir)
                logger.info("🗑️  Removed working directory at %s", self.working_dir)
            except Exception as e:
                logger.error("❌  Failed to remove working directory: %s", e)

        self.deleted = True

    # Unused function. Keeping for reference or future use
    def _escape(self, command: str) -> str:
        # Escape double quotes and special characters for JSON safety
        command = command.replace('"', '\\"')
        command = command.replace("<", "&lt;").replace(">", "&gt;")
        return command

    def execute_privileged(
        self, command: str, timeout: Optional[int] = 300, sensitive: bool = False
    ) -> CmdReturn:
        """Run a command as root over the docker exec control plane.

        Reserved for setup the bot itself must not perform (package installs,
        writes outside the working directory). Unlike execute(), this path is
        not reachable from the container's published port.

        ``timeout`` is accepted for signature parity but not enforced: the
        docker exec API has no timeout, so a wedged command blocks here.
        """
        if not self.container:
            raise RuntimeError("No active container to execute a privileged command in")

        logger.debug("➡️  Executing privileged command: %s", "<redacted>" if sensitive else command)
        exit_code, (stdout, stderr) = self.container.exec_run(
            ["bash", "-lc", command], user="root", demux=True
        )
        return CmdReturn(
            stdout=stdout.decode(errors="replace") if stdout else "",
            stderr=stderr.decode(errors="replace") if stderr else "",
            return_code=exit_code if exit_code is not None else 0,
        )

    def execute(
        self, command: str, timeout: Optional[int] = 300, sensitive: bool = False
    ) -> CmdReturn:  # TODO: Need proper return value
        logger.debug("➡️  Executing command in container: %s", "<redacted>" if sensitive else command)
        # command = self._escape(command)
        start_time = time.perf_counter()
        # command = self._escape(command)
        try:
            response = requests.post(
                f"http://localhost:{self.port}/",
                json={"message": command},
                timeout=timeout,
            )

            elapsed = time.perf_counter() - start_time
            logger.debug(
                "Command completed in %.2fs",
                elapsed,
            )

            output = response.json().get("output", "")
            logger.debug("⬅️  Return Code: %d,\nStdout:\n%s\nStderr:\n%s",
                         output.get("return_code", 0),
                         output.get("stdout", ""),
                         output.get("stderr", ""))

            response.raise_for_status()

            return CmdReturn(
                stdout=output.get("stdout", ""),
                stderr=output.get("stderr", ""),
                return_code=output.get("return_code", 0)
            )
        except requests.exceptions.ConnectTimeout:
            elapsed = time.perf_counter() - start_time
            msg = f"Connection timeout after {elapsed:.1f}s (port {self.port})"
            logger.error("❌ %s", msg)
            return CmdReturn(stdout="", stderr=msg, return_code=124)

        except requests.exceptions.ReadTimeout:
            elapsed = time.perf_counter() - start_time
            msg = f"Read timeout after {elapsed:.1f}s while waiting for command output"
            logger.error("❌ %s", msg)

            # Attempt to recover the shell by sending a simple command
            self._attempt_shell_recovery()

            return CmdReturn(stdout="", stderr=msg, return_code=124)

        except requests.exceptions.RequestException as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(
                "❌ Request failed after %.2fs while executing command: %s",
                elapsed,
                e,
            )
            return CmdReturn(stdout="", stderr=str(e), return_code=1)
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(
                "❌ Unexpected error after %.2fs while executing command: %s",
                elapsed,
                e,
            )
            return CmdReturn(stdout="", stderr="Unexpected error", return_code=1)

    def _attempt_shell_recovery(self):
        """
        Attempt to recover the shell after a timeout by sending a simple echo command.
        This helps clear any stuck state in the shell communicator.
        """
        try:
            logger.info("🛠️  Attempting to recover shell after timeout...")
            # Send a simple command to trigger shell-level recovery
            # Shell recovery needs ~2s (SIGINT + queue clear + marker check), so allow 5s total
            response = requests.post(
                f"http://localhost:{self.port}/",
                json={"message": "echo '__RECOVERY__'"},
                timeout=5,
            )
            if response.status_code == 200:
                output = response.json().get("output", {})
                logger.info("✅ Shell recovery successful (exit code: %d)", output.get("return_code", 0))
            else:
                logger.warning("⚠️  Shell recovery returned status %d", response.status_code)
        except requests.exceptions.Timeout:
            logger.warning("⚠️  Shell recovery timed out - shell may still be unresponsive")
        except Exception as e:
            logger.error("❌ Shell recovery failed: %s", e)

    def copy_to_container(self, src_path: str, dest_path: str) -> bool:
        """
        Copy a file or folder from the host machine to the Docker container.

        Args:
            src_path: Path to the source file/folder on the host machine
            dest_path: Destination path inside the container

        Returns:
            bool: True if copy was successful, False otherwise
        """
        if not self.container:
            logger.error("❌ No active container to copy to")
            return False

        try:
            # Check if source path exists
            if not os.path.exists(src_path):
                logger.error("❌ Source path does not exist: %s", src_path)
                return False
            # Ensure destination directory exists inside container
            dest_dir = os.path.dirname(dest_path)
            if dest_dir and dest_dir != '/':
                # Check if directory exists inside the container first
                check_cmd = f"test -d {shlex.quote(dest_dir)}"
                check_result = self.execute(check_cmd)

                if check_result.return_code != 0:
                    logger.debug("📁 Creating destination directory inside container: %s", dest_dir)
                    mkdir_cmd = f"mkdir -p {shlex.quote(dest_dir)}"
                    mkdir_result = self.execute(mkdir_cmd)

                    if mkdir_result.return_code != 0:
                        logger.error("❌ Failed to create destination directory %s: %s",
                                   dest_dir, mkdir_result.stderr)
                        return False
                    else:
                        logger.debug("✅ Destination directory created: %s", dest_dir)
                else:
                    logger.debug("✅ Destination directory already exists: %s", dest_dir)

            # Use docker cp command to copy files/folders
            # Escape paths for shell safety

            # Build docker cp command
            cmd = ["docker", "cp", src_path, f"{self.container.id}:{dest_path}"]

            logger.debug("📁 Copying %s to container:%s", src_path, dest_path)

            # Execute the copy command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info("✅ Successfully copied %s to container:%s", src_path, dest_path)
                return True
            else:
                logger.error("❌ Failed to copy file. Error: %s", result.stderr)
                return False

        except subprocess.TimeoutExpired:
            logger.error("❌ Copy operation timed out after 300 seconds")
            return False
        except Exception as e:
            logger.exception("❌ Unexpected error during copy operation: %s", e)
            return False

    def copy_from_container(self, src_path: str, dest_path: str) -> bool:
        """
        Copy a file or folder from the Docker container to the host machine.

        Args:
            src_path: Path to the source file/folder inside the container
            dest_path: Destination path on the host machine

        Returns:
            bool: True if copy was successful, False otherwise
        """
        if not self.container:
            logger.error("❌ No active container to copy from")
            return False

        try:
            # Check if source path exists inside the container
            check_cmd = f"test -e {shlex.quote(src_path)}"
            check_result = self.execute(check_cmd)

            if check_result.return_code != 0:
                logger.error("❌ Source path does not exist in container: %s", src_path)
                return False

            # Check if destination directory exists on host machine
            dest_dir = os.path.dirname(dest_path)
            if not os.path.exists(dest_dir):
                logger.error("❌ Destination directory does not exist on host: %s", dest_dir)
                return False

            cmd = ["docker", "cp", f"{self.container.id}:{src_path}", dest_path]

            # Build docker cp command

            logger.debug("📁 Copying container:%s to %s", src_path, dest_path)

            # Execute the copy command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info("✅ Successfully copied from container:%s to %s", src_path, dest_path)
                return True
            else:
                logger.error("❌ Failed to copy file. Error: %s", result.stderr)
                return False

        except subprocess.TimeoutExpired:
            logger.error("❌ Copy operation timed out after 300 seconds")
            return False
        except Exception as e:
            logger.exception("❌ Unexpected error during copy operation: %s", e)
            return False
