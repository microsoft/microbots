from enum import IntEnum, StrEnum
from pathlib import Path


class ModelProvider(StrEnum):
    """Supported LLM providers for MicroBot.

    Use these values as the provider prefix in the model string: ``<provider>/<model_name>``.
    """

    OPENAI = "azure-openai"
    """Azure OpenAI provider. Example: ``azure-openai/gpt-4o``"""
    OLLAMA_LOCAL = "ollama-local"
    """Local Ollama provider. Example: ``ollama-local/llama3``"""
    ANTHROPIC = "anthropic"
    """Anthropic Claude provider. Example: ``anthropic/claude-sonnet-4-20250514``"""


class ModelEnum(StrEnum):
    GPT_5 = "gpt-5"


class PermissionLabels(StrEnum):
    """Permission levels for mounted folders in the bot's sandbox environment."""

    READ_ONLY = "READ_ONLY"
    """Read-only access to the mounted folder."""
    READ_WRITE = "READ_WRITE"
    """Read and write access to the mounted folder."""


class PermissionMapping:
    MAPPING = {
        PermissionLabels.READ_ONLY: "ro",
        PermissionLabels.READ_WRITE: "rw",
    }


class FILE_PERMISSIONS(IntEnum):
    READ = 4
    WRITE = 2
    EXECUTE = 1


WORKING_DIR = str(Path.home() / "MICROBOTS_WORKDIR")
DOCKER_WORKING_DIR = "/workdir"
LOG_FILE_DIR = "/var/log"
TOOL_FILE_BASE_PATH = Path(__file__).parent / "tools" / "tool_definitions"
