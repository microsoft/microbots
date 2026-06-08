"""
CopilotBot — A wrapper around the GitHub Copilot SDK.

Unlike MicroBot (which manages its own LLM ↔ shell agent loop), CopilotBot
delegates the **entire agent loop to the Copilot runtime**.  Copilot handles
planning, tool invocation (file edits, shell commands, web requests, etc.)
and multi-turn reasoning autonomously.

CopilotBot reuses the Microbots infrastructure:
  - Docker sandbox (LocalDockerEnvironment) for isolated execution
  - Mount system for folder access control
  - ToolAbstract lifecycle (install → verify → setup) for additional tools
  - copilot-cli is installed **inside** the container and run in headless
    server mode; the SDK on the host connects to it via TCP.

Architecture:

    Host                          Docker Container
    ─────                         ────────────────
    CopilotBot                    copilot-cli --headless --port <P>
        │                              │
        ├── Copilot SDK ──TCP──────────┘
        │   (ExternalServerConfig)
        │
        ├── additional tools
        │   (define_tool → SDK session)
        │
        └── BotRunResult

Prerequisites:
  - pip install microbots[ghcp]   (github-copilot-sdk)
  - Docker daemon running
  - GitHub authentication (GITHUB_TOKEN / COPILOT_GITHUB_TOKEN or copilot login)
"""

import asyncio
import os
import time
import threading
from collections.abc import Callable
from logging import getLogger
from typing import Optional

from microbots.constants import (
    DOCKER_WORKING_DIR,
    PermissionLabels,
)
from microbots.environment.local_docker.LocalDockerEnvironment import (
    LocalDockerEnvironment,
)
from microbots.extras.mount import Mount, MountType
from microbots.MicroBot import BotRunResult
from microbots.tools.external_tool import ExternalTool
from microbots.tools.tool import ToolAbstract
from microbots.utils.copilot_auth import get_copilot_token
from microbots.utils.network import get_free_port  # still used for _create_environment

logger = getLogger(" CopilotBot ")

# Default model when none is specified (just the deployment name, no provider prefix)
_DEFAULT_MODEL = "gpt-4.1"

# Time (seconds) to wait for copilot-cli to start inside the container
_CLI_STARTUP_TIMEOUT = 60

# copilot-cli port inside the container
_CONTAINER_CLI_PORT = 4321

# Environment variable names for BYOK configuration
_BYOK_ENV_PROVIDER_TYPE = "COPILOT_BYOK_PROVIDER_TYPE"
_BYOK_ENV_BASE_URL = "COPILOT_BYOK_BASE_URL"
_BYOK_ENV_API_KEY = "COPILOT_BYOK_API_KEY"
_BYOK_ENV_BEARER_TOKEN = "COPILOT_BYOK_BEARER_TOKEN"
_BYOK_ENV_WIRE_API = "COPILOT_BYOK_WIRE_API" # completions / responses
_BYOK_ENV_AZURE_API_VERSION = "COPILOT_BYOK_AZURE_API_VERSION"
_BYOK_ENV_MODEL = "COPILOT_BYOK_MODEL"


