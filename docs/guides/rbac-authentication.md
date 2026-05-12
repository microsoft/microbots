# Understanding RBAC and Authentication in Microbots

Microbots supports both API Key and Azure AD authentication for LLM providers. This guide breaks down how each method works, what Azure RBAC is, and which one to use for your setup.

For setup instructions, see the [Authentication setup guide](../authentication.md).

---

## The Problem: AI Agents Need LLM Access

Every Microbots bot makes API calls to an LLM provider (Azure OpenAI, Anthropic, etc.). These APIs require authentication — they need to know *who* is calling and *whether they're allowed to*.

There are two fundamentally different approaches to this:

| Approach | Analogy |
|----------|---------|
| **API Key** | A physical key — anyone who has it can open the door |
| **Azure AD + RBAC** | An ID badge — the system verifies *who you are* and checks *what you're allowed to do* |

---

## What is RBAC?

**RBAC** (Role-Based Access Control) is Azure's authorization model. Instead of sharing a secret key, you:

1. **Create an identity** — a service principal, managed identity, or user account
2. **Assign a role** — e.g., `Cognitive Services OpenAI User`
3. **Scope it** — to a specific resource, resource group, or subscription

The identity can then access the resource *without any API key*. Azure verifies the identity and checks the role assignment on every request.

> **Microbots (your bot)** —*token*→ **Azure AD (verify who)** —*allow*→ **Azure OpenAI (LLM endpoint)**
>
> Azure AD performs an **RBAC Check**: Does this identity have the required role?

---

## Why Microbots Supports Both Methods

### API Key Authentication

**What it is:** A static string (like `sk-abc123...`) passed with every request.

**Advantages:**

- Zero setup — paste the key and go
- Works anywhere (local, CI, any cloud)
- No Azure AD infrastructure needed

**Disadvantages:**

- **No identity** — you can't tell *who* used the key
- **No audit trail** — no logs of which bot/user made which call
- **Manual rotation** — if leaked, you must regenerate and update everywhere
- **Oversharing** — the same key gives full access to anyone who has it
- **No granular permissions** — can't restrict to specific models or operations

**Best for:** Local development, quick prototyping, non-Azure environments.

---

### Azure AD + RBAC Authentication

**What it is:** The bot authenticates as an identity (service principal or managed identity), receives a short-lived token (~1 hour), and uses that token for API calls. Azure checks RBAC roles on every request.

**Advantages:**

- **No secrets to manage** — tokens are auto-generated
- **Auditable** — every call is logged with the identity that made it
- **Least privilege** — assign only the roles needed (e.g., read-only vs. full access)
- **Auto-rotation** — tokens expire and refresh automatically
- **Revocable** — disable the identity instantly; no key rotation needed
- **Conditional access** — can restrict by network, device, location

**Disadvantages:**

- Requires Azure AD setup (tenant, app registration or managed identity)
- More complex initial configuration
- Only works with Azure-hosted or Azure-federated services

**Best for:** Production deployments, CI/CD pipelines, enterprise environments, multi-team setups.

---

## Decision Guide

| Scenario | Recommended Method |
|----------|-------------------|
| Local development / trying things out | API Key |
| Shared team environment | Azure AD |
| CI/CD pipeline (GitHub Actions, Azure DevOps) | Azure AD (Managed Identity or Service Principal) |
| Running on Azure VM / Container Apps | Azure AD (Managed Identity) |
| Non-Azure cloud (AWS, GCP) | API Key |
| Compliance / audit requirements | Azure AD |
| Quick demo | API Key |

---

## How It Works in Microbots

### API Key Flow

```
1. You set OPEN_AI_KEY=sk-... in env
2. Bot starts → reads env var
3. Every LLM call includes the key in the header
4. Azure OpenAI validates the key → responds
```

### Azure AD Flow

```
1. You configure credentials (Service Principal, Managed Identity, or CLI)
2. Bot starts → calls DefaultAzureCredential → gets a token
3. Token is cached and proactively refreshed before expiry
4. Every LLM call includes the token in the header
5. Azure AD validates the token → checks RBAC → responds
```

The key difference: with Azure AD, the token **expires automatically** and is **refreshed transparently**. If the identity is revoked, the next token request fails — no leaked keys to worry about.

---

## RBAC Roles for Azure OpenAI

To use Azure AD auth with Azure OpenAI, the identity needs one of these roles:

| Role | Use with Microbots |
|------|-------------------|
| `Cognitive Services OpenAI User` | **Recommended.** Least-privilege role for running bots |
| `Cognitive Services OpenAI Contributor` | Use if you also need to manage deployments and fine-tuning |

For a full breakdown of what each role can and cannot do, see the [Azure OpenAI RBAC documentation](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/role-based-access-control#add-role-assignment-to-an-azure-openai-resource).

Assign via Azure CLI:

```bash
az role assignment create \
  --assignee <service-principal-id> \
  --role "Cognitive Services OpenAI User" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<resource>
```

---

## Security Comparison

| Concern | API Key | Azure AD + RBAC |
|---------|---------|----------------|
| Key leaked in logs/git | High risk — full access until rotated | N/A — no static key exists |
| Developer leaves team | Must rotate all shared keys | Revoke their identity — instant |
| Audit "who did what" | Impossible | Full Azure Monitor logs |
| Blast radius of compromise | All users of that key | Only the compromised identity |
| Token lifetime | Infinite (until manually rotated) | ~1 hour (auto-refreshed) |

---

## How Microbots Handles Tokens Internally

1. **Early validation** — If neither API key nor token provider is configured, a `ValueError` is raised at bot creation time (not on first API call)
2. **Proactive refresh** — `get_bearer_token_provider()` refreshes the token *before* it expires
3. **Per-request injection** — The SDK calls the token provider before every API request
4. **Docker isolation** — For BrowsingBot, a fresh token is injected into the container as an environment variable (marked sensitive)

---

## Next Steps

- **Set up API Key auth** → [Authentication Guide: API Key](../authentication.md#1-api-key-authentication-default)
- **Set up Azure AD auth** → [Authentication Guide: Azure AD](../authentication.md#2-azure-ad-token-authentication)
- **Understand the safety model** → [Safety-First Agentic Workflow](../blog/microbots-safety-first-ai-agent.md)
