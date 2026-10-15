"""
Tests for AgentBoss.

Unit tests mock all heavy dependencies (Docker, LLM) so they can run fast
and offline.  Integration tests (marked ``slow``) exercise the full stack.
"""

import os
import sys

import pytest
from unittest.mock import patch, Mock, MagicMock, call

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from microbots import AgentBoss, BotRunResult
from microbots.MicroBot import MicroBot, BotType, system_prompt_common
from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.extras.mount import Mount, MountType
from microbots.tools.tool_definitions.microbot_sub_agent import MicrobotSubAgent
from microbots.tools.tool import ToolAbstract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_boss(
    model="azure-openai/test-deployment",
    folder_to_mount="/tmp/fake-repo",
    environment=None,
    additional_tools=None,
):
    """Create an AgentBoss with Docker and LLM mocked out."""
    mock_env = environment or MagicMock()

    with patch.object(MicroBot, "_create_environment") as mock_create_env, \
         patch.object(MicroBot, "_create_llm") as mock_create_llm:
        # When no environment is supplied, _create_environment sets self.environment,
        # so we simulate that here.
        def _set_env(folder_to_mount_arg):
            # The MicroBot constructor will call _create_environment when
            # self.environment is falsy — simulate it by assigning our mock.
            pass

        mock_create_env.side_effect = _set_env

        kwargs = dict(model=model, folder_to_mount=folder_to_mount)
        if environment is not None:
            kwargs["environment"] = environment
        if additional_tools is not None:
            kwargs["additional_tools"] = additional_tools

        # Temporarily patch install_tool / verify_tool_installation so the
        # constructor doesn't hit real code.
        with patch.object(MicrobotSubAgent, "install_tool"), \
             patch.object(MicrobotSubAgent, "verify_tool_installation"):
            boss = AgentBoss(**kwargs)

        # If we didn't supply an environment above, the real __init__ called
        # _create_environment (mocked) but never assigned self.environment.
        # Assign the mock now so the rest of the test can reference it.
        if not boss.environment:
            boss.environment = mock_env

        return boss, mock_create_env, mock_create_llm


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAgentBossInit:
    """Verify __init__ wiring without starting Docker or LLM."""

    def test_default_additional_tools_is_none(self):
        """When additional_tools is not passed it defaults to None and
        the constructor creates an empty list then prepends MicrobotSubAgent."""
        boss, *_ = _make_boss()

        # The only tool should be the auto-injected MicrobotSubAgent.
        assert len(boss.additional_tools) == 1
        assert isinstance(boss.additional_tools[0], MicrobotSubAgent)

    def test_additional_tools_prepends_sub_agent(self):
        """User-supplied tools are kept, but MicrobotSubAgent is first."""
        extra_tool = MagicMock(spec=ToolAbstract)
        extra_tool.install_tool = MagicMock()
        extra_tool.verify_tool_installation = MagicMock()
        extra_tool.setup_tool = MagicMock()
        extra_tool.usage_instructions_to_llm = None

        boss, *_ = _make_boss(additional_tools=[extra_tool])

        assert len(boss.additional_tools) == 2
        assert isinstance(boss.additional_tools[0], MicrobotSubAgent)
        assert boss.additional_tools[1] is extra_tool

    def test_folder_mount_is_read_write(self):
        """AgentBoss always mounts the repo as READ_WRITE."""
        boss, *_ = _make_boss(folder_to_mount="/tmp/my-repo")

        mount: Mount = boss.folder_to_mount
        assert mount.permission == PermissionLabels.READ_WRITE
        assert mount.mount_type == MountType.MOUNT

    def test_sandbox_path_uses_basename(self):
        """The sandbox path should be /<DOCKER_WORKING_DIR>/<basename>."""
        boss, *_ = _make_boss(folder_to_mount="/home/user/projects/cool-repo")

        expected = f"/{DOCKER_WORKING_DIR}/cool-repo"
        assert boss.folder_to_mount.sandbox_path == expected

    def test_host_path_preserved(self):
        """The original host path is stored in the mount."""
        host_path = "/tmp"
        boss, *_ = _make_boss(folder_to_mount=host_path)

        assert boss.folder_to_mount.host_path == host_path

    def test_system_prompt_contains_agent_boss_identity(self):
        """The system prompt must contain the AgentBoss-specific instructions."""
        boss, *_ = _make_boss()

        assert "Agent Boss" in boss.system_prompt
        assert "microbot_sub" in boss.system_prompt

    def test_system_prompt_contains_common_prompt(self):
        """The system prompt should include the shared base prompt."""
        boss, *_ = _make_boss()

        assert system_prompt_common in boss.system_prompt

    def test_system_prompt_contains_sandbox_path(self):
        """The system prompt should reference the sandbox mount path."""
        boss, *_ = _make_boss(folder_to_mount="/tmp/my-project")

        expected_path = f"/{DOCKER_WORKING_DIR}/my-project"
        assert expected_path in boss.system_prompt

    def test_bot_type_is_custom(self):
        """AgentBoss should register as CUSTOM_BOT."""
        boss, *_ = _make_boss()

        assert boss.bot_type == BotType.CUSTOM_BOT

    def test_model_provider_parsed(self):
        """Model provider should be extracted from the model string."""
        boss, *_ = _make_boss(model="azure-openai/gpt-5")

        assert boss.model_provider == "azure-openai"
        assert boss.deployment_name == "gpt-5"

    def test_environment_passed_through(self):
        """When an environment is explicitly provided it must be used."""
        mock_env = MagicMock()
        boss, mock_create_env, _ = _make_boss(environment=mock_env)

        assert boss.environment is mock_env
        # _create_environment should NOT have been called
        mock_create_env.assert_not_called()

    def test_environment_auto_created_when_none(self):
        """When no environment is given, _create_environment is called."""
        boss, mock_create_env, _ = _make_boss(environment=None)

        mock_create_env.assert_called_once()


