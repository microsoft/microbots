"""
Unit and integration tests for CopilotBot.

Unit tests mock the copilot SDK and Docker environment to verify the
wiring and lifecycle.  Integration tests (marked ``@pytest.mark.integration``)
require a real Docker daemon, copilot-cli, and GitHub authentication.
"""

import contextlib
import importlib
import os
import shutil
import subprocess
import sys
import types
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

# ---------------------------------------------------------------------------
# Mock the copilot SDK before importing CopilotBot (optional dependency)
# ---------------------------------------------------------------------------
_mock_copilot = MagicMock()
_mock_copilot.CopilotClient = MagicMock
_mock_copilot.ExternalServerConfig = MagicMock

_mock_session = MagicMock()
_mock_session.PermissionRequestResult = MagicMock
_mock_session.PermissionHandler = MagicMock()
_mock_session.PermissionHandler.approve_all = MagicMock()

_mock_events = MagicMock()
_mock_events.SessionEventType = MagicMock()
_mock_events.SessionEventType.ASSISTANT_MESSAGE = "assistant.message"
_mock_events.SessionEventType.ASSISTANT_MESSAGE_DELTA = "assistant.message_delta"
_mock_events.SessionEventType.SESSION_IDLE = "session.idle"

_mock_tools = MagicMock()
_mock_tools.Tool = MagicMock
_mock_tools.ToolInvocation = MagicMock
_mock_tools.ToolResult = MagicMock
_mock_tools.define_tool = MagicMock

_mock_types = MagicMock()
_mock_types.PermissionHandler = MagicMock()
_mock_types.PermissionHandler.approve_all = MagicMock()

sys.modules.setdefault("copilot", _mock_copilot)
sys.modules.setdefault("copilot.session", _mock_session)
sys.modules.setdefault("copilot.generated.session_events", _mock_events)
sys.modules.setdefault("copilot.tools", _mock_tools)
sys.modules.setdefault("copilot.types", _mock_types)

# Reload to pick up mock
if "microbots.bot.CopilotBot" in sys.modules:
    importlib.reload(sys.modules["microbots.bot.CopilotBot"])

from microbots.MicroBot import BotRunResult


def _restore_real_copilot_modules():
    """Remove mock copilot modules from sys.modules and reload CopilotBot.

    This allows integration tests to use the real copilot SDK instead of
    the mocks injected at module level for unit tests.
    """
    mock_keys = [k for k in sys.modules if k == "copilot" or k.startswith("copilot.")]
    for key in mock_keys:
        del sys.modules[key]
    # Also force CopilotBot to re-import the real SDK on next import
    if "microbots.bot.CopilotBot" in sys.modules:
        del sys.modules["microbots.bot.CopilotBot"]


def _reinstall_default_copilot_mocks():
    """Reinstall the module-level copilot mocks and reload CopilotBot.

    Used to undo a temporary swap performed by ``_swap_copilot_sdk_layout``
    so subsequent tests in this file see the original mock fixtures.
    """
    sys.modules["copilot"] = _mock_copilot
    sys.modules["copilot.session"] = _mock_session
    sys.modules["copilot.generated.session_events"] = _mock_events
    sys.modules["copilot.tools"] = _mock_tools
    sys.modules["copilot.types"] = _mock_types
    if "microbots.bot.CopilotBot" in sys.modules:
        importlib.reload(sys.modules["microbots.bot.CopilotBot"])


@contextlib.contextmanager
def _swap_copilot_sdk_layout(*, session_has_handler: bool, types_has_handler: bool):
    """Temporarily install fresh stub modules for ``copilot.session`` and
    ``copilot.types`` to simulate a specific SDK layout, then reload
    ``microbots.bot.CopilotBot`` so the new import logic re-runs.

    ``session_has_handler``/``types_has_handler`` control whether
    ``PermissionHandler`` is exposed on the corresponding module.  The
    returned tuple yields the two ``PermissionHandler`` sentinels (or
    ``None`` when not present) so tests can assert which one was picked.
    """
    # Build a stub ``copilot`` package that still exposes CopilotClient and
    # ExternalServerConfig so the first try/except in __init__ succeeds.
    stub_copilot = types.ModuleType("copilot")
    stub_copilot.CopilotClient = _mock_copilot.CopilotClient
    stub_copilot.ExternalServerConfig = _mock_copilot.ExternalServerConfig

    stub_session = types.ModuleType("copilot.session")
    stub_session.PermissionRequestResult = MagicMock
    session_handler = MagicMock(name="session.PermissionHandler") if session_has_handler else None
    if session_handler is not None:
        session_handler.approve_all = MagicMock(name="session.approve_all")
        stub_session.PermissionHandler = session_handler

    stub_types = types.ModuleType("copilot.types")
    types_handler = MagicMock(name="types.PermissionHandler") if types_has_handler else None
    if types_handler is not None:
        types_handler.approve_all = MagicMock(name="types.approve_all")
        stub_types.PermissionHandler = types_handler

    saved = {
        name: sys.modules.get(name)
        for name in ("copilot", "copilot.session", "copilot.types")
    }
    sys.modules["copilot"] = stub_copilot
    sys.modules["copilot.session"] = stub_session
    sys.modules["copilot.types"] = stub_types
    # Other submodules (generated.session_events, tools) keep the existing
    # module-level mocks so CopilotBot's other imports still work.
    try:
        if "microbots.bot.CopilotBot" in sys.modules:
            importlib.reload(sys.modules["microbots.bot.CopilotBot"])
        yield session_handler, types_handler
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
        _reinstall_default_copilot_mocks()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _copilot_cli_available():
    return shutil.which("copilot") is not None


def _copilot_sdk_installed():
    try:
        from importlib.metadata import version
        version("github-copilot-sdk")
        return True
    except Exception:
        return False


def _copilot_auth_available():
    if os.environ.get("GITHUB_TOKEN") or os.environ.get("COPILOT_GITHUB_TOKEN"):
        return True
    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Unit test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_environment():
    """Create a mock LocalDockerEnvironment."""
    env = MagicMock()
    env.port = 9000
    env.container_port = 8080
    env.container = MagicMock()
    env.container.id = "abc123def456"
    env.image = "kavyasree261002/shell_server:latest"
    env.working_dir = "/tmp/mock_workdir"
    env.folder_to_mount = None
    env.overlay_mount = False

    # Make execute return success by default
    success_return = MagicMock()
    success_return.return_code = 0
    success_return.stdout = "copilot version 1.0.0"
    success_return.stderr = ""
    env.execute = MagicMock(return_value=success_return)
    env.copy_to_container = MagicMock(return_value=True)
    env.stop = MagicMock()
    env.get_ipv4_address = MagicMock(return_value="172.17.0.2")
    return env


