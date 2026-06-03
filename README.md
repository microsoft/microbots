# 🤖 Microbots

MicroBots is a lightweight, extensible AI agent for code comprehension and controlled file edits. It integrates cleanly into automation pipelines, mounting a target directory with explicit read-only or read/write modes so LLMs can safely inspect, refactor, or generate files with least-privilege access.

## 🚀 Quick Start

### Pre-requisites

- Docker
- AI LLM Provider and API Key

### Install

```bash
pip install microbots
```

### Example

```python
from microbots import WritingBot

myWritingBot = WritingBot(
    model="azure-openai/my-gpt5",
    folder_to_mount=str("myReactApp"),
)

data = myWritingBot.run(
    "Fix the build error and make sure the build is successful.",
    timeout_in_seconds=600,
)
print(data.results)
```

## 🤖 Available Bots

| Bot                | Description                                                            |
| ------------------ | ---------------------------------------------------------------------- |
| **ReadingBot**     | Reads files and extracts information based on instructions (read-only) |
| **WritingBot**     | Reads and writes files based on instructions (read/write)              |
| **BrowsingBot**    | Browses the web to gather information                                  |
| **LogAnalysisBot** | Analyzes logs for debugging                                            |
| **AgentBoss**      | Orchestrates multiple bots for complex tasks                           |

## ⚙️ How it works

![Overall Architecture](https://raw.githubusercontent.com/microsoft/microbots/main/docs/images/overall_architecture.png)

MicroBots creates a containerized environment and mounts the specified directory, restricting permissions to read-only or read/write based on the Bot used. This ensures AI agents operate within defined boundaries, enhancing security and control over code modifications while protecting the local environment.

## ✨ LLM Support

Microbots supports multiple LLM providers — pick whichever fits your stack:

| Provider string | Description                                                |
| --------------- | ---------------------------------------------------------- |
| `openai`        | OpenAI or Azure OpenAI via the OpenAI SDK (API key)        |
| `azure-openai`  | Azure OpenAI via the Azure SDK (API key or Azure AD token) |
| `anthropic`     | Anthropic models, direct or via Azure AI Foundry           |
| `ollama-local`  | Local models via [Ollama](https://ollama.com/)             |

Each provider has its own set of environment variables (endpoint, API key, deployment name, etc.). See the [Authentication guide](https://microsoft.github.io/microbots/advanced/authentication/) for the exact `.env` variables required for each provider and for Azure AD / managed identity setup.

## 📚 Links

- [GitHub Repository](https://github.com/microsoft/microbots)
- [Contributing Guide](https://github.com/microsoft/microbots/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/microsoft/microbots/blob/main/CODE_OF_CONDUCT.md)

---

## 🎯 Getting Started

Ready to build your first Microbot project? Follow the step-by-step onboarding guide:

➡️ **[Get Started with Microbots](https://microsoft.github.io/microbots/getting-started/prerequisites/)**

## Legal Notice

Trademarks: this project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow Microsoft's Trademark & Brand Guidelines. Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.
