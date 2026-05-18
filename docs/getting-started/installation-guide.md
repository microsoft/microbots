# Microbot Installation

Install the `microbots` package and configure an LLM provider.

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

Microbots supports **Azure OpenAI**, **OpenAI**, **Anthropic**, and **Ollama**. This guide uses Azure OpenAI.

Create a `.env` file in the project root:

```env title=".env"
AZURE_OPENAI_ENDPOINT="https://your-resource-name.openai.azure.com"
AZURE_OPENAI_API_KEY="your-api-key-here"
AZURE_OPENAI_API_VERSION="2023-03-15-preview"
```

Replace `your-resource-name` and `your-api-key-here` with values from the Azure portal.

Continue with the [Sample Project Creation and First Run](create-your-first-microbot-project/index.md) guide.