@pytest.fixture
def mock_copilot_session():
    """Mock Copilot SDK session."""
    session = AsyncMock()
    session.disconnect = AsyncMock()

    response = Mock()
    response.data = Mock()
    response.data.content = "Task completed successfully."
    session.send_and_wait = AsyncMock(return_value=response)
    session.on = MagicMock()
    return session


@pytest.fixture
def mock_copilot_client(mock_copilot_session):
    """Mock CopilotClient."""
    client = AsyncMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.create_session = AsyncMock(return_value=mock_copilot_session)
    return client


@pytest.fixture
def copilot_bot(mock_environment, mock_copilot_client):
    """Create a CopilotBot with all external dependencies mocked."""
    with (
        patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
        patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
        patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
        patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
        patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
        patch("copilot.CopilotClient", return_value=mock_copilot_client),
        patch("copilot.ExternalServerConfig", return_value=MagicMock()),
    ):
        from microbots.bot.CopilotBot import CopilotBot
        bot = CopilotBot(
            model="gpt-4.1",
            environment=mock_environment,
            github_token="ghp_test_token_123",
        )
        yield bot
        # Stop the event loop thread properly before teardown
        try:
            bot._loop.call_soon_threadsafe(bot._loop.stop)
            bot._thread.join(timeout=2)
        except Exception:
            pass
        bot.environment = None  # Prevent stop() from trying env.stop() again


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotInit:
    """Tests for CopilotBot initialisation."""

    def test_stores_model(self, copilot_bot):
        assert copilot_bot.model == "gpt-4.1"

    def test_stores_github_token(self, copilot_bot):
        assert copilot_bot.github_token == "ghp_test_token_123"

    def test_environment_assigned(self, copilot_bot, mock_environment):
        assert copilot_bot.environment is mock_environment

    def test_additional_tools_default_empty(self, copilot_bot):
        assert copilot_bot.additional_tools == []

    def test_rejects_external_tool(self, mock_environment, mock_copilot_client):
        """CopilotBot raises ValueError if an ExternalTool is passed."""
        from microbots.tools.external_tool import ExternalTool

        ext_tool = MagicMock(spec=ExternalTool)
        ext_tool.name = "my_external"

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            with pytest.raises(ValueError, match="does not support ExternalTool"):
                CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                    additional_tools=[ext_tool],
                    github_token="ghp_test",
                )

    def test_import_error_without_sdk(self):
        """CopilotBot raises ImportError when copilot SDK is not installed."""
        # Temporarily remove the mock so the import fails
        saved = sys.modules.get("copilot")
        try:
            sys.modules["copilot"] = None  # Force ImportError on import
            # Need to reload the module
            if "microbots.bot.CopilotBot" in sys.modules:
                importlib.reload(sys.modules["microbots.bot.CopilotBot"])
            from microbots.bot.CopilotBot import CopilotBot as CB
            with pytest.raises(ImportError, match="github-copilot-sdk"):
                CB(model="gpt-4.1")
        finally:
            sys.modules["copilot"] = saved
            if "microbots.bot.CopilotBot" in sys.modules:
                importlib.reload(sys.modules["microbots.bot.CopilotBot"])

    # ──────────────────────────────────────────────────────────────────
    # PermissionHandler import path — covers the new logic in __init__
    # that supports both pre-0.3.0 and >=0.3.0 github-copilot-sdk layouts.
    # ──────────────────────────────────────────────────────────────────

    def _build_bot_under_swap(self, mock_environment, mock_copilot_client):
        """Construct a CopilotBot using the reloaded module under the
        currently-active ``_swap_copilot_sdk_layout`` context."""
        from microbots.bot.CopilotBot import CopilotBot
        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )
        return bot

    def test_permission_handler_loaded_from_session(
        self, mock_environment, mock_copilot_client
    ):
        """SDK >= 0.3.0: ``PermissionHandler`` is loaded from copilot.session
        and is preferred over copilot.types when both expose it."""
        with _swap_copilot_sdk_layout(
            session_has_handler=True, types_has_handler=True
        ) as (session_handler, types_handler):
            bot = self._build_bot_under_swap(mock_environment, mock_copilot_client)
            try:
                assert bot._PermissionHandler is session_handler
                assert bot._PermissionHandler is not types_handler
            finally:
                bot._loop.call_soon_threadsafe(bot._loop.stop)
                bot._thread.join(timeout=2)
                bot.environment = None

    def test_permission_handler_falls_back_to_types(
        self, mock_environment, mock_copilot_client
    ):
        """Pre-0.3.0 SDK: ``PermissionHandler`` is absent from copilot.session
        and the import falls back to copilot.types."""
        with _swap_copilot_sdk_layout(
            session_has_handler=False, types_has_handler=True
        ) as (session_handler, types_handler):
            assert session_handler is None
            bot = self._build_bot_under_swap(mock_environment, mock_copilot_client)
            try:
                assert bot._PermissionHandler is types_handler
            finally:
                bot._loop.call_soon_threadsafe(bot._loop.stop)
                bot._thread.join(timeout=2)
                bot.environment = None

    def test_import_error_when_permission_handler_missing_everywhere(
        self, mock_environment, mock_copilot_client
    ):
        """If neither copilot.session nor copilot.types exposes
        ``PermissionHandler`` we raise a distinct, accurate ImportError
        (and not the misleading "github-copilot-sdk is not installed" one)."""
        with _swap_copilot_sdk_layout(
            session_has_handler=False, types_has_handler=False
        ):
            from microbots.bot.CopilotBot import CopilotBot
            with pytest.raises(ImportError, match="PermissionHandler"):
                with (
                    patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
                    patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
                    patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
                    patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
                    patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
                    patch("copilot.CopilotClient", return_value=mock_copilot_client),
                    patch("copilot.ExternalServerConfig", return_value=MagicMock()),
                ):
                    CopilotBot(
                        model="gpt-4.1",
                        environment=mock_environment,
                        github_token="ghp_test",
                    )


