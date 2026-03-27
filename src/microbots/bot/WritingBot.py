import os
from typing import Optional

from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.MicroBot import BotType, MicroBot, system_prompt_common
from microbots.tools.tool import ToolAbstract
from microbots.extras.mount import Mount


class WritingBot(MicroBot):

    def __init__(
        self,
        model: str,
        folder_to_mount: str,
        environment: Optional[any] = None,
        additional_tools: Optional[list[ToolAbstract]] = None,
        token_provider: Optional[any] = None,
    ):
        # validate init values before assigning
        bot_type = BotType.WRITING_BOT

        folder_mount_info = Mount(
            folder_to_mount, f"/{DOCKER_WORKING_DIR}/{os.path.basename(folder_to_mount)}", PermissionLabels.READ_WRITE
        )

        system_prompt = f"""
        {system_prompt_common}
        You are a writing bot.
        You are only provided access to write files inside the mounted directory.
        The directory is mounted at  {folder_mount_info.sandbox_path} in your current environment.
        You can access files using paths like {folder_mount_info.sandbox_path}/filename.txt or by changing to that directory first.
        Once all the commands are done, and task is verified finally give me the result.

        COMMAND USAGE RESTRICTIONS:
        - Use ONLY standard Linux commands: `git`, `sed`, `awk`, `grep`, `patch`, `find`, `cat`, `head`, `tail`, `ls`, `cp`, `mv`, `rm`, `mkdir`, `touch`, `diff` etc.
        - DO NOT use non-existent commands like `applypatch`, `edit`, `modify` - use `git apply` or `patch` instead
        - For file editing, use `sed`, `awk`, or direct file operations with standard tools
        - When using `grep` with special characters, escape them properly
        - Break complex operations into smaller, verifiable steps
        """

        super().__init__(
            model=model,
            bot_type=bot_type,
            system_prompt=system_prompt,
            environment=environment,
            additional_tools=additional_tools or [],
            folder_to_mount=folder_mount_info,
            token_provider=token_provider,
        )
