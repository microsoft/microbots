import shlex
from typing import Optional

from microbots.MicroBot import BotType, MicroBot, BotRunResult
from microbots.environment.Environment import Environment
from microbots.tools.tool import ToolAbstract
from microbots.tools.tool_yaml_parser import parse_tool_definition


BROWSER_USE_TOOL = parse_tool_definition("browser-use.yaml")


class BrowsingBot(MicroBot):
    """
    A bot that searches the web with the ``browser`` tool.

    Parameters
    ----------
    model : str
        The model to use, in the format ``<provider>/<model_name>``.
    environment : Optional[Environment]
        The execution environment for the bot. If not provided, a default
        environment is created. Defaults to None.
    additional_tools : Optional[list[ToolAbstract]]
        Extra tools to install alongside the browser tool. Defaults to None.
    token_provider : Optional[any]
        A callable that returns a bearer token for Azure AD authentication.
        Defaults to None.
    image : Optional[str]
        Shell-server image of the auto-created environment. The browser tool
        only supports Debian-based images (the default). Defaults to None.
    """

    def __init__(
        self,
        model: str,
        environment: Optional[Environment] = None,
        additional_tools: Optional[list[ToolAbstract]] = None,
        token_provider: Optional[any] = None,
        image: Optional[str] = None,
    ):
        # validate init values before assigning
        bot_type = BotType.BROWSING_BOT
        system_prompt = """
        You search the web to gather information about a topic.
        """

        super().__init__(
            bot_type=bot_type,
            model=model,
            system_prompt=system_prompt,
            environment=environment,
            additional_tools=(additional_tools or []) + [BROWSER_USE_TOOL],
            token_provider=token_provider,
            image=image,
        )

    def run(self, task, timeout_in_seconds=200) -> BotRunResult:
        for tool in self.additional_tools:
            tool.setup_tool(self.environment)

        # If an Azure AD token provider is configured, get a fresh token and inject it into the
        # container so that browser.py (running inside Docker) can use it for ChatAzureOpenAI.
        if self.token_provider is not None:
            token = self.token_provider()
            self.environment.execute(f'export AZURE_OPENAI_AD_TOKEN={shlex.quote(token)}', sensitive=True)

        # browser-use will run inside the docker. So, single command to env should be sufficient
        browser_output = self.environment.execute(f"browser {shlex.quote(task)}", timeout=timeout_in_seconds)
        if browser_output.return_code != 0:
            return BotRunResult(
                status=False,
                result=None,
                error=f"Failed to run browser command. Error: {browser_output.stderr}",
            )

        browser_stdout = browser_output.stdout
        final_result = browser_stdout.split("Final result:")[-1].strip() if "Final result:" in browser_stdout else browser_stdout.strip()

        return BotRunResult(
            status=browser_output.return_code == 0,
            result=final_result,
            error=browser_output.stderr if browser_output.return_code != 0 else None,
        )

