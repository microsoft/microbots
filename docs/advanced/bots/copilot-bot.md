# CopilotBot

CopilotBot is a Microbots agent that delegates the entire agent loop to the **GitHub Copilot runtime**. Unlike other Microbots bots (ReadingBot, WritingBot, etc.) where Microbots manages the LLM ↔ tool loop, CopilotBot lets the Copilot runtime handle planning, tool invocation, file edits, shell commands, and multi-turn reasoning — all within a secure Docker sandbox.

## Prerequisites

- **Docker** — a running Docker daemon
- **Python 3.10+**
- **One of the following** for authentication:
    - A GitHub Copilot subscription (for native Copilot auth), **or**
    - API credentials for any OpenAI-compatible, Azure OpenAI, or Anthropic endpoint (BYOK — no Copilot subscription needed)

## Installation

```bash
pip install microbots[ghcp]
```

This installs the `github-copilot-sdk` package alongside Microbots.

!!! note
    You do **not** need to install `copilot-cli` on your host machine. Microbots automatically installs and runs it inside the Docker container during initialization.

## Quick Start

```python
from microbots.bot.CopilotBot import CopilotBot

bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/your/project",
    github_token="ghp_your_github_token",
)

result = bot.run("Fix the failing unit tests and make sure all tests pass.")

print(result.status)  # True if successful
print(result.result)  # The agent's final response
print(result.error)   # Error message if status is False

bot.stop()
```

## Authentication Methods

CopilotBot supports multiple authentication methods. The first two require a GitHub Copilot subscription; the BYOK methods do not.

### 1. GitHub Token (Native Copilot Auth)

Pass a GitHub token directly or let Microbots discover it from the environment.

```python
# Option A: Pass explicitly
bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    github_token="ghp_your_token",
)

# Option B: Set environment variable (auto-discovered)
# export GITHUB_TOKEN="ghp_your_token"
# — or —
# export COPILOT_GITHUB_TOKEN="ghp_your_token"
# — or —
# export GH_TOKEN="ghp_your_token"

bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
)
```

If no token is provided and no environment variable is set, Microbots will attempt to retrieve a token from a local GitHub Copilot login (e.g. via `gh copilot`).

**Token discovery order:** explicit `github_token` → `COPILOT_GITHUB_TOKEN` → `GITHUB_TOKEN` → `GH_TOKEN` → local Copilot login.

!!! note
    The local Copilot login fallback requires `copilot-cli` to be installed on your **host** machine and a valid login session in your home directory (e.g. via `copilot login`). If `copilot-cli` is not installed or no login is found, this step is skipped.

### 2. BYOK — API Key (No Copilot Subscription Required)

Use your own API key and endpoint. This works with any OpenAI-compatible API, Anthropic, or Azure OpenAI — no GitHub Copilot subscription needed.

#### OpenAI

```python
bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    api_key="sk-your-openai-key",
    base_url="https://api.openai.com/v1",
    provider_type="openai",      # default, can be omitted
)
```

#### Anthropic

```python
bot = CopilotBot(
    model="claude-sonnet-4.5",
    folder_to_mount="/path/to/project",
    api_key="sk-ant-your-key",
    base_url="https://api.anthropic.com",
    provider_type="anthropic",
)
```

#### Azure OpenAI

```python
bot = CopilotBot(
    model="my-gpt4-deployment",
    folder_to_mount="/path/to/project",
    api_key="your-azure-api-key",
    base_url="https://your-resource.openai.azure.com",
    provider_type="azure",
    azure_api_version="2024-10-21",
)
```

#### Using `wire_api` for newer models

For models that use the Responses API (e.g. GPT-5 series), set `wire_api="responses"`:

```python
bot = CopilotBot(
    model="gpt-5",
    folder_to_mount="/path/to/project",
    api_key="sk-your-key",
    base_url="https://api.openai.com/v1",
    wire_api="responses",
)
```

### 3. BYOK — Bearer Token

If your provider uses bearer token authentication instead of an API key:

```python
bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    bearer_token="your-bearer-token",
    base_url="https://your-endpoint.com/v1",
)
```

!!! note
    When both `api_key` and `bearer_token` are provided, `bearer_token` takes precedence.

### 4. BYOK — Token Provider (e.g. Azure AD)

For environments that use dynamic token authentication (such as Azure AD managed identity), pass a callable that returns a fresh token:

```python
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()

def get_token():
    return credential.get_token("https://cognitiveservices.azure.com/.default").token

bot = CopilotBot(
    model="my-gpt4-deployment",
    folder_to_mount="/path/to/project",
    base_url="https://your-resource.openai.azure.com",
    provider_type="azure",
    azure_api_version="2024-10-21",
    token_provider=get_token,
)
```

The `token_provider` must be a callable that returns a non-empty string. It is called once at initialization time.

### 5. BYOK — Environment Variables

Configure BYOK entirely through environment variables without changing any code:

```bash
export COPILOT_BYOK_BASE_URL="https://api.openai.com/v1"
export COPILOT_BYOK_API_KEY="sk-your-key"
export COPILOT_BYOK_PROVIDER_TYPE="openai"          # optional, defaults to "openai"
export COPILOT_BYOK_MODEL="gpt-4.1"                 # optional, overrides the model param
export COPILOT_BYOK_WIRE_API="completions"           # optional
export COPILOT_BYOK_AZURE_API_VERSION="2024-10-21"   # optional, for Azure only
```