@pytest.mark.unit
class TestCopilotBotRun:
    """Tests for CopilotBot.run()."""

    def test_run_returns_bot_run_result(self, copilot_bot):
        result = copilot_bot.run("Fix the bug in main.py")
        assert isinstance(result, BotRunResult)

    def test_run_success(self, copilot_bot):
        result = copilot_bot.run("Fix the bug in main.py")
        assert result.status is True
        assert result.error is None
        assert result.result is not None

    def test_run_calls_tool_setup(self, copilot_bot, mock_environment):
        mock_tool = MagicMock()
        mock_tool.usage_instructions_to_llm = "Use tool X"
        mock_tool.install_commands = []
        mock_tool.verify_commands = []
        copilot_bot.additional_tools = [mock_tool]

        copilot_bot.run("test task")
        mock_tool.setup_tool.assert_called_once_with(mock_environment)

    def test_run_handles_exception(self, copilot_bot):
        """Run returns failure BotRunResult on exceptions."""
        with patch.object(copilot_bot, "_run_async", side_effect=RuntimeError("boom")):
            result = copilot_bot.run("test")
            assert result.status is False
            assert "boom" in result.error


@pytest.mark.unit
class TestCopilotBotSystemMessage:
    """Tests for system message construction."""

    def test_system_message_empty_no_mount_no_tools(self, copilot_bot):
        msg = copilot_bot._build_system_message()
        assert msg == ""

    def test_system_message_includes_mount_path(self, mock_environment, mock_copilot_client):
        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            from microbots.extras.mount import Mount
            mount = Mount("/tmp/test_repo", "/workdir/test_repo", "READ_WRITE")
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )
            bot.folder_to_mount = mount
            msg = bot._build_system_message()
            assert "/workdir/test_repo" in msg
            bot.stop()

    def test_system_message_includes_tool_instructions(self, copilot_bot):
        mock_tool = MagicMock()
        mock_tool.usage_instructions_to_llm = "# Use browser command"
        copilot_bot.additional_tools = [mock_tool]

        msg = copilot_bot._build_system_message()
        assert "browser" in msg


@pytest.mark.unit
class TestCopilotBotStop:
    """Tests for CopilotBot.stop()."""

    def test_stop_cleans_environment(self, copilot_bot, mock_environment):
        copilot_bot.stop()
        mock_environment.stop.assert_called_once()

    def test_stop_idempotent(self, copilot_bot, mock_environment):
        copilot_bot.stop()
        copilot_bot.stop()  # Should not raise


@pytest.mark.unit
class TestCopilotBotCLIInstall:
    """Tests for copilot-cli installation logic."""

    def test_install_cli_calls_execute(self, mock_environment):
        from microbots.bot.CopilotBot import CopilotBot

        with (
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=AsyncMock()),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )
            # _install_copilot_cli was called during __init__
            # Verify that execute was called with npm install command
            calls = [str(c) for c in mock_environment.execute.call_args_list]
            npm_calls = [c for c in calls if "npm install" in c or "copilot" in c]
            assert len(npm_calls) > 0, "Expected copilot-cli install commands"
            bot.stop()

    def test_install_cli_raises_on_failure(self, mock_environment):
        from microbots.bot.CopilotBot import CopilotBot

        fail_return = MagicMock()
        fail_return.return_code = 1
        fail_return.stdout = ""
        fail_return.stderr = "npm ERR! not found"
        mock_environment.execute = MagicMock(return_value=fail_return)

        with (
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=AsyncMock()),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            with pytest.raises(RuntimeError, match="Failed to install copilot-cli"):
                CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                    github_token="ghp_test",
                )


