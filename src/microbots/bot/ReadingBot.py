import os
from typing import Optional

from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.MicroBot import BotType, MicroBot, system_prompt_common
from microbots.tools.tool import ToolAbstract
from microbots.extras.mount import Mount


class ReadingBot(MicroBot):

    def __init__(
        self,
        model: str,
        folder_to_mount: str,
        environment: Optional[any] = None,
        additional_tools: Optional[list[ToolAbstract]] = None,
        token_provider: Optional[any] = None,
    ):
        # validate init values before assigning
        bot_type = BotType.READING_BOT

        base_name = os.path.basename(folder_to_mount)
        folder_mount_info = Mount(
            folder_to_mount, f"/{DOCKER_WORKING_DIR}/{base_name}", PermissionLabels.READ_ONLY
        )

        system_prompt = f"""
        {system_prompt_common}
        You are a reading bot.
        You are only provided access to read files inside the mounted directory.
        The directory is mounted at {folder_mount_info.sandbox_path} in your current environment.
        You can access files using paths like {folder_mount_info.sandbox_path}/filename.txt or by changing to that directory first.
        Once you have identified the issue or reproduced the problem, set task_done=true and provide your findings in the result field.
        Do not explore unrelated files. Focus only on files directly related to the task.
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