@pytest.mark.unit
class TestAgentBossRun:
    """Verify the run() method delegates correctly to MicroBot.run."""

    def test_run_wraps_task_in_lead_prompt(self):
        """run() should wrap the task in an Agent-Boss-specific prompt."""
        boss, *_ = _make_boss()

        with patch.object(MicroBot, "run", return_value=BotRunResult(
            status=True, result="done", error=None
        )) as mock_super_run:
            boss.run(task="Fix the bug")

        called_task = mock_super_run.call_args[1].get("task") or mock_super_run.call_args[0][0]
        assert "Agent Boss" in called_task
        assert "Fix the bug" in called_task

    def test_run_default_iterations_and_timeout(self):
        """Default max_iterations=50, timeout_in_seconds=1200."""
        boss, *_ = _make_boss()

        with patch.object(MicroBot, "run", return_value=BotRunResult(
            status=True, result="ok", error=None
        )) as mock_super_run:
            boss.run(task="do something")

        mock_super_run.assert_called_once()
        _, kwargs = mock_super_run.call_args
        assert kwargs["max_iterations"] == 50
        assert kwargs["timeout_in_seconds"] == 1200

    def test_run_custom_iterations_and_timeout(self):
        """User-supplied iterations and timeout should be forwarded."""
        boss, *_ = _make_boss()

        with patch.object(MicroBot, "run", return_value=BotRunResult(
            status=True, result="ok", error=None
        )) as mock_super_run:
            boss.run(task="do something", max_iterations=100, timeout_in_seconds=3600)

        _, kwargs = mock_super_run.call_args
        assert kwargs["max_iterations"] == 100
        assert kwargs["timeout_in_seconds"] == 3600

    def test_run_returns_bot_run_result(self):
        """run() must return whatever MicroBot.run returns."""
        boss, *_ = _make_boss()
        expected = BotRunResult(status=True, result="all good", error=None)

        with patch.object(MicroBot, "run", return_value=expected):
            result = boss.run(task="anything")

        assert result is expected

    def test_run_propagates_failure(self):
        """A failed sub-run should be returned as-is."""
        boss, *_ = _make_boss()
        expected = BotRunResult(status=False, result=None, error="timeout")

        with patch.object(MicroBot, "run", return_value=expected):
            result = boss.run(task="slow task")

        assert result.status is False
        assert result.error == "timeout"

    def test_run_task_prompt_structure(self):
        """The lead_task_prompt must contain the expected framing text."""
        boss, *_ = _make_boss()

        original_task = "Refactor module X and add tests"
        with patch.object(MicroBot, "run", return_value=BotRunResult(
            status=True, result="done", error=None
        )) as mock_super_run:
            boss.run(task=original_task)

        called_task = mock_super_run.call_args[1]["task"]
        assert "decomposing it into subtasks" in called_task
        assert "delegating each one to a microbot_sub agent" in called_task
        assert original_task in called_task


# ---------------------------------------------------------------------------
# Integration tests (slow)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.docker
class TestAgentBossIntegration:
    """Slow integration tests that exercise AgentBoss end-to-end."""

    def test_agent_boss_solves_issue_1(self, test_repo, issue_1, openai_model):
        """AgentBoss should autonomously fix the missing-colon syntax error.

        The test mirrors ``test_microbot_2bot_combo`` but uses a single
        AgentBoss invocation instead of manually orchestrating two MicroBots.
        AgentBoss is expected to:
          1. Discover the failure in ``tests/missing_colon.py``.
          2. Diagnose the syntax error.
          3. Apply a fix.
        """
        assert test_repo is not None

        verify_function = issue_1[1]

        boss = AgentBoss(
            model=openai_model,
            folder_to_mount=str(test_repo),
        )

        response: BotRunResult = boss.run(
            task=(
                "The file tests/missing_colon.py has a syntax error that prevents it "
                "from running. Please identify the error and fix the source file so "
                "that `python3 tests/missing_colon.py` exits successfully."
            ),
            max_iterations=50,
            timeout_in_seconds=600,
        )

        logger.info(
            "AgentBoss result — Status: %s, Result: %s, Error: %s",
            response.status,
            response.result,
            response.error,
        )

        assert response.status, f"AgentBoss run failed: {response.error}"
        assert response.error is None

        # Verify that the fix was actually applied on the host repo
        verify_function(test_repo)
