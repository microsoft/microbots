"""
Integration tests for LocalDockerEnvironment
"""
import pytest
import os
import socket
import re
import logging
import time
import requests
from unittest.mock import patch, Mock, MagicMock, call

# Add src to path for imports
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from microbots.environment.local_docker.LocalDockerEnvironment import LocalDockerEnvironment
from microbots.environment.local_docker.images import DEBIAN_IMAGE, DEFAULT_IMAGE
from microbots.environment.Environment import CmdReturn
from microbots.extras.mount import Mount
from microbots.constants import DOCKER_WORKING_DIR, WORKING_DIR

logger = logging.getLogger(__name__)

class TestLocalDockerEnvironmentIntegration:
    """Integration tests for LocalDockerEnvironment with real Docker containers"""

    @pytest.fixture(scope="class")
    def available_port(self):
        """Find an available port for testing - class scoped to reuse same port"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    @pytest.fixture(scope="class")
    def shared_env(self, available_port):
        """Create a single LocalDockerEnvironment instance for all tests in this class"""
        env = None
        try:
            env = LocalDockerEnvironment(port=available_port)

            # Wait for container to be ready
            time.sleep(2)

            # Verify it's working
            result = env.execute("echo 'Environment ready'")
            assert result.return_code == 0

            yield env
        finally:
            if env:
                env.stop()

    @pytest.mark.integration
    @pytest.mark.docker
    def test_basic_environment_lifecycle(self, shared_env):
        """Test basic environment functionality using shared environment"""
        # Test that container is running
        assert shared_env.container is not None
        shared_env.container.reload()
        assert shared_env.container.status == 'running'

        # Test that we can connect and execute commands
        result = shared_env.execute("echo 'Hello World'")
        assert result.return_code == 0
        assert "Hello World" in result.stdout


    @pytest.mark.integration
    @pytest.mark.docker
    def test_command_execution_basic(self, shared_env):
        """Test basic command execution functionality using shared environment"""
        # Test simple echo
        result = shared_env.execute("echo 'test message'")
        assert result.return_code == 0
        assert "test message" in result.stdout
        assert result.stderr == ""

        # Test command with error
        result = shared_env.execute("nonexistent_command")
        assert result.return_code != 0
        assert result.stderr != ""

        # Test pwd
        result = shared_env.execute("pwd")
        assert result.return_code == 0
        assert "/" in result.stdout

    @pytest.mark.integration
    @pytest.mark.docker
    def test_command_execution_complex(self, shared_env):
        """Test that heredoc commands are automatically converted to safe alternatives"""
        # Test the specific heredoc command that was causing timeouts
        heredoc_command = """cat > /tmp/test_heredoc.py << EOF
#!/usr/bin/env python3
import sys

def missing_colon_error():
    # This function demonstrates a syntax error - missing colon after if statement
    if True
        print("This will cause a syntax error")
        return True

    return False

if __name__ == "__main__":
    try:
        result = missing_colon_error()
        print(f"Function result: {result}")
    except SyntaxError as e:
        print(f"Syntax error caught: {e}")
        sys.exit(1)
