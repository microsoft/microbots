# Microbot Installation

### Introduction

With Python and Docker in place, the next task is to install the `microbots` package into an isolated Python environment and configure the LLM provider that the bots will use. Isolating dependencies in a virtual environment prevents version conflicts with other Python projects on your machine, and storing credentials in a `.env` file keeps API keys out of source control.

In this guide, you will create a project directory, set up a Python virtual environment, install the `microbots` package, and configure **Azure OpenAI** as the LLM provider through a `.env` file. By the end, your project will be ready to run its first bot.

## Prerequisites

To complete this guide, you will need:

- **Python 3.10 or later, but below 3.13** installed on your machine. See the [Pre-requisites](prerequisites.md#step-1-installing-python) guide.
- **Docker** installed and running. See the [Pre-requisites](prerequisites.md#step-2-installing-docker) guide.
- An **Azure OpenAI** resource with an API key, endpoint URL, and a deployed model. See the [Azure OpenAI documentation](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource) for setup instructions.

!!! warning "Python 3.13 is not supported"
    Some of the `microbots` dependencies do not yet support Python 3.13. Use a Python version that is **at least 3.10 and below 3.13** (for example, 3.10, 3.11, or 3.12). You can check your version with `python --version`.

## Step 1 — Setting Up the Project Directory

In this step, you will create a project folder and a Python virtual environment that isolates the `microbots` package and its dependencies from your system Python installation.

Create a project folder for your bot and navigate into it:

```bash title="Terminal"
mkdir microbots-introduction
cd microbots-introduction
```

The `mkdir` command creates a new directory named `microbots-introduction`, and `cd` makes it your working directory.

Next, create a Python virtual environment inside the project folder:

```bash title="Terminal"
python -m venv .venv
```

The `-m venv` flag tells Python to run the built-in `venv` module, which creates an isolated environment in the `.venv` directory. Any packages installed while this environment is active will be scoped to this project only.

Activate the virtual environment so subsequent `pip` commands install packages into it:

```bash title="Terminal"
source .venv/bin/activate
```

When activation succeeds, your shell prompt will be prefixed with `(.venv)`.

Finally, install the `microbots` package from PyPI:

```bash title="Terminal"
pip install microbots
```

This downloads `microbots` and its dependencies into the active virtual environment.

You have now created a project folder and installed the `microbots` package into an isolated environment. In the next step, you will configure the LLM provider credentials.

## Step 2 — Configuring the LLM Provider

In this step, you will configure the credentials Microbots uses to authenticate with an LLM. Microbots currently supports **Azure OpenAI**, **Anthropic**, and **Ollama** as LLM providers. This guide uses **Azure OpenAI**.

You will need three values from your Azure OpenAI resource:

- An **API key** (`OPEN_AI_KEY`)
- An **endpoint URL** (`OPEN_AI_END_POINT`)
- A **deployed model name**

Create a file named `.env` in the root of your project and add the following content:

```env title=".env"
OPEN_AI_END_POINT="https://your-resource-name.openai.azure.com"
OPEN_AI_KEY="your-api-key-here"
OPEN_AI_API_VERSION="2023-03-15-preview"
```

Replace `your-resource-name` with the name of your Azure OpenAI resource and `your-api-key-here` with the key from the Azure portal. The `OPEN_AI_API_VERSION` value pins the Azure OpenAI REST API version that the framework uses; keep the value shown unless your resource requires a different version.

!!! note
    For advanced authentication options (Azure AD tokens, managed identity, service principals), see the [Authentication Guide](../advanced/authentication.md).

## Conclusion

In this guide, you set up an isolated Python virtual environment, installed the `microbots` package, and configured the Azure OpenAI credentials your bots will use. Your project is now ready for its first bot run. Continue with the [Sample Project Creation and First Run](../create-your-first-microbot-project/sample-project-and-first-run.md) guide to create a sample TypeScript project and execute the `LogAnalysisBot` against it.