# ---------------------------------------------------------------------------
# Unit tests — resolve_auth_config and BYOK
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveAuthConfig:
    """Tests for the standalone resolve_auth_config function."""

    def test_explicit_api_key_returns_byok_provider(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        model, gh_token, provider = resolve_auth_config(
            model="gpt-4.1",
            api_key="sk-test-key",
            base_url="https://api.openai.com/v1",
        )
        assert model == "gpt-4.1"
        assert gh_token is None
        assert provider is not None
        assert provider["type"] == "openai"
        assert provider["base_url"] == "https://api.openai.com/v1"
        assert provider["api_key"] == "sk-test-key"
        assert "bearer_token" not in provider

    def test_explicit_bearer_token_takes_precedence_over_api_key(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        _, _, provider = resolve_auth_config(
            model="gpt-4.1",
            api_key="sk-key",
            bearer_token="my-bearer",
            base_url="https://api.openai.com/v1",
        )
        assert provider["bearer_token"] == "my-bearer"
        assert "api_key" not in provider

    def test_explicit_api_key_without_base_url_raises(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        with pytest.raises(ValueError, match="base_url"):
            resolve_auth_config(model="gpt-4.1", api_key="sk-test")

    def test_azure_provider_type_includes_api_version(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        _, _, provider = resolve_auth_config(
            model="gpt-4.1",
            api_key="azure-key",
            base_url="https://my-resource.openai.azure.com",
            provider_type="azure",
            azure_api_version="2024-10-21",
        )
        assert provider["type"] == "azure"
        assert provider["azure"] == {"api_version": "2024-10-21"}

    def test_wire_api_included_when_set(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        _, _, provider = resolve_auth_config(
            model="gpt-5",
            api_key="key",
            base_url="https://endpoint.com/v1",
            wire_api="responses",
        )
        assert provider["wire_api"] == "responses"

    def test_env_vars_resolve_byok(self, monkeypatch):
        from microbots.bot.CopilotBot import resolve_auth_config

        monkeypatch.setenv("COPILOT_BYOK_BASE_URL", "https://env-endpoint.com/v1")
        monkeypatch.setenv("COPILOT_BYOK_API_KEY", "env-key")
        monkeypatch.setenv("COPILOT_BYOK_PROVIDER_TYPE", "anthropic")
        monkeypatch.setenv("COPILOT_BYOK_MODEL", "claude-sonnet-4.5")

        model, gh_token, provider = resolve_auth_config(model="gpt-4.1")
        assert model == "claude-sonnet-4.5"
        assert gh_token is None
        assert provider["type"] == "anthropic"
        assert provider["base_url"] == "https://env-endpoint.com/v1"
        assert provider["api_key"] == "env-key"

    def test_env_vars_bearer_token(self, monkeypatch):
        from microbots.bot.CopilotBot import resolve_auth_config

        monkeypatch.setenv("COPILOT_BYOK_BASE_URL", "https://endpoint.com/v1")
        monkeypatch.setenv("COPILOT_BYOK_BEARER_TOKEN", "env-bearer")

        _, _, provider = resolve_auth_config(model="gpt-4.1")
        assert provider["bearer_token"] == "env-bearer"
        assert "api_key" not in provider

    def test_env_vars_ignored_when_explicit_key_provided(self, monkeypatch):
        from microbots.bot.CopilotBot import resolve_auth_config

        monkeypatch.setenv("COPILOT_BYOK_BASE_URL", "https://env-endpoint.com/v1")
        monkeypatch.setenv("COPILOT_BYOK_API_KEY", "env-key")

        _, _, provider = resolve_auth_config(
            model="gpt-4.1",
            api_key="explicit-key",
            base_url="https://explicit.com/v1",
        )
        assert provider["api_key"] == "explicit-key"
        assert provider["base_url"] == "https://explicit.com/v1"

    def test_token_provider_returns_byok_with_bearer(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        _, _, provider = resolve_auth_config(
            model="gpt-4.1",
            base_url="https://azure.endpoint.com/v1",
            token_provider=lambda: "ad-token-123",
        )
        assert provider["bearer_token"] == "ad-token-123"
        assert "api_key" not in provider

    def test_token_provider_without_base_url_raises(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        with pytest.raises(ValueError, match="base_url"):
            resolve_auth_config(
                model="gpt-4.1",
                token_provider=lambda: "token",
            )

    def test_token_provider_not_callable_raises(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        with pytest.raises(ValueError, match="callable"):
            resolve_auth_config(
                model="gpt-4.1",
                base_url="https://endpoint.com/v1",
                token_provider="not-a-callable",
            )

    def test_token_provider_returning_empty_raises(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        with pytest.raises(ValueError, match="non-empty"):
            resolve_auth_config(
                model="gpt-4.1",
                base_url="https://endpoint.com/v1",
                token_provider=lambda: "",
            )

    def test_token_provider_exception_raises(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        def bad_provider():
            raise RuntimeError("auth failed")

        with pytest.raises(ValueError, match="auth failed"):
            resolve_auth_config(
                model="gpt-4.1",
                base_url="https://endpoint.com/v1",
                token_provider=bad_provider,
            )

    def test_fallback_to_github_token(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        model, gh_token, provider = resolve_auth_config(
            model="gpt-4.1",
            github_token="ghp_test123",
        )
        assert model == "gpt-4.1"
        assert gh_token == "ghp_test123"
        assert provider is None

    def test_default_provider_type_is_openai(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        _, _, provider = resolve_auth_config(
            model="m", api_key="k", base_url="https://x.com/v1"
        )
        assert provider["type"] == "openai"

    def test_anthropic_provider_type(self):
        from microbots.bot.CopilotBot import resolve_auth_config

        _, _, provider = resolve_auth_config(
            model="claude-sonnet-4.5",
            api_key="ant-key",
            base_url="https://api.anthropic.com",
            provider_type="anthropic",
        )
        assert provider["type"] == "anthropic"


@pytest.mark.unit
class TestCopilotBotBYOKInit:
    """Tests for CopilotBot initialisation with BYOK parameters."""

    def test_byok_api_key_sets_provider_config(self, mock_environment, mock_copilot_client):
        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                api_key="sk-byok-key",
                base_url="https://api.openai.com/v1",
            )
            assert bot._provider_config is not None
            assert bot._provider_config["api_key"] == "sk-byok-key"
            assert bot.github_token is None
            bot.stop()

    def test_byok_token_provider_sets_provider_config(self, mock_environment, mock_copilot_client):
        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                base_url="https://azure.endpoint.com/v1",
                token_provider=lambda: "ad-token-xyz",
            )
            assert bot._provider_config is not None
            assert bot._provider_config["bearer_token"] == "ad-token-xyz"
            assert bot.github_token is None
            bot.stop()

    def test_native_auth_has_no_provider_config(self, copilot_bot):
        assert copilot_bot._provider_config is None
        assert copilot_bot.github_token == "ghp_test_token_123"


# ---------------------------------------------------------------------------
# Helper context manager shared by several new test classes
# ---------------------------------------------------------------------------

def _standard_init_patches(mock_environment, mock_copilot_client):
    """Return a combined context manager for standard CopilotBot init patches."""
    return (
        patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
        patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
        patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
        patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
        patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
        patch("copilot.CopilotClient", return_value=mock_copilot_client),
        patch("copilot.ExternalServerConfig", return_value=MagicMock()),
    )


# ---------------------------------------------------------------------------
# Unit tests — __init__ with folder_to_mount and auto-created environment
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotInitFolderMount:
    """Tests for __init__ paths: folder_to_mount string and auto environment."""

    def test_folder_to_mount_creates_mount_object(self, mock_environment, mock_copilot_client):
        """When folder_to_mount string is provided, a Mount is stored."""
        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
                folder_to_mount="/tmp/test_repo",
            )
            assert bot.folder_to_mount is not None
            assert "test_repo" in bot.folder_to_mount.sandbox_path
            bot.stop()

    def test_auto_creates_environment_when_none(self, mock_environment, mock_copilot_client):
        """When environment=None, LocalDockerEnvironment is instantiated."""
        mock_environment.get_ipv4_address = MagicMock(return_value="172.17.0.2")
        with (
            patch(
                "microbots.bot.CopilotBot.LocalDockerEnvironment",
                return_value=mock_environment,
            ) as mock_lde,
            patch("microbots.bot.CopilotBot.get_free_port", return_value=9000),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                github_token="ghp_test",
            )
            mock_lde.assert_called_once()
            assert bot.environment is mock_environment
            bot.stop()


# ---------------------------------------------------------------------------
# Unit tests — non-ExternalTool installation in __init__
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotNonExternalToolInstall:
    """Tests that non-ExternalTool tools are installed during __init__."""

    def test_non_external_tool_install_and_verify_called(
        self, mock_environment, mock_copilot_client
    ):
        """install_tool and verify_tool_installation are called for regular tools."""
        from microbots.tools.tool import ToolAbstract

        mock_tool = MagicMock(spec=ToolAbstract)
        mock_tool.name = "my_tool"
        mock_tool.usage_instructions_to_llm = "Use my_tool"

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
                additional_tools=[mock_tool],
            )
            mock_tool.install_tool.assert_called_once_with(mock_environment)
            mock_tool.verify_tool_installation.assert_called_once_with(mock_environment)
            bot.stop()


# ---------------------------------------------------------------------------
# Unit tests — _install_copilot_cli verification failure
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotCLIVerification:
    """Tests that copilot-cli verification failure raises RuntimeError."""

    def test_install_cli_verify_fails_raises(self, mock_environment):
        """RuntimeError raised when install commands succeed but 'copilot --version' fails."""
        from microbots.bot.CopilotBot import CopilotBot

        success_ret = MagicMock()
        success_ret.return_code = 0
        success_ret.stdout = ""
        success_ret.stderr = ""

        fail_ret = MagicMock()
        fail_ret.return_code = 1
        fail_ret.stdout = ""
        fail_ret.stderr = "command not found: copilot"

        def side_effect(cmd, **kwargs):
            if "copilot --version" in cmd:
                return fail_ret
            return success_ret

        mock_environment.execute = MagicMock(side_effect=side_effect)

        with (
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=AsyncMock()),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            with pytest.raises(RuntimeError, match="verification failed"):
                CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                    github_token="ghp_test",
                )


# ---------------------------------------------------------------------------
# Unit tests — _start_copilot_cli_server
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotStartServer:
    """Tests for _start_copilot_cli_server()."""

    def _make_bot_for_server_test(self, mock_environment, mock_copilot_client, github_token=None, provider_config=None):
        """Build a CopilotBot with _start_copilot_cli_server NOT patched."""
        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            if github_token:
                bot = CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                    github_token=github_token,
                )
            elif provider_config:
                bot = CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                    api_key="sk-key",
                    base_url="https://api.openai.com/v1",
                )
            else:
                bot = CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                )
            return bot

    def test_start_server_injects_github_token(self, mock_environment, mock_copilot_client):
        """Token injection calls when github_token is set without provider_config."""
        bot = self._make_bot_for_server_test(
            mock_environment, mock_copilot_client, github_token="ghp_server_test"
        )
        execute_args = [str(c) for c in mock_environment.execute.call_args_list]
        assert any("GITHUB_TOKEN" in a for a in execute_args)
        assert any("COPILOT_GITHUB_TOKEN" in a for a in execute_args)
        bot.stop()

    def test_start_server_skips_token_injection_for_byok(
        self, mock_environment, mock_copilot_client
    ):
        """No token injection when BYOK provider_config is active."""
        bot = self._make_bot_for_server_test(
            mock_environment, mock_copilot_client, provider_config=True
        )
        execute_args = [str(c) for c in mock_environment.execute.call_args_list]
        assert not any("GITHUB_TOKEN" in a for a in execute_args)
        bot.stop()

    def test_start_server_raises_on_execute_failure(self, mock_environment, mock_copilot_client):
        """RuntimeError raised when start_cmd execute fails."""
        fail_ret = MagicMock()
        fail_ret.return_code = 1
        fail_ret.stderr = "failed to start"

        success_ret = MagicMock()
        success_ret.return_code = 0
        success_ret.stdout = ""
        success_ret.stderr = ""

        def side_effect(cmd, **kwargs):
            if "copilot --headless" in cmd:
                return fail_ret
            return success_ret

        mock_environment.execute = MagicMock(side_effect=side_effect)

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            with pytest.raises(RuntimeError, match="Failed to start copilot-cli server"):
                CopilotBot(
                    model="gpt-4.1",
                    environment=mock_environment,
                    github_token="ghp_test",
                )


# ---------------------------------------------------------------------------
# Unit tests — _wait_for_cli_ready
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotWaitReady:
    """Tests for _wait_for_cli_ready() called directly on a minimal instance."""

    def _make_minimal_bot(self):
        """Return a bare CopilotBot instance with only environment set."""
        from microbots.bot.CopilotBot import CopilotBot

        bot = object.__new__(CopilotBot)
        mock_env = MagicMock()
        mock_env.get_ipv4_address = MagicMock(return_value="127.0.0.1")
        bot.environment = mock_env
        return bot

    def test_wait_for_cli_ready_success(self):
        """Returns immediately when socket connection succeeds."""
        bot = self._make_minimal_bot()
        mock_sock = MagicMock()
        with patch("socket.create_connection", return_value=mock_sock) as mock_conn:
            bot._wait_for_cli_ready()
            mock_conn.assert_called_once()
            mock_sock.close.assert_called_once()

    def test_wait_for_cli_ready_timeout(self):
        """Raises TimeoutError when connections always fail past the deadline."""
        bot = self._make_minimal_bot()
        with (
            patch("socket.create_connection", side_effect=ConnectionRefusedError()),
            patch("microbots.bot.CopilotBot.time") as mock_time,
        ):
            # First call sets deadline (0 + _CLI_STARTUP_TIMEOUT), second exceeds it
            mock_time.time.side_effect = [0, 9999]
            mock_time.sleep = MagicMock()
            with pytest.raises(TimeoutError, match="copilot-cli did not become ready"):
                bot._wait_for_cli_ready()

    def test_wait_for_cli_ready_oserror_retries(self):
        """OSError is caught and retried like ConnectionRefusedError."""
        bot = self._make_minimal_bot()
        mock_sock = MagicMock()
        # First attempt raises OSError, second attempt succeeds
        with patch("socket.create_connection", side_effect=[OSError("network error"), mock_sock]):
            with patch("microbots.bot.CopilotBot.time") as mock_time:
                mock_time.time.side_effect = [0, 1, 2]
                mock_time.sleep = MagicMock()
                bot._wait_for_cli_ready()
                mock_sock.close.assert_called_once()


# ---------------------------------------------------------------------------
# Unit tests — run() with additional_mounts
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotRunMounts:
    """Tests for run() with additional_mounts parameter."""

    def test_run_with_additional_mounts_calls_mount_additional(self, copilot_bot):
        """_mount_additional is called for each mount in additional_mounts."""
        from microbots.extras.mount import Mount, MountType

        mock_mount = MagicMock(spec=Mount)
        mock_mount.mount_type = MountType.COPY
        mock_mount.host_path_info = MagicMock()
        mock_mount.host_path_info.abs_path = "/tmp/extra"
        mock_mount.sandbox_path = "/workdir/extra"

        copilot_bot.environment.copy_to_container = MagicMock(return_value=True)

        with patch.object(copilot_bot, "_mount_additional") as mock_ma:
            copilot_bot.run("test task", additional_mounts=[mock_mount])
            mock_ma.assert_called_once_with(mock_mount)


# ---------------------------------------------------------------------------
# Unit tests — _execute_session
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotExecuteSession:
    """Tests for _execute_session() paths."""

    def test_execute_session_includes_provider_config(self, mock_environment, mock_copilot_client):
        """provider is added to session kwargs when _provider_config is set."""
        import asyncio

        session = AsyncMock()
        response = Mock()
        response.data = Mock()
        response.data.content = "done"
        session.send_and_wait = AsyncMock(return_value=response)
        session.on = MagicMock()
        session.disconnect = AsyncMock()
        mock_copilot_client.create_session = AsyncMock(return_value=session)

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                api_key="sk-key",
                base_url="https://api.openai.com/v1",
            )
            result = asyncio.run(
                bot._execute_session(
                    task="do something",
                    system_content="",
                    timeout=30,
                    streaming=False,
                )
            )
            _, call_kwargs = mock_copilot_client.create_session.call_args
            assert "provider" in call_kwargs
            assert result == "done"
            bot.stop()

    def test_execute_session_includes_system_message(self, mock_environment, mock_copilot_client):
        """system_message is added to session kwargs when system_content is non-empty."""
        import asyncio

        session = AsyncMock()
        response = Mock()
        response.data = Mock()
        response.data.content = "done"
        session.send_and_wait = AsyncMock(return_value=response)
        session.on = MagicMock()
        session.disconnect = AsyncMock()
        mock_copilot_client.create_session = AsyncMock(return_value=session)

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )
            asyncio.run(
                bot._execute_session(
                    task="do something",
                    system_content="You are a helper.",
                    timeout=30,
                    streaming=False,
                )
            )
            _, call_kwargs = mock_copilot_client.create_session.call_args
            assert "system_message" in call_kwargs
            assert call_kwargs["system_message"]["content"] == "You are a helper."
            bot.stop()

    def test_execute_session_returns_collected_event_text(
        self, mock_environment, mock_copilot_client
    ):
        """Returns last collected text when send_and_wait returns no content."""
        import asyncio

        session = AsyncMock()
        # send_and_wait returns response with no content
        empty_response = Mock()
        empty_response.data = Mock()
        empty_response.data.content = ""
        session.send_and_wait = AsyncMock(return_value=empty_response)
        session.disconnect = AsyncMock()

        captured = []

        def capture_on(callback):
            captured.append(callback)

        session.on = MagicMock(side_effect=capture_on)
        mock_copilot_client.create_session = AsyncMock(return_value=session)

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            from copilot.generated.session_events import SessionEventType

            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )

            # Simulate an ASSISTANT_MESSAGE event arriving before send_and_wait returns
            async def _send_and_wait_with_event(task, timeout):
                if captured:
                    msg_event = Mock()
                    msg_event.type = SessionEventType.ASSISTANT_MESSAGE
                    msg_event.data = Mock()
                    msg_event.data.content = "from event"
                    captured[0](msg_event)
                return empty_response

            session.send_and_wait = _send_and_wait_with_event

            result = asyncio.run(
                bot._execute_session(
                    task="do something",
                    system_content="",
                    timeout=30,
                    streaming=False,
                )
            )
            assert result == "from event"
            bot.stop()

    def test_execute_session_returns_fallback_when_no_content(
        self, mock_environment, mock_copilot_client
    ):
        """Returns fallback message when no text is collected at all."""
        import asyncio

        session = AsyncMock()
        empty_response = Mock()
        empty_response.data = Mock()
        empty_response.data.content = ""
        session.send_and_wait = AsyncMock(return_value=empty_response)
        session.on = MagicMock()
        session.disconnect = AsyncMock()
        mock_copilot_client.create_session = AsyncMock(return_value=session)

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )
            result = asyncio.run(
                bot._execute_session(
                    task="do something",
                    system_content="",
                    timeout=1,
                    streaming=False,
                )
            )
            assert "without producing" in result
            bot.stop()

    def test_execute_session_on_event_handlers(self, mock_environment, mock_copilot_client):
        """_on_event handles ASSISTANT_MESSAGE_DELTA, SESSION_IDLE, and unknown types."""
        import asyncio

        session = AsyncMock()
        empty_response = Mock()
        empty_response.data = Mock()
        empty_response.data.content = ""
        session.disconnect = AsyncMock()

        captured = []

        def capture_on(callback):
            captured.append(callback)

        session.on = MagicMock(side_effect=capture_on)

        async def _send_and_wait_with_events(task, timeout):
            if captured:
                cb = captured[0]
                # ASSISTANT_MESSAGE_DELTA with delta_content
                delta_event = Mock()
                delta_event.type = "assistant.message_delta"
                delta_event.data = Mock()
                delta_event.data.delta_content = "partial"
                cb(delta_event)

                # SESSION_IDLE
                idle_event = Mock()
                idle_event.type = "session.idle"
                cb(idle_event)

                # Unknown event type
                unknown_event = Mock()
                unknown_event.type = "some.other.event"
                cb(unknown_event)

                # ASSISTANT_MESSAGE with no content (data.content is empty)
                msg_empty = Mock()
                msg_empty.type = "assistant.message"
                msg_empty.data = Mock()
                msg_empty.data.content = ""
                cb(msg_empty)

            return empty_response

        session.send_and_wait = _send_and_wait_with_events
        mock_copilot_client.create_session = AsyncMock(return_value=session)

        with (
            patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=mock_environment),
            patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
            patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
            patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
            patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
            patch("copilot.CopilotClient", return_value=mock_copilot_client),
            patch("copilot.ExternalServerConfig", return_value=MagicMock()),
        ):
            from microbots.bot.CopilotBot import CopilotBot
            bot = CopilotBot(
                model="gpt-4.1",
                environment=mock_environment,
                github_token="ghp_test",
            )
            # Should not raise — covers all branches of _on_event
            asyncio.run(
                bot._execute_session(
                    task="do something",
                    system_content="",
                    timeout=5,
                    streaming=False,
                )
            )
            bot.stop()


