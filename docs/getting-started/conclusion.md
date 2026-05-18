# Conclusion

You built a complete Microbots project — a sample C application with a deliberate error and a `LogAnalysisBot` run that produced a root-cause analysis without ever modifying your host filesystem.

## What Just Happened

`python3 log_analysis_bot.py` triggered the framework to:

1. **Create a Docker container** with `code/` mounted read-only via OverlayFS.
2. **Send the task** to the LLM with a `LogAnalysisBot` system prompt.
3. **Execute shell commands** inside the container (`ls`, `cat`, `nl`, …) as directed by the LLM.
4. **Return a `BotRunResult`** containing the root-cause analysis.

The host filesystem was never writable from the bot.

## Available Bots

| Bot | Permission | Description |
|-----|-----------|-------------|
| `ReadingBot` | Read-only | Reads files and extracts information. |
| `WritingBot` | Read-write | Reads and writes files to fix issues or generate code. |
| `BrowsingBot` | — | Browses the web to gather information. |
| `LogAnalysisBot` | Read-only | Analyzes logs for root-cause debugging. |
| `AgentBoss` | — | Orchestrates multiple bots for complex tasks. |

Explore the [API Reference](../api-reference/microbots/MicroBot.md) for each bot, or read the [Microbots : Safety First Agentic Workflow](../blog/microbots-safety-first-ai-agent.md) blog for the safety architecture.