def resolve_auth_config(
    model: str = _DEFAULT_MODEL,
    github_token: Optional[str] = None,
    api_key: Optional[str] = None,
    bearer_token: Optional[str] = None,
    base_url: Optional[str] = None,
    provider_type: Optional[str] = None,
    wire_api: Optional[str] = None,
    azure_api_version: Optional[str] = None,
    token_provider: Optional[Callable[[], str]] = None,
) -> tuple[str, Optional[str], Optional[dict]]:
    """Resolve authentication and provider configuration for CopilotBot.

    Determines whether to use BYOK (Bring Your Own Key) or native GitHub
    Copilot authentication, and builds the appropriate provider config.

    Priority order:
      1. Explicit ``api_key`` or ``bearer_token`` with ``base_url`` → BYOK
      2. Environment variables (``COPILOT_BYOK_*``) → BYOK
      3. ``token_provider`` (e.g. Azure AD token provider) → BYOK with bearer token
      4. GitHub token → native Copilot authentication

    Parameters
    ----------
    model : str
        Model name (e.g. ``"gpt-4.1"``, ``"claude-sonnet-4.5"``).
    github_token : Optional[str]
        GitHub token for native Copilot auth.
    api_key : Optional[str]
        API key for BYOK provider.
    bearer_token : Optional[str]
        Bearer token for BYOK (takes precedence over ``api_key``).
    base_url : Optional[str]
        API endpoint URL for BYOK provider.
    provider_type : Optional[str]
        Provider type: ``"openai"``, ``"azure"``, or ``"anthropic"``.
    wire_api : Optional[str]
        API format: ``"completions"`` or ``"responses"``.
    azure_api_version : Optional[str]
        Azure API version (only for ``type: "azure"``).
    token_provider : Optional[Callable[[], str]]
        Callable that returns a bearer token string (e.g. Azure AD
        token provider).  The token is fetched once at config resolution
        time.  For long-running sessions, create a new session with a
        refreshed token.

    Returns
    -------
    tuple[str, Optional[str], Optional[dict]]
        ``(model, github_token, provider_config)`` where
        ``provider_config`` is *None* for native Copilot auth or a dict
        suitable for the ``provider`` kwarg of ``create_session``.

    Raises
    ------
    ValueError
        If BYOK is requested but ``base_url`` is missing, or if
        ``token_provider`` is not a valid callable.
    """

    # ── 1. Explicit api_key / bearer_token ───────────────────────────
    if api_key or bearer_token:
        if not base_url:
            raise ValueError(
                "BYOK requires a base_url when api_key or bearer_token is provided."
            )
        provider = _build_provider_config(
            provider_type=provider_type or "openai",
            base_url=base_url,
            api_key=api_key,
            bearer_token=bearer_token,
            wire_api=wire_api,
            azure_api_version=azure_api_version,
        )
        logger.info("🔑 BYOK auth resolved via explicit credentials (type=%s)", provider["type"])
        return model, None, provider

    # ── 2. Environment variables ─────────────────────────────────────
    env_base_url = os.environ.get(_BYOK_ENV_BASE_URL)
    env_api_key = os.environ.get(_BYOK_ENV_API_KEY)
    env_bearer_token = os.environ.get(_BYOK_ENV_BEARER_TOKEN)

    if env_base_url and (env_api_key or env_bearer_token):
        env_model = os.environ.get(_BYOK_ENV_MODEL, model)
        provider = _build_provider_config(
            provider_type=os.environ.get(_BYOK_ENV_PROVIDER_TYPE, "openai"),
            base_url=env_base_url,
            api_key=env_api_key,
            bearer_token=env_bearer_token,
            wire_api=os.environ.get(_BYOK_ENV_WIRE_API),
            azure_api_version=os.environ.get(_BYOK_ENV_AZURE_API_VERSION),
        )
        logger.info("🔑 BYOK auth resolved via environment variables (type=%s)", provider["type"])
        return env_model, None, provider

    # ── 2.5. BYOK base_url set but no key/bearer → auto-detect via DefaultAzureCredential ──
    # Only fires when COPILOT_BYOK_PROVIDER_TYPE is also set (explicit BYOK intent).
    # Without it, a bare COPILOT_BYOK_BASE_URL would hijack tests that expect native Copilot auth.
    env_provider_type = os.environ.get(_BYOK_ENV_PROVIDER_TYPE)
    if env_base_url and env_provider_type and not (env_api_key or env_bearer_token) and not token_provider:
        try:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            _credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                _credential, "https://cognitiveservices.azure.com/.default"
            )
            logger.debug("DefaultAzureCredential configured for BYOK — falling through to step 3")
        except Exception as e:
            logger.debug("DefaultAzureCredential not available for BYOK: %s", e)

    # ── 3. Token provider (e.g. Azure AD) ────────────────────────────
    if token_provider:
        if not callable(token_provider):
            raise ValueError("token_provider must be a callable that returns a string token.")
        resolved_url = base_url or env_base_url
        if not resolved_url:
            raise ValueError(
                "BYOK with token_provider requires a base_url (pass it directly "
                "or set COPILOT_BYOK_BASE_URL)."
            )
        try:
            token = token_provider()
        except Exception as e:
            raise ValueError(f"token_provider failed during validation: {e}") from e
        if not isinstance(token, str) or not token:
            raise ValueError("token_provider must return a non-empty string token.")

        provider = _build_provider_config(
            provider_type=provider_type or os.environ.get(_BYOK_ENV_PROVIDER_TYPE, "openai"),
            base_url=resolved_url,
            bearer_token=token,
            wire_api=wire_api or os.environ.get(_BYOK_ENV_WIRE_API),
            azure_api_version=azure_api_version or os.environ.get(_BYOK_ENV_AZURE_API_VERSION),
        )
        logger.info("🔑 BYOK auth resolved via token_provider (type=%s)", provider["type"])
        return os.environ.get(_BYOK_ENV_MODEL, model), None, provider

    # ── 4. Native GitHub Copilot auth ────────────────────────────────
    resolved_github_token = (
        github_token
        or os.environ.get("COPILOT_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or get_copilot_token()
    )
    logger.info("🔑 Using native GitHub Copilot authentication")
    return model, resolved_github_token, None


def _build_provider_config(
    provider_type: str,
    base_url: str,
    api_key: Optional[str] = None,
    bearer_token: Optional[str] = None,
    wire_api: Optional[str] = None,
    azure_api_version: Optional[str] = None,
) -> dict:
    """Build the ``provider`` dict accepted by ``create_session``."""
    config: dict = {
        "type": provider_type,
        "base_url": base_url,
    }
    # bearer_token takes precedence over api_key per SDK docs
    if bearer_token:
        config["bearer_token"] = bearer_token
    elif api_key:
        config["api_key"] = api_key

    if wire_api:
        config["wire_api"] = wire_api

    if provider_type == "azure" and azure_api_version:
        config["azure"] = {"api_version": azure_api_version}

    return config


class CopilotBot:
    """Wrapper around the GitHub Copilot SDK with a sandboxed Docker environment.

    The Copilot runtime manages the agent loop (planning, tool calls,
    multi-turn reasoning).  CopilotBot sets up the sandbox, installs
    copilot-cli inside it, connects the SDK, and exposes a simple
    ``run(task)`` interface.

    Parameters
    ----------
    model : str
        Copilot model name (e.g. ``"gpt-4.1"``, ``"claude-sonnet-4.5"``).
        Unlike MicroBot, no ``<provider>/`` prefix is needed.
    folder_to_mount : str
        Absolute host path to mount into the sandbox.
    permission : PermissionLabels
        Mount permission — READ_ONLY or READ_WRITE.  Defaults to READ_WRITE.
    environment : Optional[LocalDockerEnvironment]
        Pre-created environment.  One is created automatically when *None*.
    additional_tools : Optional[list[ToolAbstract]]
        Extra Microbots tools to install in the sandbox.  Their
        ``usage_instructions_to_llm`` are appended to the system message
        and, where possible, they are registered as SDK custom tools.
    github_token : Optional[str]
        Explicit GitHub token.  Falls back to ``GITHUB_TOKEN`` /
        ``COPILOT_GITHUB_TOKEN`` env vars.  Used only when BYOK is not
        configured.
    api_key : Optional[str]
        API key for BYOK provider.  When provided with ``base_url``,
        bypasses GitHub Copilot auth and uses the key directly.
    bearer_token : Optional[str]
        Bearer token for BYOK provider.  Takes precedence over ``api_key``.
    base_url : Optional[str]
        API endpoint URL for BYOK (e.g.
        ``"https://api.openai.com/v1"``).
    provider_type : Optional[str]
        BYOK provider type: ``"openai"``, ``"azure"``, or
        ``"anthropic"``.  Defaults to ``"openai"``.
    wire_api : Optional[str]
        API format: ``"completions"`` (default) or ``"responses"``
        (for GPT-5 series).
    azure_api_version : Optional[str]
        Azure API version string (only for ``provider_type="azure"``).
    token_provider : Optional[Callable[[], str]]
        A callable returning a bearer token (e.g. Azure AD token
        provider).  Requires ``base_url``.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        folder_to_mount: Optional[str] = None,
        permission: PermissionLabels = PermissionLabels.READ_WRITE,
        environment: Optional[LocalDockerEnvironment] = None,
        additional_tools: Optional[list[ToolAbstract]] = None,
        github_token: Optional[str] = None,
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        base_url: Optional[str] = None,
        provider_type: Optional[str] = None,
        wire_api: Optional[str] = None,
        azure_api_version: Optional[str] = None,
        token_provider: Optional[Callable[[], str]] = None,
    ):
        try:
            from copilot import CopilotClient, ExternalServerConfig
        except ImportError:
            raise ImportError(
                "CopilotBot requires the github-copilot-sdk package. "
                "Install with: pip install microbots[ghcp]"
            )

        # ``PermissionHandler`` lives in ``copilot.session`` in
        # github-copilot-sdk >= 0.3.0 and in ``copilot.types`` in older
        # releases.  Try the new location first and fall back to the old
        # one so we work with both.
        try:
            from copilot.session import PermissionHandler
        except ImportError:
            try:
                from copilot.types import PermissionHandler
            except ImportError as exc:
                raise ImportError(
                    "CopilotBot could not locate 'PermissionHandler' in the "
                    "installed github-copilot-sdk (looked in copilot.session "
                    "and copilot.types). Please install a compatible version, "
                    "e.g. pip install -U microbots[ghcp]."
                ) from exc

        self.additional_tools = additional_tools or []

        # ── Resolve auth: BYOK vs native GitHub Copilot ─────────────
        self.model, self.github_token, self._provider_config = resolve_auth_config(
            model=model,
            github_token=github_token,
            api_key=api_key,
            bearer_token=bearer_token,
            base_url=base_url,
            provider_type=provider_type,
            wire_api=wire_api,
            azure_api_version=azure_api_version,
            token_provider=token_provider,
        )

        # ── Mount setup ─────────────────────────────────────────────
        self.folder_to_mount: Optional[Mount] = None
        if folder_to_mount:
            sandbox_path = f"/{DOCKER_WORKING_DIR}/{os.path.basename(folder_to_mount)}"
            self.folder_to_mount = Mount(folder_to_mount, sandbox_path, permission)

        # ── Docker environment ──────────────────────────────────────
        self.environment = environment
        if not self.environment:
            self._create_environment()

        # ── Validate tools — ExternalTool is not supported ──────────
        # __ And ___
        # ── Install additional tools inside the container ───────────
        for tool in self.additional_tools:
            if isinstance(tool, ExternalTool):
                raise ValueError(
                    f"CopilotBot does not support ExternalTool '{tool.name}'. "
                    f"copilot-cli runs inside the Docker container, so only "
                    f"internal (container-side) tools are allowed."
                )

            logger.info("🔧 Installing additional tool '%s'...", tool.name)
            tool.install_tool(self.environment)
            tool.verify_tool_installation(self.environment)
            logger.info("✅ Tool '%s' installed and verified", tool.name)

        # ── Install & start copilot-cli inside the container ────────
        self._install_copilot_cli()
        self._start_copilot_cli_server()

        # ── Background event loop for async SDK calls ───────────────
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        # ── Connect SDK to in-container CLI ─────────────────────────
        container_ip = self.environment.get_ipv4_address()
        logger.info("🔌 Connecting Copilot SDK to CLI server at %s:%d", container_ip, _CONTAINER_CLI_PORT)
        self._client = CopilotClient(
            ExternalServerConfig(url=f"{container_ip}:{_CONTAINER_CLI_PORT}")
        )
        self._run_async(self._client.start())
        self._PermissionHandler = PermissionHandler

        logger.info(
            "✅ CopilotBot initialised — model=%s, cli=%s:%d",
            self.model,
            container_ip,
            _CONTAINER_CLI_PORT,
        )

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def run(
        self,
        task: str,
        additional_mounts: Optional[list[Mount]] = None,
        timeout_in_seconds: int = 600,
        streaming: bool = False,
    ) -> BotRunResult:
        """Send *task* to the Copilot agent and wait for completion.

        The Copilot runtime manages the full agent loop autonomously —
        planning, tool invocation, multi-turn reasoning, and file edits
        all happen inside the sandboxed environment.

        Parameters
        ----------
        task : str
            A natural-language description of the task.
        additional_mounts : Optional[list[Mount]]
            Extra folders to copy into the container before running.
        timeout_in_seconds : int
            Maximum wall-clock time for the agent run.
        streaming : bool
            Whether to enable streaming delta events (logged at DEBUG level).

        Returns
        -------
        BotRunResult
            status=True on success with the agent's final message in *result*,
            or status=False with an error description.
        """
        logger.info("🚀 Starting CopilotBot run — task: %.120s...", task)

        # Setup additional tools (env vars, files, setup_commands)
        for tool in self.additional_tools:
            logger.info("⚙️  Setting up tool '%s'", tool.name)
            tool.setup_tool(self.environment)

        # Mount additional folders
        for mount in additional_mounts or []:
            self._mount_additional(mount)

        # Build system message with tool instructions
        system_content = self._build_system_message()

        try:
            result_text = self._run_async(
                self._execute_session(
                    task=task,
                    system_content=system_content,
                    timeout=timeout_in_seconds,
                    streaming=streaming,
                )
            )
            logger.info("✅ CopilotBot run completed successfully")
            return BotRunResult(status=True, result=result_text, error=None)
        except Exception as e:
            logger.exception("❌ CopilotBot run failed: %s", e)
            return BotRunResult(status=False, result=None, error=str(e))

    def stop(self):
        """Tear down the SDK client, CLI server, and Docker environment."""
        if getattr(self, "_stopped", False):
            return
        self._stopped = True

        # Stop the SDK client (best-effort, with timeout to avoid deadlock)
        try:
            if self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._client.stop(), self._loop
                )
                future.result(timeout=10)
        except Exception:
            pass

        # Shut down the background event loop
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
        except Exception:
            pass

        if self.environment:
            self.environment.stop()
            self.environment = None
        logger.info("CopilotBot stopped")

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # Private — environment & CLI setup
    # ──────────────────────────────────────────────────────────────────

    def _create_environment(self):
        free_port = get_free_port()
        self.environment = LocalDockerEnvironment(
            port=free_port,
            folder_to_mount=self.folder_to_mount,
        )

    def _install_copilot_cli(self):
        """Install copilot-cli inside the Docker container."""
        logger.info("📦 Installing copilot-cli inside container...")

        # Install Node.js (required for copilot-cli via npm)
        install_commands = [
            # Remove stale third-party repos that may have expired GPG keys
            "rm -f /etc/apt/sources.list.d/yarn.list",
            # Install Node.js 22.x (copilot-cli requires Node 22+)
            "apt-get update -qq && apt-get install -y -qq curl ca-certificates > /dev/null 2>&1",
            "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - > /dev/null 2>&1",
            "apt-get install -y -qq nodejs > /dev/null 2>&1",
            # Install copilot-cli globally
            # NOTE: Pinning to 1.0.39 which is the latest @github/copilot release compatible with github-copilot-sdk==0.3.0 as of May 2026.
            "npm install -g @github/copilot@1.0.39 > /dev/null 2>&1",
        ]

        for cmd in install_commands:
            result = self.environment.execute(cmd, timeout=300)
            if result.return_code != 0:
                raise RuntimeError(
                    f"Failed to install copilot-cli: {cmd}\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}"
                )

        # Verify installation
        verify = self.environment.execute("copilot --version")
        if verify.return_code != 0:
            raise RuntimeError(
                f"copilot-cli installation verification failed: {verify.stderr}"
            )
        logger.info("✅ copilot-cli installed: %s", verify.stdout.strip())

    def _start_copilot_cli_server(self):
        """Start copilot-cli in headless server mode inside the container.

        The CLI listens on ``_CONTAINER_CLI_PORT`` inside the container.
        The host connects directly to the container's bridge-network IP.
        Authentication is handled via the GITHUB_TOKEN environment variable
        injected into the container.
        """
        # Inject the GitHub token into the container for native Copilot auth.
        # When BYOK is active, authentication is handled via the provider
        # config passed to create_session — no container-side token needed.
        if self.github_token and not self._provider_config:
            self.environment.execute(
                f'export GITHUB_TOKEN="{self.github_token}"', sensitive=True
            )
            self.environment.execute(
                f'export COPILOT_GITHUB_TOKEN="{self.github_token}"', sensitive=True
            )

        # Start copilot in headless mode in the background
        # Using nohup + & to run it as a background process inside the container's shell
        start_cmd = (
            f"nohup copilot --headless --port {_CONTAINER_CLI_PORT} --host 0.0.0.0 "
            f"> /var/log/copilot-cli.log 2>&1 &"
        )
        result = self.environment.execute(start_cmd)
        if result.return_code != 0:
            raise RuntimeError(
                f"Failed to start copilot-cli server: {result.stderr}"
            )

        # Wait for the server to be ready
        self._wait_for_cli_ready()
        logger.info(
            "✅ copilot-cli headless server running on container port %d",
            _CONTAINER_CLI_PORT,
        )

    def _wait_for_cli_ready(self):
        """Poll until the copilot-cli server is accepting connections."""
        import socket as _socket

        container_ip = self.environment.get_ipv4_address()
        deadline = time.time() + _CLI_STARTUP_TIMEOUT
        while time.time() < deadline:
            try:
                self.environment.execute("pgrep -f 'copilot.*--headless' || true")
                sock = _socket.create_connection(
                    (container_ip, _CONTAINER_CLI_PORT), timeout=5
                )
                sock.close()
                return
            except (ConnectionRefusedError, OSError):
                time.sleep(1)
        self.environment.execute("cat /var/log/copilot-cli.log || true")
        raise TimeoutError(
            f"copilot-cli did not become ready within {_CLI_STARTUP_TIMEOUT}s "
            f"on {container_ip}:{_CONTAINER_CLI_PORT}"
        )

    # ──────────────────────────────────────────────────────────────────
    # Private — SDK session & execution
    # ──────────────────────────────────────────────────────────────────

    def _run_async(self, coro):
        """Submit an async coroutine to the background loop and block."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def _execute_session(
        self,
        task: str,
        system_content: str,
        timeout: int,
        streaming: bool,
    ) -> str:
        """Create a Copilot session, send the task, and collect the result."""
        from copilot.generated.session_events import SessionEventType

        session_kwargs = {
            "model": self.model,
            "on_permission_request": self._PermissionHandler.approve_all,
            "streaming": streaming,
            "hooks": {
                "on_pre_tool_use": self._on_pre_tool_use,
                "on_post_tool_use": self._on_post_tool_use,
            },
        }

        if self._provider_config:
            session_kwargs["provider"] = self._provider_config

        if system_content:
            session_kwargs["system_message"] = {"content": system_content}

        logger.info("📡 Creating Copilot session (model=%s, streaming=%s, byok=%s)", self.model, streaming, self._provider_config is not None)
        logger.debug("Session kwargs: %s", session_kwargs)
        session = await self._client.create_session(**session_kwargs)

        collected_text = []
        done_event = asyncio.Event()

        def _on_event(event):
            if event.type == SessionEventType.ASSISTANT_MESSAGE:
                if event.data and event.data.content:
                    collected_text.append(event.data.content)
                    logger.info("💬 Assistant message received (%d chars)", len(event.data.content))
            elif event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                if event.data and event.data.delta_content:
                    logger.debug("📝 %s", event.data.delta_content)
            elif event.type == SessionEventType.SESSION_IDLE:
                logger.info("⏹️  Session idle — agent finished processing")
                done_event.set()
            else:
                logger.debug("📨 Session event: %s", event.type)

        session.on(_on_event)

        # Send the task prompt and wait for completion
        logger.info("📤 Sending task to Copilot agent...")
        logger.debug("Task content: %s", task)
        response = await session.send_and_wait(task, timeout=float(timeout))

        # If send_and_wait returned a full response, use it
        if response and response.data and response.data.content:
            logger.info("✅ Received response from send_and_wait with %d chars", len(response.data.content))
            logger.info("Response content: %s", response.data.content)
            return response.data.content

        # Otherwise wait for the collected events
        if not collected_text:
            try:
                await asyncio.wait_for(done_event.wait(), timeout=float(timeout))
            except asyncio.TimeoutError:
                logger.warning("⏱️  Timed out waiting for session idle after %ds", timeout)

        await session.disconnect()

        if collected_text:
            return collected_text[-1]  # Return the last assistant message

        return "Agent completed without producing a final message."

    def _build_system_message(self) -> str:
        """Compose the system message from mount info and tool instructions."""
        parts = []

        if self.folder_to_mount:
            parts.append(
                f"The working directory is mounted at {self.folder_to_mount.sandbox_path}. "
                f"You can access files using paths relative to or absolute from that directory."
            )

        for tool in self.additional_tools:
            if tool.usage_instructions_to_llm:
                parts.append(tool.usage_instructions_to_llm)

        return "\n\n".join(parts)

    # ──────────────────────────────────────────────────────────────────
    # Private — SDK hooks for tool-use logging
    # ──────────────────────────────────────────────────────────────────

    async def _on_pre_tool_use(self, input_data, invocation):
        """Hook called before each tool execution — log the call."""
        tool_name = input_data.get("toolName", "unknown")
        tool_args = input_data.get("toolArgs", {})
        logger.info("➡️  Tool call: %s — args: %s", tool_name, tool_args)
        return {"permissionDecision": "allow"}

    async def _on_post_tool_use(self, input_data, invocation):
        """Hook called after each tool execution — log the result."""
        tool_name = input_data.get("toolName", "unknown")
        result = input_data.get("toolResult", "")
        # Truncate long results for readable logs
        result_str = str(result)
        logger.debug("Tool '%s'\nexecution result: %s", tool_name, result_str)
        if len(result_str) > 500:
            result_str = result_str[:500] + "... (truncated)"
        logger.info("⬅️  Tool result: %s — output: %s", tool_name, result_str)
        return {}

    # ──────────────────────────────────────────────────────────────────
    # Private — mount helpers
    # ──────────────────────────────────────────────────────────────────

    def _mount_additional(self, mount: Mount):
        """Copy an additional folder into the running container."""
        if mount.mount_type != MountType.COPY:
            raise ValueError(
                "Only COPY mount type is supported for additional mounts"
            )
        if not self.environment.copy_to_container(
            mount.host_path_info.abs_path, mount.sandbox_path
        ):
            raise ValueError(
                f"Failed to copy additional mount: "
                f"{mount.host_path_info.abs_path} -> {mount.sandbox_path}"
            )