EOF"""

        logger.info("Testing heredoc command execution...")
        start_time = time.time()

        # Execute the heredoc command
        result = shared_env.execute(heredoc_command, timeout=60)
        end_time = time.time()
        execution_time = end_time - start_time

        logger.info(f"Heredoc command completed in {execution_time:.2f} seconds")
        logger.info(f"Return code: {result.return_code}")
        logger.info(f"Stdout: {result.stdout}")
        logger.info(f"Stderr: {result.stderr}")

        # The command should complete successfully (converted automatically)
        assert result.return_code == 0, f"Heredoc command failed with return code {result.return_code}"

        # Should complete in reasonable time (less than 30 seconds)
        assert execution_time < 30, f"Heredoc command took too long: {execution_time:.2f} seconds"

        # Verify the file was created correctly
        verify_result = shared_env.execute("cat /tmp/test_heredoc.py")
        assert verify_result.return_code == 0
        assert "missing_colon_error" in verify_result.stdout
        assert re.search(r"if True$", verify_result.stdout, re.MULTILINE) is not None  # Check for "if True" at end of line (missing colon)
        logger.info(f"Verify result: {verify_result}")

        # Test that the Python file has the expected syntax error
        python_result = shared_env.execute("python3 /tmp/test_heredoc.py")
        # Should fail due to syntax error (missing colon)
        assert python_result.return_code != 0
        assert "SyntaxError" in python_result.stderr or "invalid syntax" in python_result.stderr

        logger.info("Heredoc command with automatic conversion test passed successfully")

    @pytest.mark.integration
    @pytest.mark.docker
    @pytest.mark.slow
    def test_read_write_mount(self, test_repo):
        """Test READ_WRITE mount functionality - creates own env because mounting requires initialization-time config"""
        # Get a fresh port for this test since shared_env is using the class-scoped port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            mount_port = s.getsockname()[1]

        env = None
        test_repo_mount = Mount(
            host_path=str(test_repo),
            sandbox_path=f"{DOCKER_WORKING_DIR}/{test_repo.name}",
            permission="READ_WRITE"
        )
        try:
            env = LocalDockerEnvironment(
                port=mount_port,
                folder_to_mount=test_repo_mount,
            )

            mount_path = f"{DOCKER_WORKING_DIR}/{test_repo.name}"

            # Test that mounted directory is accessible
            result = env.execute(f"ls {mount_path}")
            assert result.return_code == 0
            assert "tests" in result.stdout

            # Test reading subdirectory
            result = env.execute(f"ls {mount_path}/tests")
            assert result.return_code == 0
            assert "missing_colon.py" in result.stdout

            # Test writing to the mounted directory (should succeed with READ_WRITE)
            result = env.execute(f"echo 'new content from container' > {mount_path}/new_test_file.txt")
            assert result.return_code == 0

            # Verify the file was created on the host
            new_file_path = test_repo / "new_test_file.txt"
            assert new_file_path.exists()
            with open(new_file_path, 'r') as f:
                content = f.read().strip()
                assert "new content from container" in content

            # Clean up the created file
            new_file_path.unlink()

        finally:
            if env:
                env.stop()

    @pytest.mark.integration
    @pytest.mark.docker
    @pytest.mark.slow
    def test_read_only_mount(self, test_repo):
        """Test READ_ONLY mount with overlay functionality - creates own env because mounting requires initialization-time config"""
        # Get a fresh port for this test since shared_env is using the class-scoped port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            mount_port = s.getsockname()[1]

        env = None
        test_repo_mount = Mount(
            host_path=str(test_repo),
            sandbox_path=f"{DOCKER_WORKING_DIR}/{test_repo.name}",
            permission="READ_ONLY"
        )

        try:
            env = LocalDockerEnvironment(
                port=mount_port,
                folder_to_mount=test_repo_mount,
            )

            mount_path = f"{DOCKER_WORKING_DIR}/{test_repo.name}"

            # Test that mounted directory is accessible
            result = env.execute(f"ls {mount_path}")
            assert result.return_code == 0
            assert "tests" in result.stdout

            # Test reading subdirectory
            result = env.execute(f"ls {mount_path}/tests")
            assert result.return_code == 0
            assert "missing_colon.py" in result.stdout

            # Test writing to the mounted directory (should appear to succeed with overlay)
            result = env.execute(f"echo 'overlay content' > {mount_path}/overlay_file.txt")
            assert result.return_code == 0

            # Verify the file appears to exist in container
            result = env.execute(f"cat {mount_path}/overlay_file.txt")
            assert result.return_code == 0
            assert "overlay content" in result.stdout

            # Verify the file was NOT created on the host (read-only mount)
            overlay_file_path = test_repo / "overlay_file.txt"
            assert not overlay_file_path.exists()

            # Test modifying existing file (should work in overlay)
            result = env.execute(f"echo 'overlay modification' >> {mount_path}/tests/missing_colon.py")
            assert result.return_code == 0

            # Verify original file on host is unchanged
            with open(test_repo / "tests" / "missing_colon.py", 'r') as f:
                content = f.read()
                assert "overlay modification" not in content

        finally:
            if env:
                env.stop()

    @pytest.mark.integration
    @pytest.mark.docker
    def test_copy_to_container(self, shared_env, test_repo):
        """Test copying files from host to container using shared environment"""
        # Test copying a single file
        source_file = test_repo / "tests" / "missing_colon.py"
        dest_dir = "/tmp/"

        success = shared_env.copy_to_container(str(source_file), dest_dir)
        assert success is True

        # Verify file exists and has correct content in container
        result = shared_env.execute(f"cat {dest_dir}missing_colon.py")
        assert result.return_code == 0
        assert "division" in result.stdout

        # Test copying non-existent file
        success = shared_env.copy_to_container("/nonexistent/file.txt", "/tmp/fail.txt")
        assert success is False

    @pytest.mark.integration
    @pytest.mark.docker
    def test_copy_from_container(self, shared_env):
        """Test copying files from container to host using shared environment"""
        # Create a file in container
        container_file = "/tmp/container_created.txt"
        result = shared_env.execute(f"echo 'Created in container' > {container_file}")
        assert result.return_code == 0

        # Copy file from container to host directory
        host_dest_dir = "/tmp/"
        success = shared_env.copy_from_container(container_file, host_dest_dir)
        assert success is True

        # The file should be copied to /tmp/container_created.txt
        copied_file_path = "/tmp/container_created.txt"

        # Verify file exists on host with correct content
        assert os.path.exists(copied_file_path)
        with open(copied_file_path, 'r') as f:
            content = f.read()
            assert "Created in container" in content

        # Clean up the created file
        os.remove(copied_file_path)

        # Test copying non-existent file
        success = shared_env.copy_from_container("/nonexistent/file.txt", "/tmp/fail.txt")
        assert success is False

    @pytest.mark.integration
    @pytest.mark.docker
    def test_command_timeout(self, shared_env):
        """Test that commands timeout correctly and return appropriate error code"""
        # Execute a command that should timeout
        start_time = time.time()
        result = shared_env.execute("sleep 10", timeout=2)
        elapsed = time.time() - start_time

        # Should timeout and return exit code 124
        assert result.return_code == 124, f"Expected timeout exit code 124, got {result.return_code}"

        # Should contain timeout message in stderr
        assert "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower(), \
            f"Expected timeout message in stderr, got: {result.stderr}"

        # Should timeout quickly - around 2s for command + 5s for recovery attempt
        assert elapsed < 10, f"Command should timeout in ~2-7s (including recovery), took {elapsed:.1f}s"

    @pytest.mark.integration
    @pytest.mark.docker
    def test_shell_recovery_after_timeout(self, shared_env):
        """Test that shell remains responsive after a command timeout"""

        # First, execute a command that will timeout
        logger.info("1. Executing command that will timeout...")
        result = shared_env.execute("sleep 10", timeout=2)
        assert result.return_code == 124, "Command should timeout with exit code 124"
        logger.info("   ✓ Command timed out as expected")

        # Give recovery mechanism more time to work (shell recovery + HTTP recovery)
        time.sleep(3)

        # Now try to execute a normal command - shell should be responsive
        logger.info("2. Testing if shell is still responsive after timeout...")
        result = shared_env.execute("echo 'Shell is responsive'", timeout=10)

        assert result.return_code == 0, \
            f"Shell should be responsive after timeout. Got return code {result.return_code}, stderr: {result.stderr}"
        assert "Shell is responsive" in result.stdout, \
            f"Output should contain expected text. Got: {result.stdout}"
        logger.info("   ✓ Shell recovered successfully")

        # Execute multiple commands to ensure stability
        logger.info("3. Testing multiple commands after recovery...")
        for i in range(3):
            result = shared_env.execute(f"echo 'Command {i+1}'", timeout=5)
            assert result.return_code == 0, f"Command {i+1} should succeed after recovery"
            assert f"Command {i+1}" in result.stdout, f"Command {i+1} output should be correct"
            logger.info(f"   ✓ Command {i+1} successful")

    @pytest.mark.integration
    @pytest.mark.docker
    def test_multiple_timeouts(self, shared_env):
        """Test that shell can handle multiple consecutive timeouts"""
        for i in range(3):
            logger.info(f"Timeout test {i+1}/3...")

            # Execute a command that will timeout
            result = shared_env.execute("sleep 5", timeout=1)
            assert result.return_code == 124, f"Timeout {i+1} should return exit code 124"

            # Wait a moment for recovery
            time.sleep(0.5)

            # Verify shell is still responsive
            result = shared_env.execute(f"echo 'After timeout {i+1}'", timeout=5)
            assert result.return_code == 0, f"Shell should be responsive after timeout {i+1}"
            assert f"After timeout {i+1}" in result.stdout, f"Output {i+1} should be correct"
            logger.info(f"   ✓ Recovery {i+1} successful")


@pytest.mark.unit
class TestCreateWorkingDir:
    """Unit tests for LocalDockerEnvironment._create_working_dir else branch"""

    def _make_env(self):
        """Create a bare LocalDockerEnvironment without calling __init__"""
        env = LocalDockerEnvironment.__new__(LocalDockerEnvironment)
        env.deleted = True  # Prevent __del__ from calling stop()
        env.working_dir = None
        return env

    @patch("microbots.environment.local_docker.LocalDockerEnvironment.time.sleep")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.makedirs")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.path.exists")
    def test_retries_when_directory_already_exists(self, mock_exists, mock_makedirs, mock_sleep):
        """Test that _create_working_dir retries with a new path when the directory already exists"""
        # First call: directory exists; second call: directory does not exist
        mock_exists.side_effect = [True, False]

        env = self._make_env()
        env._create_working_dir(retries=3, delay=2)

        # Should have slept once with the initial delay
        mock_sleep.assert_called_once_with(2)
        # makedirs called once on the successful retry
        assert mock_makedirs.call_count == 1
        assert env.working_dir is not None

    @patch("microbots.environment.local_docker.LocalDockerEnvironment.time.sleep")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.makedirs")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.path.exists")
    def test_raises_exception_after_all_retries_exhausted(self, mock_exists, mock_makedirs, mock_sleep):
        """Test that _create_working_dir raises Exception when retries are exhausted"""
        # Directory always exists
        mock_exists.return_value = True

        env = self._make_env()
        with pytest.raises(Exception, match="Failed to create a unique working directory"):
            env._create_working_dir(retries=0, delay=2)

        # Should never create or sleep since retries=0
        mock_makedirs.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("microbots.environment.local_docker.LocalDockerEnvironment.time.sleep")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.makedirs")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.path.exists")
    def test_exponential_backoff_on_retries(self, mock_exists, mock_makedirs, mock_sleep):
        """Test that delay doubles on each retry (exponential backoff)"""
        # Exists 3 times, then succeeds on 4th
        mock_exists.side_effect = [True, True, True, False]

        env = self._make_env()
        env._create_working_dir(retries=3, delay=1)

        # Sleep calls should show exponential backoff: 1, 2, 4
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)
        assert mock_makedirs.call_count == 1

    @patch("microbots.environment.local_docker.LocalDockerEnvironment.time.sleep")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.makedirs")
    @patch("microbots.environment.local_docker.LocalDockerEnvironment.os.path.exists")
    def test_logs_info_when_directory_already_exists(self, mock_exists, mock_makedirs, mock_sleep, caplog):
        """Test that info is logged when directory already exists"""
        mock_exists.side_effect = [True, False]

        env = self._make_env()
        with caplog.at_level(logging.INFO):
            env._create_working_dir(retries=3, delay=2)

        assert any("already exists" in record.message for record in caplog.records)

    def test_execute_logs_command_when_not_sensitive(self, caplog):
        """execute() logs the actual command when sensitive=False (default)."""
        env = self._make_env()
        env.port = 9999

        mock_response = Mock()
        mock_response.json.return_value = {"output": {"return_code": 0, "stdout": "", "stderr": ""}}
        mock_response.raise_for_status = Mock()

        with patch("microbots.environment.local_docker.LocalDockerEnvironment.requests.post",
                   return_value=mock_response), \
             caplog.at_level(logging.DEBUG):
            env.execute("echo secret")

        assert "echo secret" in caplog.text
        assert "<redacted>" not in caplog.text

    def test_execute_redacts_command_when_sensitive(self, caplog):
        """execute() logs <redacted> instead of the command when sensitive=True."""
        env = self._make_env()
        env.port = 9999

        mock_response = Mock()
        mock_response.json.return_value = {"output": {"return_code": 0, "stdout": "", "stderr": ""}}
        mock_response.raise_for_status = Mock()

        with patch("microbots.environment.local_docker.LocalDockerEnvironment.requests.post",
                   return_value=mock_response), \
             caplog.at_level(logging.DEBUG):
            env.execute("export SECRET_TOKEN=abc123", sensitive=True)

        assert "<redacted>" in caplog.text
        assert "SECRET_TOKEN" not in caplog.text
        assert "abc123" not in caplog.text


@pytest.mark.unit
class TestGetIpv4Address:
    """Unit tests for LocalDockerEnvironment.get_ipv4_address"""

    def _make_env(self):
        """Create a bare LocalDockerEnvironment without calling __init__"""
        env = LocalDockerEnvironment.__new__(LocalDockerEnvironment)
        env.deleted = True
        env.container = None
        return env

    def test_returns_ip_address_from_container_networks(self):
        """get_ipv4_address returns the IP from the first Docker network"""
        env = self._make_env()
        env.container = Mock()
        env.container.attrs = {
            "NetworkSettings": {
                "Networks": {
                    "bridge": {"IPAddress": "172.17.0.2"}
                }
            }
        }

        result = env.get_ipv4_address()

        env.container.reload.assert_called_once()
        assert result == "172.17.0.2"

    def test_raises_runtime_error_when_no_container(self):
        """get_ipv4_address raises RuntimeError when container is None"""
        env = self._make_env()

        with pytest.raises(RuntimeError, match="No active container"):
            env.get_ipv4_address()

    def test_raises_runtime_error_when_ip_is_empty(self):
        """get_ipv4_address raises RuntimeError when IP address is empty"""
        env = self._make_env()
        env.container = Mock()
        env.container.attrs = {
            "NetworkSettings": {
                "Networks": {
                    "bridge": {"IPAddress": ""}
                }
            }
        }

        with pytest.raises(RuntimeError, match="Could not determine container IP address"):
            env.get_ipv4_address()


@pytest.mark.unit
class TestPrivilegedControlChannel:
    """Unit tests for privileged setup isolated from the bot's shell."""

    @pytest.fixture
    def env(self):
        env = LocalDockerEnvironment.__new__(LocalDockerEnvironment)
        env.deleted = True
        env.container = Mock()
        env.execute = Mock()
        env.overlay_mount = False
        env.folder_to_mount = Mock(sandbox_path=f"{DOCKER_WORKING_DIR}/repo")
        return env

    @pytest.mark.parametrize(
        "uid, expected",
        [
            (None, {}),
            (0, {}),
            (2001, {"AGENT_UID": "2001", "AGENT_GID": "2002"}),
        ],
    )
    def test_host_identity(self, monkeypatch, uid, expected):
        if uid is None:
            monkeypatch.delattr(os, "getuid")
        else:
            monkeypatch.setattr(os, "getuid", lambda: uid)
        monkeypatch.setattr(os, "getgid", Mock(return_value=2002))

        assert LocalDockerEnvironment._host_identity() == expected
        if not expected:
            os.getgid.assert_not_called()

    def test_start_restricts_container_privileges_and_published_port(self, env):
        env.image = "test_image"
        env.sudo_access = False
        env.working_dir = "/tmp/test_workdir"
        env.folder_to_mount = None
        env.port = 12345
        env.container_port = 8080
        env.client = Mock()
        env.client.containers.run.return_value.id = "test_container"
        calls = []

        with patch.object(env, "_prepare_shell_server", side_effect=lambda: calls.append("prepare")), \
             patch.object(env, "_launch_shell_server", side_effect=lambda: calls.append("launch")):
            env.start()

        env.client.containers.run.assert_called_once_with(
            "test_image",
            entrypoint=["sleep", "infinity"],
            init=True,
            volumes={"/tmp/test_workdir": {"bind": DOCKER_WORKING_DIR, "mode": "rw"}},
            ports={"8080/tcp": ("127.0.0.1", 12345)},
            detach=True,
            cap_add=["SYS_ADMIN"],
            security_opt=["no-new-privileges:true", "apparmor=unconfined"],
        )
        assert env.container is env.client.containers.run.return_value
        assert calls == ["prepare", "launch"]
        env.execute.assert_called_once_with("cd /")

    @pytest.mark.parametrize("failing", ["_prepare_shell_server", "_launch_shell_server"])
    def test_start_stops_container_when_shell_server_setup_fails(self, env, failing):
        env.image = "test_image"
        env.sudo_access = False
        env.working_dir = "/tmp/test_workdir"
        env.folder_to_mount = None
        env.port = 12345
        env.container_port = 8080
        env.client = Mock()
        env.client.containers.run.return_value.id = "test_container"
        env.stop = Mock()

        with patch.object(env, "_prepare_shell_server"), patch.object(env, "_launch_shell_server"), \
             patch.object(env, failing, side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                env.start()

        env.stop.assert_called_once_with()
        env.execute.assert_not_called()

    @pytest.mark.parametrize(
        "exit_code, stdout, stderr, expected",
        [
            (0, b"output", b"", CmdReturn("output", "", 0)),
            (7, b"out\xff", b"err\xff", CmdReturn("out\ufffd", "err\ufffd", 7)),
            (None, None, None, CmdReturn("", "", 0)),
        ],
    )
    def test_execute_privileged_uses_root_docker_exec(self, env, exit_code, stdout, stderr, expected):
        env.container.exec_run.return_value = (exit_code, (stdout, stderr))

        result = env.execute_privileged("echo test", timeout=15)

        env.container.exec_run.assert_called_once_with(
            ["bash", "-lc", "echo test"], user="root", demux=True
        )
        env.execute.assert_not_called()
        assert result == expected

    def test_execute_privileged_requires_container(self, env):
        env.container = None

        with pytest.raises(RuntimeError, match="No active container"):
            env.execute_privileged("echo test")

        env.execute.assert_not_called()

    @pytest.mark.parametrize("sensitive", [False, True])
    def test_execute_privileged_logging(self, env, caplog, sensitive):
        env.container.exec_run.return_value = (0, (None, None))

        with caplog.at_level(logging.DEBUG):
            env.execute_privileged("echo private-value", sensitive=sensitive)

        assert ("echo private-value" in caplog.text) is not sensitive
        assert ("<redacted>" in caplog.text) is sensitive
        env.container.exec_run.assert_called_once_with(
            ["bash", "-lc", "echo private-value"], user="root", demux=True
        )

    @pytest.mark.parametrize("identity", [{}, {"AGENT_UID": "2001", "AGENT_GID": "2002"}])
    def test_setup_overlay_uses_privileged_channel(self, env, identity):
        env.execute_privileged = Mock(return_value=CmdReturn("", "", 0))
        sandbox = env.folder_to_mount.sandbox_path
        overlay = f"{DOCKER_WORKING_DIR}/overlay/repo"

        with patch.object(env, "_host_identity", return_value=identity):
            env._setup_overlay_mount()

        expected_calls = [
            call(
                f"mkdir -p {sandbox} {overlay}/upper {overlay}/work && "
                f"mount -t overlay overlay "
                f"-o lowerdir=/ro/repo/,upperdir={overlay}/upper/,workdir={overlay}/work/ "
                f"{sandbox}"
            )
        ]
        if identity:
            expected_calls.append(call(f"chown 2001:2002 {sandbox}"))
        assert env.execute_privileged.call_args_list == expected_calls
        assert env.overlay_mount is True
        env.execute.assert_not_called()

    def test_setup_overlay_failure_does_not_mark_mounted(self, env):
        env.execute_privileged = Mock(return_value=CmdReturn("", "mount denied", 1))

        with pytest.raises(RuntimeError, match="Failed to set up overlay mount for repo: mount denied"):
            env._setup_overlay_mount()

        env.execute_privileged.assert_called_once()
        assert env.overlay_mount is False
        env.execute.assert_not_called()

    @pytest.mark.parametrize("unmount_code, remove_code", [(0, 0), (1, 0), (0, 1)])
    def test_teardown_overlay_cleans_up_and_resets_state(self, env, caplog, unmount_code, remove_code):
        env.overlay_mount = True
        env.execute_privileged = Mock(side_effect=[
            CmdReturn("", "unmount denied" if unmount_code else "", unmount_code),
            CmdReturn("", "remove denied" if remove_code else "", remove_code),
        ])

        with caplog.at_level(logging.INFO):
            env._teardown_overlay_mount()

        assert env.execute_privileged.call_args_list == [
            call(f"umount -l {DOCKER_WORKING_DIR}/repo"),
            call(f"rm -rf {DOCKER_WORKING_DIR}/repo {DOCKER_WORKING_DIR}/overlay/repo"),
        ]
        assert ("Failed to unmount overlay: unmount denied" in caplog.text) == bool(unmount_code)
        assert ("Failed to remove overlay directories: remove denied" in caplog.text) == bool(remove_code)
        assert env.overlay_mount is False
        env.execute.assert_not_called()

    def test_teardown_overlay_exception_resets_state(self, env, caplog):
        env.overlay_mount = True
        env.execute_privileged = Mock(side_effect=RuntimeError("container unavailable"))

        with caplog.at_level(logging.ERROR):
            env._teardown_overlay_mount()

        assert "Failed to teardown overlay mount: container unavailable" in caplog.text
        assert env.overlay_mount is False
        env.execute.assert_not_called()


@pytest.mark.unit
class TestImageSelection:
    """The caller picks the image; it defaults to the Debian shell-server image."""

    @pytest.fixture
    def make_env(self):
        def _make(**kwargs):
            with patch.object(LocalDockerEnvironment, "_create_working_dir"), \
                 patch.object(LocalDockerEnvironment, "start"), \
                 patch("microbots.environment.local_docker.LocalDockerEnvironment.docker"):
                env = LocalDockerEnvironment(port=1234, **kwargs)
            env.deleted = True
            return env
        return _make

    def test_defaults_to_debian_image(self, make_env):
        assert DEFAULT_IMAGE == DEBIAN_IMAGE == "mcr.microsoft.com/devcontainers/python:3.11"
        assert make_env().image == DEFAULT_IMAGE

    def test_explicit_image_is_used(self, make_env):
        assert make_env(image="custom/shell:dev").image == "custom/shell:dev"


@pytest.mark.unit
class TestShellServerPreparation:
    """The stock image is prepared and the shell server started over the root control plane."""

    @pytest.fixture
    def env(self):
        env = LocalDockerEnvironment.__new__(LocalDockerEnvironment)
        env.deleted = True
        env.image = "mcr.example/stock:1"
        env.sudo_access = False
        env.port = 12345
        env.container_port = 8080
        env.container = Mock()
        env.container.put_archive.return_value = True
        env.execute_privileged = Mock(return_value=CmdReturn("ok", "", 0))
        return env

    def test_archive_contains_root_owned_shell_server(self):
        import io
        import tarfile
        from microbots.environment.local_docker.LocalDockerEnvironment import _shell_server_archive

        with tarfile.open(fileobj=io.BytesIO(_shell_server_archive())) as tar:
            members = {m.name: m for m in tar.getmembers()}
        assert set(members) == {
            "shell_server",
            "shell_server/dockerShell.py",
            "shell_server/ShellCommunicator.py",
            "shell_server/prepare.sh",
        }
        assert all(m.uid == 0 and m.gid == 0 for m in members.values())
        assert members["shell_server"].mode == 0o755
        assert members["shell_server/prepare.sh"].mode == 0o755
        assert members["shell_server/dockerShell.py"].mode == 0o644

    @pytest.mark.parametrize("identity, sudo_access, prefix", [
        ({}, False, ""),
        ({"AGENT_UID": "2001", "AGENT_GID": "2002"}, False, "AGENT_UID=2001 AGENT_GID=2002 "),
        ({}, True, "AGENT_SUDO=1 "),
        ({"AGENT_UID": "2001", "AGENT_GID": "2002"}, True, "AGENT_UID=2001 AGENT_GID=2002 AGENT_SUDO=1 "),
    ])
    def test_prepare_copies_server_and_runs_prepare_script_as_root(self, env, identity, sudo_access, prefix):
        env.sudo_access = sudo_access
        with patch.object(env, "_host_identity", return_value=identity):
            env._prepare_shell_server()

        env.container.put_archive.assert_called_once()
        assert env.container.put_archive.call_args.args[0] == "/opt/microbots"
        assert env.execute_privileged.call_args_list == [
            call("mkdir -p /opt/microbots"),
            call(f"{prefix}sh /opt/microbots/shell_server/prepare.sh"),
        ]

    def test_prepare_failure_reports_script_output(self, env):
        env.execute_privileged.side_effect = [CmdReturn("", "", 0), CmdReturn("out", "no package manager", 1)]
        with patch.object(env, "_host_identity", return_value={}):
            with pytest.raises(RuntimeError, match="Failed to prepare image 'mcr.example/stock:1'(.|\n)*no package manager"):
                env._prepare_shell_server()

    def test_prepare_fails_when_copy_fails(self, env):
        env.container.put_archive.return_value = False
        with patch.object(env, "_host_identity", return_value={}):
            with pytest.raises(RuntimeError, match="Failed to copy the shell server"):
                env._prepare_shell_server()

    def test_launch_starts_server_as_root_and_waits_until_it_answers(self, env):
        identity = {"AGENT_UID": "2001", "AGENT_GID": "2002"}
        with patch.object(env, "_host_identity", return_value=identity), \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.requests.get",
                   side_effect=[requests.exceptions.ConnectionError(), Mock(status_code=405)]) as get, \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.time.sleep"):
            env._launch_shell_server()

        args, kwargs = env.container.exec_run.call_args
        assert args[0][:2] == ["sh", "-c"]
        assert "exec /opt/microbots/venv/bin/python dockerShell.py" in args[0][2]
        assert kwargs == {
            "user": "root",
            "detach": True,
            "environment": {"BOT_PORT": "8080", "BOT_WORKDIR": DOCKER_WORKING_DIR, **identity},
        }
        assert get.call_count == 2
        get.assert_called_with("http://localhost:12345/", timeout=2)

    def test_launch_times_out_with_server_log(self, env):
        env.execute_privileged.return_value = CmdReturn("Traceback: boom", "", 0)
        clock = iter([0, 0, 200])
        with patch.object(env, "_host_identity", return_value={}), \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.requests.get",
                   side_effect=requests.exceptions.ConnectionError()), \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.time.sleep"), \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.time.monotonic", side_effect=lambda: next(clock)):
            with pytest.raises(RuntimeError, match="did not start within 120s(.|\n)*Traceback: boom"):
                env._launch_shell_server()