# ---------------------------------------------------------------------------
# Unit tests — _on_pre_tool_use and _on_post_tool_use hooks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotToolUseHooks:
    """Tests for _on_pre_tool_use() and _on_post_tool_use() async hooks."""

    def test_on_pre_tool_use_returns_allow(self, copilot_bot):
        import asyncio

        result = asyncio.run(
            copilot_bot._on_pre_tool_use(
                {"toolName": "bash", "toolArgs": {"command": "ls"}},
                None,
            )
        )
        assert result == {"permissionDecision": "allow"}

    def test_on_pre_tool_use_missing_keys(self, copilot_bot):
        import asyncio

        result = asyncio.run(copilot_bot._on_pre_tool_use({}, None))
        assert result == {"permissionDecision": "allow"}

    def test_on_post_tool_use_returns_empty_dict(self, copilot_bot):
        import asyncio

        result = asyncio.run(
            copilot_bot._on_post_tool_use(
                {"toolName": "bash", "toolResult": "output here"},
                None,
            )
        )
        assert result == {}

    def test_on_post_tool_use_truncates_long_result(self, copilot_bot):
        import asyncio

        long_result = "x" * 600
        # Should not raise even with a very long result string
        result = asyncio.run(
            copilot_bot._on_post_tool_use(
                {"toolName": "bash", "toolResult": long_result},
                None,
            )
        )
        assert result == {}

    def test_on_post_tool_use_missing_keys(self, copilot_bot):
        import asyncio

        result = asyncio.run(copilot_bot._on_post_tool_use({}, None))
        assert result == {}


