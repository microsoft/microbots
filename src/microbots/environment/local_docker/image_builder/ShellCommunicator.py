#!/usr/bin/env python3
"""
Shell Communication Script
A Python script to create and communicate with shell sessions.
Supports interactive shell communication, command execution, and bidirectional data flow.
"""

import os
import queue
import signal
import subprocess
import sys
import threading
import time
import logging
from typing import Callable, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='/var/log/ShellCommunicator.log')

@dataclass
class CmdReturn:
    stdout: str
    stderr: str
    return_code: int


class ShellCommunicator:
    """
    A class to create and manage shell sessions with bidirectional communication.
    """

    def __init__(self, shell_type: str = "bash", encoding: str = "utf-8"):
        """
        Initialize the shell communicator.

        Args:
            shell_type: Type of shell (only "bash" is supported)
            encoding: Text encoding for communication
        """
        self.shell_type = shell_type.lower()
        if self.shell_type != "bash":
            raise ValueError(f"Unsupported shell type: {shell_type}. Only 'bash' is supported.")
        self.encoding = encoding
        self.process: Optional[subprocess.Popen] = None
        self.output_queue = queue.Queue()
        self.error_queue = queue.Queue()
        self.is_running = False
        self.output_thread: Optional[threading.Thread] = None
        self.error_thread: Optional[threading.Thread] = None
        self.output_callback: Optional[Callable] = None

        # Define shell commands - only supporting bash
        self.shell_commands = {
            "bash": ["bash"],
        }

    def start_session(self) -> bool:
        """
        Start a new shell session.

        Returns:
            bool: True if session started successfully, False otherwise
        """
        try:
            if self.shell_type not in self.shell_commands:
                logger.error(" Unsupported shell type: %s", self.shell_type)
                return False

            cmd = self.shell_commands[self.shell_type]

            # Create the subprocess
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=self.encoding,
                bufsize=0,
                universal_newlines=True,
            )

            self.is_running = True

            # Start output monitoring threads
            self.output_thread = threading.Thread(
                target=self._monitor_output,
                args=(self.process.stdout, self.output_queue, "OUTPUT"),
                daemon=True,
            )
            self.error_thread = threading.Thread(
                target=self._monitor_output,
                args=(self.process.stderr, self.error_queue, "ERROR"),
                daemon=True,
            )

            self.output_thread.start()
            self.error_thread.start()

            logger.info(" %s session started successfully", self.shell_type.capitalize())
            logger.debug(" Process ID: %s", self.process.pid)
            return True

        except Exception as e:
            logger.exception(" Failed to start shell session: %s", e)
            return False

    def _monitor_output(self, stream, output_queue: queue.Queue, stream_type: str):
        """
        Monitor shell output in a separate thread.

        Args:
            stream: The stream to monitor (stdout or stderr)
            output_queue: Queue to store output
            stream_type: Type of stream ("OUTPUT" or "ERROR")
        """
        try:
            while self.is_running and self.process and self.process.poll() is None:
                line = stream.readline()
                if line:
                    output_queue.put((stream_type, line.rstrip()))
                    if self.output_callback:
                        self.output_callback(stream_type, line.rstrip())
                elif self.process.poll() is not None:
                    break
        except Exception as e:
            output_queue.put((stream_type, f"Monitor error: {e}"))

    # Unused function. Keeping for reference and future use
    def _re_escape(self, command: str) -> str:
        # Reverse .replace('"', '\\"')
        command = command.replace('\"', '"')
        command = command.replace("&lt;", "<").replace("&gt;", ">")
        return command

    # Unused function. Keeping for reference and future use
    def _is_heredoc_command(self, command: str) -> bool:
        """Check if command contains heredoc syntax."""
        import re
        # Look for heredoc patterns like <<EOF, <<'END', <<"DELIMITER", etc.
        return bool(re.search(r'<<\s*[\'"]?[A-Za-z_][A-Za-z0-9_]*[\'"]?', command))

    def send_command(
        self, command: str, wait_for_output: bool = True, timeout: float = 300
    ) -> CmdReturn:
        """
        Send a command to the shell session.

        Args:
            command: Command to execute
            wait_for_output: Whether to wait for command output
            timeout: Timeout for waiting for output

        Returns:
            CmdReturn object with stdout, stderr, and return code
        """
        if not self.is_running or not self.process:
            logger.warning(" No active shell session")
            return CmdReturn(stdout="", stderr="No active shell session", return_code=1)

        try:
            # command = self._re_escape(command)

            if not wait_for_output:
                # Send the command without marker for async execution
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
                logger.debug(" Sent async command: %s", command)
                return CmdReturn(stdout="ASYNC: Not waiting for completion", stderr="", return_code=0)

            # Generate a unique command completion marker
            marker = f"__COMMAND_COMPLETE_{int(time.time() * 1000000)}__"

            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
            # Send exit code capture on a new line after user command completes
            self.process.stdin.write(f"echo '{marker}' $?\n")
            self.process.stdin.flush()

            logger.debug(" Sent command: %s", command)
            logger.debug(" Waiting for marker: %s", marker)

            # Collect output until marker is found or timeout
            output_lines = []
            error_lines = []
            start_time = time.time()
            marker_found = False
            last_exit_code = 0

            while time.time() - start_time < timeout and not marker_found:
                try:
                    # Check for output with a small timeout
                    stream_type, line = self.output_queue.get(timeout=0.1)
                    logger.debug(" Received line from %s: %s", stream_type, line)

                    # Check if this is our completion marker
                    if marker in line:
                        marker_found = True
                        # For bash, the exit code is on the same line after the marker
                        try:
                            # Extract exit code from the same line as the marker
                            # Format: "__COMMAND_COMPLETE_xxxxx__ exit_code"
                            parts = line.split()
                            if len(parts) >= 2:
                                exit_code_str = parts[-1].strip()
                                # Handle bash exit codes (0-255 only)
                                if exit_code_str.isdigit():
                                    last_exit_code = int(exit_code_str)
                                else:
                                    last_exit_code = 1
                            else:
                                last_exit_code = 1
                        except (ValueError, AttributeError, IndexError):
                            # Default to 1 if parsing fails
                            last_exit_code = 1
                        logger.debug(" Found marker with exit code: %s", last_exit_code)
                        continue

                    # Add output to appropriate list
                    if stream_type == "ERROR":
                        error_lines.append(line)
                        logger.debug(" %s", line)
                    else:
                        output_lines.append(line)
                        logger.debug(" %s", line)

                except queue.Empty:
                    # No output available, continue waiting
                    continue
                except Exception as e:
                    logger.exception(" Unexpected error while reading output: %s", e)
                    break

            # Check for any remaining error output
            while not self.error_queue.empty():
                try:
                    stream_type, line = self.error_queue.get_nowait()
                    error_lines.append(line)
                    logger.debug(" %s", line)
                except queue.Empty:
                    break

            final_return_code = last_exit_code if marker_found else (1 if error_lines else 0)

            # Handle timeout case
            if not marker_found:
                logger.warning(" Command timed out after %s seconds", timeout)
                error_lines.append(f"Command timed out after {timeout} seconds")
                final_return_code = 124  # Standard timeout exit code

                # Attempt to recover the shell by sending Ctrl+C to interrupt the running command
                try:
                    logger.info(" Attempting to interrupt timed-out command...")
                    # Send SIGINT to the shell process to interrupt the running command
                    if self.process and self.process.poll() is None:
                        self.process.send_signal(subprocess.signal.SIGINT)
                        time.sleep(0.5)  # Give it time to handle the interrupt

                        # Clear any pending output from the interrupted command
                        self._clear_output_queues()

                        # Send a recovery marker to ensure shell is responsive
                        recovery_marker = f"__RECOVERY_{int(time.time() * 1000000)}__"
                        self.process.stdin.write(f"echo '{recovery_marker}'\n")
                        self.process.stdin.flush()

                        # Wait briefly for recovery marker
                        recovery_timeout = time.time() + 2
                        recovered = False
                        while time.time() < recovery_timeout:
                            try:
                                stream_type, line = self.output_queue.get(timeout=0.1)
                                if recovery_marker in line:
                                    recovered = True
                                    logger.info(" Shell recovered after timeout")
                                    break
                            except queue.Empty:
                                continue

                        if not recovered:
                            logger.warning(" Shell may still be unresponsive after recovery attempt")

                except Exception as e:
                    logger.error(" Failed to recover shell after timeout: %s", e)

            return CmdReturn(
                stdout="\n".join(output_lines) if output_lines else "",
                stderr="\n".join(error_lines) if error_lines else "",
                return_code=final_return_code
            )

        except Exception as e:
            logger.exception(" Failed to send command: %s", e)
            return CmdReturn(stdout="", stderr=str(e), return_code=1)

    def _clear_output_queues(self):
        """
        Clear all pending output from the output and error queues.
        This is useful after a timeout to remove stale data.
        """
        cleared_count = 0
        try:
            while not self.output_queue.empty():
                self.output_queue.get_nowait()
                cleared_count += 1
        except queue.Empty:
            pass

        try:
            while not self.error_queue.empty():
                self.error_queue.get_nowait()
                cleared_count += 1
        except queue.Empty:
            pass

        if cleared_count > 0:
            logger.debug(" Cleared %d stale messages from output queues", cleared_count)

    def is_alive(self) -> bool:
        """
        Check if the shell session is still alive.

        Returns:
            bool: True if session is active, False otherwise
        """
        return (
            self.is_running and self.process is not None and self.process.poll() is None
        )

    def get_shell_info(self) -> dict:
        """
        Get information about the current shell session.

        Returns:
            Dictionary with shell session information
        """
        if not self.process:
            return {"status": "Not started"}

        return {
            "shell_type": self.shell_type,
            "pid": self.process.pid,
            "status": "Running" if self.is_alive() else "Stopped",
            "encoding": self.encoding,
            "return_code": self.process.returncode,
        }

    def close_session(self):
        """
        Close the shell session and cleanup resources.
        """
        logger.info(" Closing shell session")

        self.is_running = False

        if self.process:
            try:
                # Try to terminate gracefully with bash exit command
                self.send_command("exit", wait_for_output=False)

                # Wait a bit for graceful shutdown
                time.sleep(1)

                # Force terminate if still running
                if self.process.poll() is None:
                    self.process.terminate()
                    time.sleep(1)

                    if self.process.poll() is None:
                        self.process.kill()

                logger.info(" Shell session closed")

            except Exception as e:
                logger.exception(" Error during cleanup: %s", e)

        # Wait for threads to finish
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=2)
        if self.error_thread and self.error_thread.is_alive():
            self.error_thread.join(timeout=2)
