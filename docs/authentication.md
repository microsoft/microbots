# Authentication

Microbots supports two authentication methods for LLM providers:

## 1. API Key Authentication (Default)

Set the API key as an environment variable. This is the default and requires no additional setup.

```bash
# For Azure OpenAI
export OPEN_AI_KEY="your-api-key"
export OPEN_AI_END_POINT="https://your-endpoint.openai.azure.com"
export OPEN_AI_API_VERSION="2024-02-01"
export OPEN_AI_DEPLOYMENT_NAME="your-deployment"

# For Anthropic
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_END_POINT="https://your-endpoint"
export ANTHROPIC_DEPLOYMENT_NAME="your-deployment"
```

## 2. Azure AD Token Authentication

For environments that require Azure AD authentication (no static API keys), Microbots can automatically obtain and refresh tokens using `azure-identity`.

`azure-identity` is a **default dependency** — no extra install step is needed.

### Option A: Environment Variable Opt-In

Set `AZURE_AUTH_METHOD=azure_ad` and configure your credentials. Microbots will use `DefaultAzureCredential`, which automatically tries the following sources in order: environment variables, workload identity, managed identity, Azure CLI, and more.

**Service Principal:**
```bash
export AZURE_AUTH_METHOD=azure_ad
export AZURE_CLIENT_ID="your-client-id"
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_SECRET="your-client-secret"
```

**Managed Identity** (on Azure VMs, Container Apps, App Service, etc.):
```bash
export AZURE_AUTH_METHOD=azure_ad
# No other env vars needed — managed identity is detected automatically
```

**Azure CLI** (local development):
```bash
az login
export AZURE_AUTH_METHOD=azure_ad
```

Also set the relevant LLM endpoint env vars (no API key required):

```bash
# Azure OpenAI
export OPEN_AI_END_POINT="https://your-endpoint.openai.azure.com"
export OPEN_AI_API_VERSION="2024-02-01"
export OPEN_AI_DEPLOYMENT_NAME="your-deployment"

# Anthropic Foundry
export ANTHROPIC_END_POINT="https://your-foundry-endpoint"
export ANTHROPIC_DEPLOYMENT_NAME="your-deployment"
```

> **Note:** `AZURE_AUTH_METHOD=azure_ad` only auto-creates a token provider for the `azure-openai` provider (using the `https://cognitiveservices.azure.com/.default` scope). For `anthropic` (Azure AI Foundry), the required scope is different and cannot be inferred automatically. You must pass `token_provider` explicitly — see **Option B** below.

### Option B: Pass a Token Provider Programmatically

Pass any `Callable[[], str]` as `token_provider`. The recommended approach uses `get_bearer_token_provider` from `azure-identity`:

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from microbots.MicroBot import MicroBot

credential = DefaultAzureCredential()
token_provider = get_bearer_token_provider(
    credential, "https://cognitiveservices.azure.com/.default"
)

bot = MicroBot(
    model="azure-openai/your-deployment",
    token_provider=token_provider,
)
```

You can substitute any `azure-identity` credential class for `DefaultAzureCredential`:

```python
from azure.identity import ClientSecretCredential, get_bearer_token_provider

credential = ClientSecretCredential(
    tenant_id="your-tenant-id",
    client_id="your-client-id",
    client_secret="your-client-secret",
)
token_provider = get_bearer_token_provider(
    credential, "https://cognitiveservices.azure.com/.default"
)

bot = MicroBot(
    model="azure-openai/your-deployment",
    token_provider=token_provider,
)
```

### How Token Refresh Works

- `get_bearer_token_provider` returns a `Callable[[], str]` backed by `BearerTokenCredentialPolicy`.
- The token is cached and **proactively refreshed** before expiry — no manual refresh needed.
- Both `AzureOpenAI` and `AnthropicFoundry` SDKs call the provider **before every request**, so the token is always fresh.
- Tasks are **never interrupted** by token expiration.

### How the Provider Is Selected

| `token_provider` present | LLM provider | SDK client used |
|---|---|---|
| Yes | `azure-openai` | `AzureOpenAI(azure_ad_token_provider=...)` |
| No | `azure-openai` | `OpenAI(api_key=...)` |
| Yes | `anthropic` | `AnthropicFoundry(azure_ad_token_provider=...)` |
| No | `anthropic` | `Anthropic(api_key=...)` |

`OllamaLocal` (local models) does not use token authentication.

### Notes

- A `ValueError` is raised at bot creation time if neither an API key nor a token provider is configured. This surfaces misconfigurations early rather than failing on the first API call.
- The browser tool runs inside Docker. When `AZURE_AUTH_METHOD=azure_ad` is set (or a `token_provider` is passed to `BrowsingBot`), `BrowsingBot.run()` calls the token provider, gets a fresh token, and injects it as `AZURE_OPENAI_AD_TOKEN` into the container. `browser.py` inside Docker reads this env var and passes it as `azure_ad_token` to `ChatAzureOpenAI`. The token is valid for ~1 hour, which is sufficient for typical browser tasks. `AZURE_OPENAI_API_KEY` is not required when using Azure AD auth.
