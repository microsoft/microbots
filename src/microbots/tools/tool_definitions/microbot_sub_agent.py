import argparse
import logging
import shlex

from pydantic.dataclasses import dataclass, Field

from microbots.tools.external_tool import ExternalTool
from microbots.MicroBot import system_prompt_common, MicroBot, BotRunResult
from microbots.environment.Environment import CmdReturn

logger = logging.getLogger(" 🤖 MicroBot-Sub")


class _NoExitArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises ``ValueError`` instead of calling ``sys.exit``."""

    def error(self, message: str) -> None:  # type: ignore[override]  # base returns NoReturn (sys.exit); we raise instead
        raise ValueError(message)


INSTRUCTIONS_TO_LLM = """
Invoke this tool to create a sub-agent that can perform specific tasks as directed by the parent MicroBot. The sub-agent will run in the same sandbox environment and can communicate with the parent MicroBot via standard input/output. Use this tool when you want to delegate a specific task to a sub-agent while maintaining control and oversight over its actions.

Example Usage:
```
    microbot_sub --task "Analyze the contents of the /data directory and report any files larger than 100MB." --iterations 25 --timeout 300
```
In this example, the parent MicroBot would invoke the `microbot_sub` tool to create a sub-agent tasked with analyzing the contents of the `/data` directory and reporting any files larger than 100MB. The sub-agent would have up to 25 iterations and a timeout of 300 seconds to complete the task before it must report back to the parent MicroBot with its findings or any issues encountered.
"""


@dataclass
class MicrobotSubAgent(ExternalTool):
    """
    A MicroBotSubAgent is a specialized ExternalTool that represents a sub-agent
    running in the same sandbox environment.

    It inherits all behaviors of an ExternalTool, but is designed to be invoked
    by a parent MicroBot when the parent determines that a sub-agent is needed
    to perform a specific task.

    Key characteristics:
    - Runs as a separate MicroBot instance sharing the parent's environment.
    - Executes commands and performs tasks as directed by the parent MicroBot,
      with its own internal reasoning and decision-making capabilities.
    - Iteration counts are propagated back to the parent bot to prevent
      exceeding the overall iteration budget.
    """

    name: str = Field(default="microbot_sub")
    description: str = Field(
        default="A sub-agent that can be invoked by the parent MicroBot to "
        "perform specific tasks within the same sandbox environment.",
    )
    usage_instructions_to_llm: str = Field(default=INSTRUCTIONS_TO_LLM)
    install_commands: list[str] = Field(default_factory=list)

    def is_invoked(self, command: str) -> bool:
        return command.strip().startswith("microbot_sub")

    def invoke(self, command: str, parent_bot: "MicroBot") -> CmdReturn:
        """Parse the command, spawn a child MicroBot, and return a ``CmdReturn``.

        The MicroBot run-loop expects ``invoke`` to return a ``CmdReturn``
        (with ``.return_code``, ``.stdout``, ``.stderr``) — the same type
        returned by ``Environment.execute``.
        """
        # Parse arguments with argparse so flag-like text inside --task values
        # is handled correctly (e.g. --task "run --iterations check").
        parser = _NoExitArgumentParser(prog="microbot_sub", add_help=False)
        parser.add_argument("--task", type=str, default=None)
        parser.add_argument("--iterations", type=int, default=25)
        parser.add_argument("--timeout", type=int, default=300)

        try:
            tokens = shlex.split(command)[1:]  # skip the "microbot_sub" program name
            args = parser.parse_args(tokens)
        except ValueError as exc:
            logger.error("Failed to parse microbot_sub command: %s", exc)
            return CmdReturn(stdout="", stderr=f"Error: {exc}", return_code=1)

        task = args.task
        iterations = args.iterations
        timeout = args.timeout

        if not task:
            logger.error("No task specified for microbot_sub invocation.")
            return CmdReturn(stdout="", stderr="Error: No task specified.", return_code=1)

        if iterations <= 0 or timeout <= 0:
            logger.error("Iterations and timeout must be positive integers.")
            return CmdReturn(stdout="", stderr="Error: Iterations and timeout must be positive integers.", return_code=1)

        remaining = parent_bot.max_iterations - parent_bot.iteration_count
        if iterations > remaining:
            msg = (
                f"Error: Requesting {iterations} iterations but only {remaining} "
                f"remain in the parent bot's budget."
            )
            logger.error(msg)
            return CmdReturn(stdout="", stderr=msg, return_code=1)

        logger.info(
            "Invoking MicroBotSubAgent with task: %s, iterations: %d, timeout: %d",
            task, iterations, timeout,
        )

        sub_bot: MicroBot = MicroBot(
            model=parent_bot.model,
            system_prompt=system_prompt_common,
            environment=parent_bot.environment,
            token_provider=parent_bot.token_provider,
        )

        result: BotRunResult = sub_bot.run(
            task=task,
            max_iterations=iterations,
            timeout_in_seconds=timeout,
        )

        # Charge the sub-bot's iterations to the parent so we don't exceed
        # the overall iteration budget.
        parent_bot.iteration_count += sub_bot.iteration_count

        if result.status:
            logger.info("Sub-agent completed successfully with output: %s", result.result)
            return CmdReturn(stdout=result.result or "", stderr="", return_code=0)
        else:
            error_msg = f"Sub-agent failed: {result.error}"
            logger.error("Sub-agent failed with result: %s, error: %s", result.result, result.error)
            return CmdReturn(
                stdout=result.result or "",
                stderr=error_msg,
                return_code=1,
            )
