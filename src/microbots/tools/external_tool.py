import logging
import os
import shutil
import subprocess
from pathlib import Path
from pydantic.dataclasses import dataclass, Field

from microbots.tools.tool import TOOLTYPE, ToolAbstract, EnvFileCopies
from microbots.environment.Environment import Environment

logger = logging.getLogger("  ExternalTool")


@dataclass
class ExternalTool(ToolAbstract):
    """
    An external tool that runs entirely on the **host** machine.

    - Environment variables are verified for presence on the host;
      a missing variable raises an error immediately.
    - Files listed in ``files_to_copy`` are copied to the *host*
      destination path (not into a Docker sandbox).
    - Install, verify, setup, and uninstall commands all execute
      on the host via ``subprocess``.
    """

    tool_type: TOOLTYPE = Field(init=False, default=TOOLTYPE.EXTERNAL)

    # --------------------------------------------------------------------- #
    # Private helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def _run_host_command(command: str) -> subprocess.CompletedProcess:
        """Run a shell command on the host and return the CompletedProcess."""
        logger.debug("Running host command for external tool: %s", command)
        # NOTE: using shell=True since commands may include shell features like
        # environment variable references, pipes, etc. We ensure that all
        # commands come from trusted YAML definitions, so this should be safe.
        # Verify commands in tool definitions are well-formed to avoid injection risks.
        output = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
        )
        logger.debug("Host command output %s", output)
        return output

    def _verify_env_variables(self):
        """Verify that every required environment variable exists on the host.

        Raises
        ------
        EnvironmentError
            If any variable listed in ``env_variables`` is not set.
        """
        missing = [
            var for var in (self.env_variables or []) if var not in os.environ
        ]
        if missing:
            msg = (
                f"Missing required environment variable(s) for tool "
                f"'{self.name}': {', '.join(missing)}"
            )
            logger.error(" %s", msg)
            raise EnvironmentError(msg)

        for var in self.env_variables or []:
            logger.info(" Environment variable %s is present on the host", var)
        logger.info(
            " Environment variable verification complete for tool: %s",
            self.name,
        )

    def _copy_files(self):
        """Copy tool files to the host destination paths."""

        def _copy_single_file(file_copy: EnvFileCopies):
            src = Path(file_copy.src)
            dest = Path(file_copy.dest)

            if not src.exists():
                logger.error(" Source file %s not found on host", src)
                raise ValueError(f"File to copy {src} not found on host")

            # Ensure parent directory exists on the host
            dest.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(str(src), str(dest))

            # Set permissions  single octal digit applied as owner+group, no others
            if not (0 <= file_copy.permissions <= 7):
                raise ValueError(
                    f"Invalid permissions {file_copy.permissions} for "
                    f"file copy {src}  {dest}"
                )
            octal_mode = (file_copy.permissions << 6) | (file_copy.permissions << 3)
            os.chmod(str(dest), octal_mode)

            logger.info(" Copied file on host: %s  %s", src, dest)

        for fc in self.files_to_copy or []:
            _copy_single_file(fc)
        logger.info(" Successfully copied all files for tool: %s", self.name)

    # --------------------------------------------------------------------- #
    # Public interface (ToolAbstract)
    # --------------------------------------------------------------------- #
    def install_tool(self, env: Environment):
        """Install the tool by running install commands on the **host**.
         Files listed in ``files_to_copy`` are also copied to the host."""
        logger.debug("Installing external tool on host: %s", self.name)
        for command in self.install_commands or []:
            result = self._run_host_command(command)
            if result.returncode != 0:
                logger.error(
                    " Host install command failed for tool %s: %s\n"
                    "stdout: %s\nstderr: %s",
                    self.name, command, result.stdout, result.stderr,
                )
                raise RuntimeError(
                    f"Failed to install external tool {self.name} with "
                    f"command '{command}'. stderr: {result.stderr}"
                )
        logger.info(" Successfully installed external tool: %s", self.name)
        self._copy_files()

    def verify_tool_installation(self, env: Environment):
        """Verify the tool by running verify commands on the **host**."""
        logger.debug("Verifying installation of external tool: %s", self.name)
        for command in self.verify_commands or []:
            result = self._run_host_command(command)
            if result.returncode != 0:
                logger.error(
                    " Host verify command failed for tool %s: %s\n"
                    "stdout: %s\nstderr: %s",
                    self.name, command, result.stdout, result.stderr,
                )
                raise RuntimeError(
                    f"Failed to verify external tool {self.name} with "
                    f"command '{command}'. stderr: {result.stderr}"
                )
        logger.info(" Successfully verified external tool: %s", self.name)

    def setup_tool(self, env: Environment):
        """Prepare the tool for use on the host.

        1. Verify all required env variables are present (error on missing).
        2. Run any setup commands on the host.
        """
        self._verify_env_variables()

        for command in self.setup_commands or []:
            result = self._run_host_command(command)
            if result.returncode != 0:
                logger.error(
                    " Host setup command failed for tool %s: %s\n"
                    "stdout: %s\nstderr: %s",
                    self.name, command, result.stdout, result.stderr,
                )
                raise RuntimeError(
                    f"Failed to setup external tool {self.name} with "
                    f"command '{command}'. stderr: {result.stderr}"
                )
        logger.info(" Successfully set up external tool: %s", self.name)

    def uninstall_tool(self, env: Environment):
        """Tear down the tool from the host.

        1. Remove copied files from host destination paths.
        2. Run uninstall commands on the host.
        """
        for fc in self.files_to_copy or []:
            dest = Path(fc.dest)
            if dest.exists():
                dest.unlink()
                logger.info(" Removed file from host: %s", dest)
            else:
                logger.warning(
                    "  File %s not found on host during uninstall of tool: %s",
                    dest, self.name,
                )

        for command in self.uninstall_commands or []:
            result = self._run_host_command(command)
            if result.returncode != 0:
                logger.error(
                    " Host uninstall command failed for tool %s: %s\n"
                    "stdout: %s\nstderr: %s",
                    self.name, command, result.stdout, result.stderr,
                )
                raise RuntimeError(
                    f"Failed to uninstall external tool {self.name} with "
                    f"command '{command}'. stderr: {result.stderr}"
                )
        logger.info(" Successfully uninstalled external tool: %s", self.name)
