from abc import ABC, abstractmethod
from typing import Optional, List
from pydantic.dataclasses import dataclass, Field
import logging
from enum import Enum
from pathlib import Path

from microbots.environment.Environment import Environment
from microbots.constants import TOOL_FILE_BASE_PATH

logger = logging.getLogger("  Tool")


class TOOLTYPE(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass
class EnvFileCopies:
    src: Path
    dest: Path
    permissions: int  # Use FILE_PERMISSION enum to set permissions

    def __post_init__(self):
        # Pydantic handles type coercion for src, dest, and permissions
        # We only need custom logic for relative path handling and range validation
        if not self.src.is_absolute():
            self.src = TOOL_FILE_BASE_PATH / self.src

        if not (0 <= self.permissions <= 7):
            raise ValueError(f"permissions must be an integer between 0 and 7 for file copy {self.src} to {self.dest}")


@dataclass
class ToolAbstract(ABC):
    """
    Abstract base class for all tools in the Microbots framework.

    Tool hierarchy:
        ToolAbstract (ABC)
         Tool (ToolAbstract)    Docker sandbox tools (install_commands, env_variables, etc.)
         ExternalTool (ToolAbstract)    LLM-native tools (get_tool_definition, execute)
                 AnthropicMemoryTool
    """
    # TODO: Handle different instructions based on the platform (linux flavours, windows, mac)
    # TODO: Add versioning to tools
    name: str
    description: str

    # This is the set of instructions that will be provided to the LLM on how to use this tool.
    # This string will be appended to the LLM's system prompt.
    # This instructions should be non-interactive
    usage_instructions_to_llm: str

    tool_type: TOOLTYPE

    # Files to be copied from the repo to the system / environment where the tool is being installed. This is useful for tools that require additional files to be installed.
    files_to_copy: Optional[List[EnvFileCopies]] = Field(default_factory=list)

    # This set of commands will be executed to install the tool.
    # Commands for internal tools will be executed inside the Docker sandbox environment,
    # while commands for external tools will be executed in the current environment (Host).
    # So, you should be careful about it as it is making changes to your system.
    # These commands will be executed in the order they are provided.
    install_commands: Optional[List[str]] = Field(default_factory=list)

    # Optional parameters for the tool
    parameters: Optional[dict] = Field(default_factory=dict)

    # Mention necessary environment variables for the tool.
    # For internal tools these env variables will be copied into the sandbox.
    # For external tools, only verification will be done for the presence of these variables.
    env_variables: Optional[List[str]] = Field(default_factory=list)

    # This set of commands will be executed to verify if the tool is installed correctly.
    # If any of these commands fail, the tool installation is considered to have failed.
    verify_commands: Optional[List[str]] = Field(default_factory=list)

    # This set of commands will be executed after the code is copied to the environment
    # and before the llm is invoked.
    # For internal tools, these commands will be executed inside the mounted folder.
    setup_commands: Optional[List[str]] = Field(default_factory=list)

    # This set of commands will be executed when the environment is being torn down.
    uninstall_commands: Optional[List[str]] = Field(default_factory=list)

    def is_invoked(self, command: str) -> bool:
        return False  # Default implementation, override in subclasses if needed

    def is_model_supported(self, model_name: str) -> bool:
        """
        Check if the tool supports the given model.

        Args:
            model_name: The name of the model to check.

        Returns:
            True if the model is supported, False otherwise.
        """
        return True  # Default implementation, override in subclasses

    @abstractmethod
    def install_tool(self, env: Environment):
        """
        Install the tool in the given environment.

        Args:
            env: The environment to install the tool in.
        """
        pass

    @abstractmethod
    def verify_tool_installation(self, env: Environment):
        """
        Verify if the tool is installed correctly in the given environment.

        Args:
            env: The environment to verify the tool installation in.
        """
        pass

    @abstractmethod
    def setup_tool(self, env: Environment):
        """
        Execute any setup commands for the tool in the given environment.
        This will be executed after the code is copied to the environment and before the llm is invoked.

        Args:
            env: The environment to execute the setup commands in.
        """
        pass

    @abstractmethod
    def uninstall_tool(self, env: Environment):
        """
        Execute any uninstall commands for the tool in the given environment.
        This will be executed when the environment is being torn down.

        Args:
            env: The environment to execute the uninstall commands in.
        """
        pass


def get_tool_from_call(command: str, tools: List[ToolAbstract]) -> Optional[ToolAbstract]:
    """
    Get the tool object corresponding to the given command.

    Args:
        command: The command to get the tool for.
        tools: The list of available tools.

    Returns:
        The tool object corresponding to the given command, or None if no matching tool is found.
    """
    for tool in tools:
        if tool.is_invoked(command):
            return tool
    return None