Then create the bot without any auth parameters:

```python
bot = CopilotBot(
    folder_to_mount="/path/to/project",
)
```

You can also use `COPILOT_BYOK_BEARER_TOKEN` instead of `COPILOT_BYOK_API_KEY` for bearer-token authentication.

## Authentication Priority

When multiple auth methods are configured simultaneously, CopilotBot resolves them in this order:

| Priority | Method | Condition |
|----------|--------|-----------|
| 1 | Explicit API key / bearer token | `api_key` or `bearer_token` parameter is set |
| 2 | Environment variables | `COPILOT_BYOK_BASE_URL` + `COPILOT_BYOK_API_KEY` or `COPILOT_BYOK_BEARER_TOKEN` |
| 3 | Token provider | `token_provider` parameter is set |
| 4 | Native GitHub Copilot | `github_token` or `GITHUB_TOKEN` / `COPILOT_GITHUB_TOKEN` / `GH_TOKEN` env vars |

## Parameters

### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | `"gpt-4.1"` | Model name (e.g. `"gpt-4.1"`, `"claude-sonnet-4.5"`). No provider prefix needed. |
| `folder_to_mount` | `str` | `None` | Absolute path to the folder to mount into the sandbox. |
| `permission` | `PermissionLabels` | `READ_WRITE` | Mount permission — `READ_ONLY` or `READ_WRITE`. |
| `environment` | `LocalDockerEnvironment` | `None` | Pre-created Docker environment. Auto-created if not provided. |
| `additional_tools` | `list[ToolAbstract]` | `[]` | Extra tools to install in the sandbox. |
| `github_token` | `str` | `None` | GitHub token for native Copilot auth. |
| `api_key` | `str` | `None` | API key for BYOK. |
| `bearer_token` | `str` | `None` | Bearer token for BYOK. |
| `base_url` | `str` | `None` | API endpoint URL for BYOK. |
| `provider_type` | `str` | `"openai"` | BYOK provider: `"openai"`, `"azure"`, or `"anthropic"`. |
| `wire_api` | `str` | `None` | API format: `"completions"` or `"responses"`. |
| `azure_api_version` | `str` | `None` | Azure API version (for `provider_type="azure"` only). |
| `token_provider` | `Callable[[], str]` | `None` | Callable returning a bearer token string. |

### `run()` method

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | `str` | *(required)* | Natural-language description of the task. |
| `additional_mounts` | `list[Mount]` | `None` | Extra folders to copy into the container. |
| `timeout_in_seconds` | `int` | `600` | Maximum wall-clock time for the agent run. |
| `streaming` | `bool` | `False` | Enable streaming delta events (logged at DEBUG level). |

### Return value — `BotRunResult`

| Field | Type | Description |
|-------|------|-------------|
| `status` | `bool` | `True` if the agent completed successfully. |
| `result` | `str` or `None` | The agent's final response text. |
| `error` | `str` or `None` | Error description if `status` is `False`. |

## Examples

### Read-only code analysis

```python
from microbots.bot.CopilotBot import CopilotBot
from microbots.constants import PermissionLabels

bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    permission=PermissionLabels.READ_ONLY,
    github_token="ghp_your_token",
)

result = bot.run("Analyze the codebase and list all public API endpoints.")
print(result.result)
bot.stop()
```

### Fix a bug with BYOK (OpenAI)

```python
from microbots.bot.CopilotBot import CopilotBot

bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    api_key="sk-your-openai-key",
    base_url="https://api.openai.com/v1",
)

result = bot.run(
    "The login form crashes when email contains a '+'. Fix the validation logic.",
    timeout_in_seconds=300,
)
print(result.result)
bot.stop()
```

### Using additional tools

```python
from microbots.bot.CopilotBot import CopilotBot
from microbots.tools.internal_tool import InternalTool

my_tool = InternalTool(tool_definition_path="path/to/tool.yaml")

bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    github_token="ghp_your_token",
    additional_tools=[my_tool],
)

result = bot.run("Use the custom tool to lint and then fix all issues.")
bot.stop()
```

!!! warning
    `ExternalTool` is **not supported** with CopilotBot. Only tools that run inside the Docker container (internal tools) can be used.

### Mounting additional folders at runtime

```python
from microbots.bot.CopilotBot import CopilotBot
from microbots.extras.mount import Mount

bot = CopilotBot(
    model="gpt-4.1",
    folder_to_mount="/path/to/project",
    github_token="ghp_your_token",
)

extra = Mount("/path/to/test-data", "/workdir/test-data", "READ_ONLY")
result = bot.run(
    "Run the integration tests using the data in /workdir/test-data.",
    additional_mounts=[extra],
)
bot.stop()
```

## Cleanup

Always call `bot.stop()` when you are done. This tears down the SDK client, the CLI server, and the Docker container:

```python
bot.stop()
```

`stop()` is idempotent — calling it multiple times is safe. It is also called automatically when the object is garbage-collected, but explicit cleanup is recommended.