@pytest.mark.unit
class TestSudoAccess:
    """Unit tests for the opt-in passwordless sudo mode."""

    @pytest.fixture
    def env(self):
        env = LocalDockerEnvironment.__new__(LocalDockerEnvironment)
        env.deleted = True
        env.image = "test_image"
        env.sudo_access = True
        env.working_dir = "/tmp/test_workdir"
        env.folder_to_mount = None
        env.port = 12345
        env.container_port = 8080
        env.client = Mock()
        env.client.containers.run.return_value.id = "test_container"
        env.container = Mock()
        env.overlay_mount = False
        env.execute = Mock(return_value=CmdReturn("", "", 0))
        env.execute_privileged = Mock(return_value=CmdReturn("", "", 0))
        return env

    def test_start_allows_privilege_escalation_and_verifies_sudo(self, env):
        with patch.object(env, "_verify_sudo_access") as verify, \
             patch.object(env, "_prepare_shell_server"), \
             patch.object(env, "_launch_shell_server"):
            env.start()

        # sudo and setuid helpers need no-new-privileges off; everything else is unchanged.
        kwargs = env.client.containers.run.call_args.kwargs
        assert kwargs["security_opt"] == ["apparmor=unconfined"]
        assert kwargs["cap_add"] == ["SYS_ADMIN"]
        verify.assert_called_once_with()

    def test_start_without_sudo_keeps_no_new_privileges_and_skips_check(self, env):
        env.sudo_access = False
        with patch.object(env, "_verify_sudo_access") as verify, \
             patch.object(env, "_prepare_shell_server"), \
             patch.object(env, "_launch_shell_server"):
            env.start()

        assert env.client.containers.run.call_args.kwargs["security_opt"] == [
            "no-new-privileges:true", "apparmor=unconfined"
        ]
        verify.assert_not_called()

    def test_shell_server_never_gets_a_root_flag(self, env):
        # The shell always drops to the agent account; sudo is configured by prepare.sh.
        with patch.object(env, "_host_identity", return_value={}):
            assert env._shell_server_environment() == {"BOT_PORT": "8080", "BOT_WORKDIR": DOCKER_WORKING_DIR}

    def test_init_defaults_to_no_sudo(self):
        with patch.object(LocalDockerEnvironment, "_create_working_dir"), \
             patch.object(LocalDockerEnvironment, "start"), \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.docker"):
            env = LocalDockerEnvironment(port=1234)
            env.deleted = True
        assert env.sudo_access is False

    def test_init_warns_but_allows_read_only_mount(self, tmp_path, caplog):
        mount = Mount(str(tmp_path), f"{DOCKER_WORKING_DIR}/repo", "READ_ONLY")
        with patch.object(LocalDockerEnvironment, "_create_working_dir"), \
             patch.object(LocalDockerEnvironment, "start") as start, \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.docker"), \
             caplog.at_level(logging.WARNING):
            env = LocalDockerEnvironment(port=1234, folder_to_mount=mount, sudo_access=True)
            env.deleted = True
        start.assert_called_once_with()
        assert env.sudo_access is True
        assert caplog.text.count("sudo_access=True with a READ_ONLY mount") == 1
        assert str(tmp_path) in caplog.text

    @pytest.mark.parametrize("sudo_access, permission", [(False, "READ_ONLY"), (True, "READ_WRITE")])
    def test_init_no_read_only_warning_otherwise(self, tmp_path, caplog, sudo_access, permission):
        mount = Mount(str(tmp_path), f"{DOCKER_WORKING_DIR}/repo", permission)
        with patch.object(LocalDockerEnvironment, "_create_working_dir"), \
             patch.object(LocalDockerEnvironment, "start"), \
             patch("microbots.environment.local_docker.LocalDockerEnvironment.docker"), \
             caplog.at_level(logging.WARNING):
            env = LocalDockerEnvironment(port=1234, folder_to_mount=mount, sudo_access=sudo_access)
            env.deleted = True
        assert "READ_ONLY mount" not in caplog.text

    def test_verify_sudo_access_accepts_passwordless_sudo(self, env, caplog):
        with caplog.at_level(logging.WARNING):
            env._verify_sudo_access()

        env.execute.assert_called_once_with("sudo -n true")
        assert "Sudo access enabled" in caplog.text

    @pytest.mark.parametrize("result, shown", [
        (CmdReturn("", "sudo: a password is required", 1), "sudo: a password is required"),
        (CmdReturn("", "", 127), "unknown error"),
    ])
    def test_verify_sudo_access_stops_and_raises_when_sudo_fails(self, env, result, shown):
        env.execute.return_value = result
        env.stop = Mock()

        with pytest.raises(RuntimeError, match=f"cannot use sudo in image 'test_image': {shown}"):
            env._verify_sudo_access()

        env.stop.assert_called_once_with()

    def test_stop_does_not_change_file_ownership(self, env, tmp_path):
        env.working_dir = str(tmp_path / "missing")
        container = env.container

        env.stop()

        assert not any("chown" in str(c) for c in env.execute_privileged.call_args_list)
        container.stop.assert_called_once_with()
        container.remove.assert_called_once_with()