# ---------------------------------------------------------------------------
# Unit tests — _mount_additional
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopilotBotMountAdditional:
    """Tests for _mount_additional()."""

    def test_mount_additional_non_copy_raises(self, copilot_bot):
        """ValueError raised for non-COPY mount type."""
        from microbots.extras.mount import Mount, MountType

        mock_mount = MagicMock()
        mock_mount.mount_type = MountType.MOUNT  # not COPY
        with pytest.raises(ValueError, match="Only COPY mount type"):
            copilot_bot._mount_additional(mock_mount)

    def test_mount_additional_copy_fails_raises(self, copilot_bot):
        """ValueError raised when copy_to_container returns False."""
        from microbots.extras.mount import MountType

        mock_mount = MagicMock()
        mock_mount.mount_type = MountType.COPY
        mock_mount.host_path_info = MagicMock()
        mock_mount.host_path_info.abs_path = "/host/path"
        mock_mount.sandbox_path = "/workdir/path"

        copilot_bot.environment.copy_to_container = MagicMock(return_value=False)
        with pytest.raises(ValueError, match="Failed to copy additional mount"):
            copilot_bot._mount_additional(mock_mount)

    def test_mount_additional_copy_succeeds(self, copilot_bot):
        """No error raised when copy_to_container succeeds."""
        from microbots.extras.mount import MountType

        mock_mount = MagicMock()
        mock_mount.mount_type = MountType.COPY
        mock_mount.host_path_info = MagicMock()
        mock_mount.host_path_info.abs_path = "/host/path"
        mock_mount.sandbox_path = "/workdir/path"

        copilot_bot.environment.copy_to_container = MagicMock(return_value=True)
        copilot_bot._mount_additional(mock_mount)  # should not raise


