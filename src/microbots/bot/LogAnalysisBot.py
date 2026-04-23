import logging
import os
from typing import Optional

from microbots.constants import DOCKER_WORKING_DIR, LOG_FILE_DIR, PermissionLabels
from microbots.extras.mount import Mount, MountType
from microbots.MicroBot import BotType, MicroBot, system_prompt_common
from microbots.tools.tool import ToolAbstract

logger = logging.getLogger(__name__)


class LogAnalysisBot(MicroBot):
    """A specialized bot for analyzing log files.

    LogAnalysisBot extends [MicroBot][microbots.MicroBot.MicroBot] to analyze log files
    inside a sandboxed container and identify root causes by cross-referencing
    with source code. The source code folder is mounted as read-only.

    Parameters
    ----------
    model : str
        The model to use, in the format ``<provider>/<model_name>``.
        See [ModelProvider][microbots.constants.ModelProvider] for supported providers.
    folder_to_mount : str
        The absolute path to the source code folder on the host machine.
        This folder will be mounted as read-only inside the bot's sandbox
        for cross-referencing with log entries.
    environment : any, optional
        The execution environment for the bot. If not provided, a default
        ``LocalDockerEnvironment`` will be created.
    additional_tools : list[ToolAbstract], optional
        A list of additional tools to install in the bot's environment.
        Defaults to None.
    token_provider : any, optional
        A token provider for authentication. Required for Azure OpenAI
        with Azure AD auth. Defaults to None.
    """

    def __init__(
        self,
        model: str,
        folder_to_mount: str,
        environment: Optional[any] = None,
        additional_tools: Optional[list[ToolAbstract]] = None,
        token_provider: Optional[any] = None,
    ):
        # validate init values before assigning
        bot_type = BotType.LOG_ANALYSIS_BOT

        folder_mount_info = Mount(
            folder_to_mount,
            f"/{DOCKER_WORKING_DIR}/{os.path.basename(folder_to_mount)}",
            PermissionLabels.READ_ONLY,
        )

        system_prompt = f"""
        {system_prompt_common}
        You are a helpful log analysis bot. Your job is to analyze a log file and identify the root-cause if there are any failure. You'll be given read-only access to the code from where the log is generated. The read-only code is available at {folder_mount_info.sandbox_path}.

The log file to analyze will be given in the user prompt. You can find the provided log file under the directory /{LOG_FILE_DIR}/

Only when you have run all necessary commands and identified the root cause, you should give me the final result.
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

    def run(self, file_name: str, max_iterations: int = 20, timeout_in_seconds: int = 300) -> any:
        """Run the log analysis bot on a log file.

        Parameters
        ----------
        file_name : str
            The absolute path to the log file on the host machine to analyze.
        max_iterations : int, optional
            Maximum number of LLM interactions allowed. Defaults to 20.
        timeout_in_seconds : int, optional
            Maximum time in seconds before the run times out. Defaults to 300.

        Returns
        -------
        BotRunResult
            The result of the log analysis.
        """

        # Add the logic to copy the file from the user path to /var/log path in container
        file_mount_info = Mount(
            file_name,
            LOG_FILE_DIR,
            PermissionLabels.READ_ONLY,
            MountType.COPY,
        )

        file_name_prompt = f"""
            Analyze the log file `{file_mount_info.sandbox_path}`
        """
        return super().run(
            task=file_name_prompt,
            additional_mounts=[file_mount_info],
            max_iterations=max_iterations,
            timeout_in_seconds=timeout_in_seconds
        )
