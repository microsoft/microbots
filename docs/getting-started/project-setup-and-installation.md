# Project Setup and Microbots Installation

In this guide, you will set up a project folder, install the `microbots` package inside a virtual environment, and configure an LLM provider so your bot has a brain to think with.

## Step 1 — Setting Up the Project Directory

Create a project folder, activate a virtual environment, and install the `microbots` package:

```bash title="Terminal"
mkdir microbots-introduction
cd microbots-introduction
python3 -m venv .venv
source .venv/bin/activate
pip install microbots
```

When the venv is active, your shell prompt is prefixed with `(.venv)` as below:

```bash title="Terminal"
(.venv) user@host:~/microbots-introduction$
```

## Step 2 — Configuring the LLM Provider

Microbots supports **Azure OpenAI**, **OpenAI**, **Anthropic**, and **Ollama**. This guide uses Azure OpenAI — for the environment variables required by the other providers, see the [Authentication Setup](../advanced/authentication.md) guide.

Create a `.env` file in the project root:

```env title=".env"
AZURE_OPENAI_ENDPOINT="https://your-resource-name.openai.azure.com"
AZURE_OPENAI_API_KEY="your-api-key-here"
AZURE_OPENAI_API_VERSION="2025-03-01-preview"
```

Replace the placeholders with values from the Azure portal:

- **`AZURE_OPENAI_ENDPOINT`** — the endpoint URL of your Azure OpenAI resource.
- **`AZURE_OPENAI_API_KEY`** — a key from the resource's **Keys and Endpoint** page.
- **`AZURE_OPENAI_API_VERSION`** — the REST API version your deployment supports.

Your project is now set up with the `microbots` package installed and an LLM provider configured. Next, you'll create a sample project and run your first bot — continue with the [Sample Project Creation and First Run](create-your-first-microbot-project/index.md) guide.


