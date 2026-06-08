import logging
import os
from typing import Optional

from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.MicroBot import BotType, MicroBot, system_prompt_common
from microbots.tools.tool import ToolAbstract
from microbots.tools.tool_definitions.microbot_sub_agent import MicrobotSubAgent
from microbots.extras.mount import Mount

logger = logging.getLogger(__name__)


class AgentBoss(MicroBot):
    """A leadership bot that decomposes a complex task into subtasks
    and delegates each one to a ``microbot_sub`` agent running inside the sandbox.

    Workflow
    --------
    1. The user provides a high-level task.
    2. AgentBoss's system prompt instructs the LLM to break the task into
       ordered subtasks and invoke ``microbot_sub`` for each one.
    3. Each ``microbot_sub`` call spawns an autonomous MicroBot
       inside the same sandbox to solve a single subtask.
    4. After all subtasks are completed, the LLM synthesises the results
       into a final answer.
    """

    def __init__(
        self,
        model: str,
        folder_to_mount: str,
        environment: Optional[any] = None,
        additional_tools: Optional[list[ToolAbstract]] = None,
    ):
        """
        Parameters
        ----------
        model : str
            Model identifier in ``<provider>/<deployment>`` format.
        folder_to_mount : str
            Absolute host path to the repository the bot should operate on.
        environment : Optional[any]
            Pre-created execution environment.  A ``LocalDockerEnvironment``
            is created automatically when *None*.
        additional_tools : Optional[list[ToolAbstract]]
            Extra tools to install alongside the built-in ``microbot_sub`` tool.
        """
        if additional_tools is None:
            additional_tools = []

        # Always include the microbot_sub_agent external tool.
        sub_agent_tool = MicrobotSubAgent()
        additional_tools = [sub_agent_tool] + additional_tools

        base_name = os.path.basename(folder_to_mount)
        folder_mount_info = Mount(
            folder_to_mount,
            f"/{DOCKER_WORKING_DIR}/{base_name}",
            PermissionLabels.READ_WRITE,
        )

        system_prompt = f"""
{system_prompt_common}

You are an **Agent Boss**  a senior technical lead responsible for solving a complex task by breaking it down into smaller, focused subtasks and delegating each one to a sub-agent.

## Your environment
- The repository is mounted at `{folder_mount_info.sandbox_path}`.
- You have access to a `microbot_sub` tool inside this environment.

## microbot_sub usage
```
microbot_sub --task "<task description>" --iterations <max_iterations> --timeout <timeout_seconds>
```

- `--task` (required): A clear, self-contained description of the subtask so the sub-agent can work autonomously.
- `--iterations` (optional, default 25): Maximum number of iterations for the sub-agent.
- `--timeout` (optional, default 300): Timeout in seconds for the sub-agent.

## Your workflow
1. **Gather** context and requirements from the task description and any relevant files in the repository.
2. **Analyse** the task carefully. Identify what information you need and what changes are required.
3. **Decompose** the task into a numbered plan of subtasks (write them in your `thoughts`).
4. Linearly **Execute** each subtask one at a time by invoking `microbot_sub` with a detailed task description.
5. After each `microbot_sub` call, **review** its output before moving on. If a subtask failed, analyse the error and retry with a corrected task description.
6. When **all subtasks are complete**, set `task_done` to true and provide a comprehensive summary of everything that was done and the final outcome in `thoughts`.

## Important rules
- Run only ONE `microbot_sub` command at a time. Wait for the output before issuing the next one.
- Each `microbot_sub` call should be focused on a single, well-defined subtask. Avoid vague or multi-part instructions.
- Don't use sub-agents to do menial work like reading a file content or simple git commands. Use them for substantial subtasks that require reasoning and multiple steps.
- Keep subtasks focused and small  each sub-agent should do one thing well.
"""

        super().__init__(
            model=model,
            bot_type=BotType.CUSTOM_BOT,
            system_prompt=system_prompt,
            environment=environment,
            additional_tools=additional_tools,
            folder_to_mount=folder_mount_info,
        )

    def run(
        self,
        task: str,
        max_iterations: int = 50,
        timeout_in_seconds: int = 1200,
    ) -> any:
        """Solve *task* by decomposing it into subtasks and delegating to sub-agents.

        Parameters
        ----------
        task : str
            High-level task description.
        max_iterations : int
            Maximum LLM  shell round-trips (default 50  higher than a
            regular bot because the lead orchestrates multiple sub-agents).
        timeout_in_seconds : int
            Wall-clock timeout in seconds (default 1200 = 20 min).

        Returns
        -------
        BotRunResult
            The final status, result, and any error message.
        """
        lead_task_prompt = f"""
You are the Agent Boss. Solve the following task by decomposing it into subtasks and delegating each one to a microbot_sub agent.

Task:
{task}
"""
        return super().run(
            task=lead_task_prompt,
            max_iterations=max_iterations,
            timeout_in_seconds=timeout_in_seconds,
        )
