# Authentication

Microbots supports multiple LLM providers, each with their own authentication method.

## Providers Overview

| Provider string | Description | SDK | Authentication |
|---|---|---|---|
| `openai` | OpenAI or Azure OpenAI via OpenAI SDK | OpenAI SDK | API key |
| `azure-openai` | Azure OpenAI via Azure SDK | AzureOpenAI SDK | API key or Azure AD token |
| `anthropic` | Anthropic models | Anthropic SDK | API key or Azure AD token (Foundry) |
| `ollama-local` | Local models via Ollama | — | None (local) |

---

## 1. OpenAI (Direct)

Uses the **OpenAI SDK** with an API key. This works for both:
- **OpenAI directly** (api.openai.com)
- **Azure OpenAI via OpenAI SDK compatibility** (Azure endpoint + API key)

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_ENDPOINT="https://api.openai.com/v1"  # or your Azure endpoint
```

For Azure-hosted models using the OpenAI SDK (as shown in Azure Foundry portal):
```bash
export OPENAI_API_KEY="your-azure-api-key"
export OPENAI_ENDPOINT="https://your-resource.openai.azure.com/openai/v1/"
```

Usage:
```python
from microbots.MicroBot import MicroBot

bot = MicroBot(model="openai/gpt-5")
```

> **When to use this:** Use the `openai` provider when you have an API key and want to use the OpenAI SDK — whether pointing at OpenAI directly or at an Azure OpenAI endpoint that supports the OpenAI SDK.

---

## 2. Azure OpenAI (Azure SDK)

Uses the **AzureOpenAI SDK**. Use this provider when you need **Azure AD token authentication** or prefer the Azure-specific SDK.

### API Key Authentication (Default)

```bash
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com"
export AZURE_OPENAI_API_VERSION="2025-03-01-preview"
export AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment"
```

> **Note:** The Responses API requires `api-version` `2025-03-01-preview` or later. Earlier versions will return a `400 BadRequest` error.

Usage:
```python
from microbots.MicroBot import MicroBot

bot = MicroBot(model="azure-openai/your-deployment")
```

### Azure AD Token Authentication

For environments that require Azure AD authentication (no static API keys), Microbots can automatically obtain and refresh tokens using `azure-identity`.

`azure-identity` is an **optional dependency**. Install it with:

```bash
pip install microbots[azure_ad]
```

#### Option A: Environment Variable Opt-In

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
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com"
export AZURE_OPENAI_API_VERSION="2024-02-01"
export AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment"
```

> **Note:** `AZURE_AUTH_METHOD=azure_ad` only auto-creates a token provider for the `azure-openai` provider (using the `https://cognitiveservices.azure.com/.default` scope). For `anthropic` (Azure AI Foundry), the required scope is different and cannot be inferred automatically. You must pass `token_provider` explicitly — see **Option B** below.

#### Option B: Pass a Token Provider Programmatically

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

---

## 3. Anthropic

```bash
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_END_POINT="https://your-endpoint"
export ANTHROPIC_DEPLOYMENT_NAME="your-deployment"
```

Usage:
```python
from microbots.MicroBot import MicroBot

bot = MicroBot(model="anthropic/your-deployment")
```

For Anthropic on Azure AI Foundry, pass a `token_provider` explicitly (see Option B above with the appropriate Foundry scope).

---

## How Token Refresh Works

- `get_bearer_token_provider` returns a `Callable[[], str]` backed by `BearerTokenCredentialPolicy`.
- The token is cached and **proactively refreshed** before expiry — no manual refresh needed.
- Both `AzureOpenAI` and `AnthropicFoundry` SDKs call the provider **before every request**, so the token is always fresh.
- Tasks are **never interrupted** by token expiration.

## How the Provider Is Selected

| `token_provider` present | LLM provider | SDK client used |
|---|---|---|
| Yes | `azure-openai` | `AzureOpenAI(azure_ad_token_provider=...)` |
| No | `azure-openai` | `AzureOpenAI(api_key=...)` |
| — | `openai` | `OpenAI(base_url=..., api_key=...)` |
| Yes | `anthropic` | `AnthropicFoundry(azure_ad_token_provider=...)` |
| No | `anthropic` | `Anthropic(api_key=...)` |

`ollama-local` does not use token authentication.

## Notes

- A `ValueError` is raised at bot creation time if neither an API key nor a token provider is configured. This surfaces misconfigurations early rather than failing on the first API call.
- The browser tool runs inside Docker. When `AZURE_AUTH_METHOD=azure_ad` is set (or a `token_provider` is passed to `BrowsingBot`), `BrowsingBot.run()` calls the token provider, gets a fresh token, and injects it as `AZURE_OPENAI_AD_TOKEN` into the container. `browser.py` inside Docker reads this env var and passes it as `azure_ad_token` to `ChatAzureOpenAI`. The token is valid for ~1 hour, which is sufficient for typical browser tasks. `AZURE_OPENAI_API_KEY` is not required when using Azure AD auth.