# ---------------------------------------------------------------------------
# Integration tests — SDK compatibility (both pre-0.3.0 and >=0.3.0 layouts)
#
# These exercise the full ``CopilotBot.__init__`` → ``run()`` → assistant-
# response path against simulated SDK module layouts so we can verify *both*
# supported ``github-copilot-sdk`` shapes in a single test run (only one
# version of the real SDK can be installed at a time).  External I/O (Docker,
# CLI startup, network) is stubbed out; everything else — the new
# PermissionHandler import branch, the asyncio loop, session creation,
# event handling, result extraction — runs for real.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCopilotBotSDKLayoutIntegration:
    """Integration-level tests that drive a full ``run()`` against each
    supported SDK module layout."""

    def _run_bot_with_layout(self, *, session_has_handler, types_has_handler):
        """Build and run a CopilotBot under a simulated SDK layout.

        Returns ``(result, bot, session_handler, types_handler)`` where
        ``result`` is the ``BotRunResult`` from ``bot.run()``.
        """
        # Mock Docker environment
        env = MagicMock()
        env.port = 9000
        env.container_port = 8080
        env.container = MagicMock()
        env.container.id = "abc123"
        env.image = "image:latest"
        env.working_dir = "/tmp/work"
        env.folder_to_mount = None
        env.overlay_mount = False
        ok = MagicMock()
        ok.return_code = 0
        ok.stdout = "copilot version 1.0.0"
        ok.stderr = ""
        env.execute = MagicMock(return_value=ok)
        env.copy_to_container = MagicMock(return_value=True)
        env.stop = MagicMock()
        env.get_ipv4_address = MagicMock(return_value="172.17.0.2")

        # Mock SDK session + client
        session = AsyncMock()
        session.disconnect = AsyncMock()
        response = Mock()
        response.data = Mock()
        response.data.content = "Task completed successfully."
        session.send_and_wait = AsyncMock(return_value=response)
        session.on = MagicMock()
        client = AsyncMock()
        client.start = AsyncMock()
        client.stop = AsyncMock()
        client.create_session = AsyncMock(return_value=session)

        with _swap_copilot_sdk_layout(
            session_has_handler=session_has_handler,
            types_has_handler=types_has_handler,
        ) as (session_handler, types_handler):
            from microbots.bot.CopilotBot import CopilotBot
            with (
                patch("microbots.bot.CopilotBot.LocalDockerEnvironment", return_value=env),
                patch("microbots.bot.CopilotBot.get_free_port", side_effect=[9000]),
                patch("microbots.bot.CopilotBot.CopilotBot._install_copilot_cli"),
                patch("microbots.bot.CopilotBot.CopilotBot._start_copilot_cli_server"),
                patch("microbots.bot.CopilotBot.CopilotBot._wait_for_cli_ready"),
                patch("copilot.CopilotClient", return_value=client),
                patch("copilot.ExternalServerConfig", return_value=MagicMock()),
            ):
                bot = CopilotBot(
                    model="gpt-4.1",
                    environment=env,
                    github_token="ghp_test",
                )
                try:
                    result = bot.run("Do the thing")
                finally:
                    # Tear down the asyncio loop thread cleanly
                    bot._loop.call_soon_threadsafe(bot._loop.stop)
                    bot._thread.join(timeout=2)
                    bot.environment = None
            return result, bot, session_handler, types_handler, client

    def test_run_with_new_sdk_layout_session(self):
        """SDK >= 0.3.0: PermissionHandler lives in ``copilot.session``.

        Verifies CopilotBot initialises, picks up the handler from
        ``copilot.session``, and ``run()`` completes successfully passing
        that handler as ``on_permission_request``."""
        result, bot, session_handler, types_handler, client = self._run_bot_with_layout(
            session_has_handler=True, types_has_handler=False
        )
        assert types_handler is None
        assert bot._PermissionHandler is session_handler
        assert result.status is True, f"run() failed: {result.error}"
        assert result.error is None
        # The new-SDK handler must be the one wired into the session.
        kwargs = client.create_session.await_args.kwargs
        assert kwargs["on_permission_request"] is session_handler.approve_all

    def test_run_with_old_sdk_layout_types(self):
        """Pre-0.3.0 SDK: PermissionHandler lives in ``copilot.types``.

        Verifies CopilotBot falls back to ``copilot.types`` and ``run()``
        still completes successfully wiring that handler through to the
        session."""
        result, bot, session_handler, types_handler, client = self._run_bot_with_layout(
            session_has_handler=False, types_has_handler=True
        )
        assert session_handler is None
        assert bot._PermissionHandler is types_handler
        assert result.status is True, f"run() failed: {result.error}"
        assert result.error is None
        kwargs = client.create_session.await_args.kwargs
        assert kwargs["on_permission_request"] is types_handler.approve_all


