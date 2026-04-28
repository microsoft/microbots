# Conclusion

### Introduction

You have now built a complete Microbots project: a sample TypeScript application with a deliberate error, a `LogAnalysisBot` script that points at the build log, and a successful run that produced a root-cause analysis. This article recaps what happened under the hood during that run and surveys the other bots the framework provides, so you can decide which one to reach for next.

## What Just Happened

When you executed `python3 log_analysis_bot.py`, the framework performed the following steps on your behalf:

1. **Created a Docker container** with the `code` folder mounted using the appropriate permissions (read-only, in this case).
2. **Sent your task** to the LLM along with a system prompt tailored to the `LogAnalysisBot` role.
3. **Executed commands** inside the container as directed by the LLM (for example, `ls`, `cat`, `nl`, and `sed`).
4. **Returned the result** as a `BotRunResult` containing the bot's analysis and root-cause report.

Your host filesystem was protected the entire time. The `LogAnalysisBot` physically could not write to your files — every command ran inside Docker's isolation boundary, on top of an OverlayFS read-only mount.

## Available Bots

Beyond the `LogAnalysisBot` used in this guide, Microbots provides several other bots tailored for different use cases — each with its own permission level to ensure least-privilege access:

| Bot | Permission | Description |
|-----|-----------|-------------|
| `ReadingBot` | Read-only | Reads files and extracts information based on instructions. |
| `WritingBot` | Read-write | Reads and writes files to fix issues or generate code. |
| `BrowsingBot` | — | Browses the web to gather information. |
| `LogAnalysisBot` | Read-only | Analyzes logs for instant root-cause debugging. |
| `AgentBoss` | — | Orchestrates multiple bots for complex multi-step tasks. |

## Conclusion

In this guide series, you installed Microbots, configured an Azure OpenAI provider, built a sample TypeScript project with a deliberate error, ran the `LogAnalysisBot` against the resulting build log, and reviewed how the framework isolates every command in Docker. To extend what you have built, explore the [API Reference](../../api-reference/microbots/MicroBot.md) for each bot listed above, or read the [Microbots : Safety First Agentic Workflow](../../blog/microbots-safety-first-ai-agent.md) blog for a deeper look at the safety architecture.
