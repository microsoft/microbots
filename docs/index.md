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

| Bot | Description |
|-----|-------------|
| **ReadingBot** | Reads files and extracts information based on instructions (read-only) |
| **WritingBot** | Reads and writes files based on instructions (read/write) |
| **BrowsingBot** | Browses the web to gather information |
| **LogAnalysisBot** | Analyzes logs for debugging |
| **AgentBoss** | Orchestrates multiple bots for complex tasks |

## ⚙️ How it works

![Overall Architecture](images/overall_architecture.png)

MicroBots creates a containerized environment and mounts the specified directory, restricting permissions to read-only or read/write based on the Bot used. This ensures AI agents operate within defined boundaries, enhancing security and control over code modifications while protecting the local environment.

## ✨ LLM Support

Azure OpenAI Models — add environment variables in a `.env` file:

```env
AZURE_OPENAI_ENDPOINT=your-endpoint-url
AZURE_OPENAI_API_KEY=your-api-key
```

## 📚 Links

- [GitHub Repository](https://github.com/microsoft/minions)
- [Contributing Guide](https://github.com/microsoft/minions/blob/main/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/microsoft/minions/blob/main/CODE_OF_CONDUCT.md)