# ---------------------------------------------------------------------------
# Integration tests — require real Docker + copilot-cli + auth
# ---------------------------------------------------------------------------

_skip_no_copilot_cli = pytest.mark.skipif(
    not _copilot_cli_available(),
    reason="GitHub Copilot CLI not installed (copilot not in PATH)",
)

_skip_no_copilot_sdk = pytest.mark.skipif(
    not _copilot_sdk_installed(),
    reason="github-copilot-sdk not installed (pip install microbots[ghcp])",
)

_skip_no_copilot_auth = pytest.mark.skipif(
    not _copilot_auth_available(),
    reason="No GitHub auth available (set GITHUB_TOKEN or run 'gh auth login')",
)


@_skip_no_copilot_cli
@_skip_no_copilot_sdk
@_skip_no_copilot_auth
@pytest.mark.integration
@pytest.mark.slow
class TestCopilotBotIntegration:
    """End-to-end integration tests with real Copilot SDK."""

    def test_simple_task(self, test_repo, issue_1):
        """CopilotBot can fix a simple syntax error."""
        _restore_real_copilot_modules()
        from microbots.bot.CopilotBot import CopilotBot

        issue_text = issue_1[0]
        verify_function = issue_1[1]

        bot = CopilotBot(
            model="gpt-4.1",
            folder_to_mount=str(test_repo),
            permission="READ_WRITE",
        )

        try:
            result = bot.run(
                issue_text,
                timeout_in_seconds=300,
            )
            assert result.status is True, f"CopilotBot failed: {result.error}"
            verify_function(test_repo)
        finally:
            bot.stop()


# ---------------------------------------------------------------------------
# BYOK helpers
# ---------------------------------------------------------------------------

def _byok_openai_available():
    """Check if OpenAI BYOK credentials are configured via env vars."""
    return bool(
        os.environ.get("OPEN_AI_KEY")
        and os.environ.get("OPEN_AI_END_POINT")
    )


_skip_no_byok_openai = pytest.mark.skipif(
    not _byok_openai_available(),
    reason="OpenAI BYOK not configured (set OPEN_AI_KEY and OPEN_AI_END_POINT)",
)


@_skip_no_copilot_cli
@_skip_no_copilot_sdk
@_skip_no_byok_openai
@pytest.mark.integration
@pytest.mark.slow
class TestCopilotBotBYOKOpenAIIntegration:
    """End-to-end integration tests for CopilotBot with OpenAI BYOK."""

    def test_byok_openai_simple_task(self, test_repo, issue_1):
        """CopilotBot can fix a simple syntax error using OpenAI BYOK credentials."""
        _restore_real_copilot_modules()
        from microbots.bot.CopilotBot import CopilotBot

        issue_text = issue_1[0]
        verify_function = issue_1[1]

        api_key = os.environ["OPEN_AI_KEY"]
        base_url = os.environ["OPEN_AI_END_POINT"]
        model = os.getenv(
            "AZURE_OPENAI_DEPLOYMENT_NAME", "mini-swe-agent-gpt5"
        )

        bot = CopilotBot(
            model=model,
            folder_to_mount=str(test_repo),
            permission="READ_WRITE",
            api_key=api_key,
            base_url=base_url,
            provider_type="openai",
        )

        try:
            assert bot._provider_config is not None
            assert bot._provider_config["type"] == "openai"
            assert bot.github_token is None

            result = bot.run(
                issue_text,
                timeout_in_seconds=300,
            )
            assert result.status is True, f"CopilotBot BYOK run failed: {result.error}"
            verify_function(test_repo)
        finally:
            bot.stop()

    def test_byok_openai_simple_task_with_token_provider(self, test_repo, issue_1):
        """CopilotBot can fix a simple syntax error using OpenAI BYOK credentials."""
        _restore_real_copilot_modules()
        from microbots.bot.CopilotBot import CopilotBot

        issue_text = issue_1[0]
        verify_function = issue_1[1]

        api_key = os.environ["OPEN_AI_KEY"]
        base_url = os.environ["OPEN_AI_END_POINT"]
        model = os.getenv(
            "AZURE_OPENAI_DEPLOYMENT_NAME", "mini-swe-agent-gpt5"
        )

        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        def get_token():
                return credential.get_token(
                    "https://cognitiveservices.azure.com/.default"
                ).token

        bot = CopilotBot(
            model=model,
            folder_to_mount=str(test_repo),
            permission="READ_WRITE",
            api_key=api_key,
            base_url=base_url,
            provider_type="openai",
            token_provider=get_token,
        )

        try:
            assert bot._provider_config is not None
            assert bot._provider_config["type"] == "openai"
            assert bot.github_token is None

            result = bot.run(
                issue_text,
                timeout_in_seconds=300,
            )
            assert result.status is True, f"CopilotBot BYOK run failed: {result.error}"
            verify_function(test_repo)
        finally:
            bot.stop()

