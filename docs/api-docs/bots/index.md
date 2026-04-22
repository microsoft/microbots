# Bots

This section covers the different types of bots that can be built with Microbots, along with detailed guides and examples for each type.

All bots extend the core [`MicroBot`](../components/bot.md) class with specialized system prompts, permissions, and tools.

| Bot | Purpose | Access Level |
|-----|---------|-------------|
| [LogAnalysisBot](log-analysis-bot.md) | Analyze log files and identify root causes | Read-only |
| ReadingBot | Code comprehension and analysis | Read-only |
| WritingBot | Controlled file edits | Read-write (restricted commands) |
| BrowsingBot | Web search and browsing | N/A |
| AgentBoss | Task decomposition and delegation | Read-write |
| CopilotBot | GitHub Copilot SDK wrapper | Configurable |

!!! note "Auto-generated API references"
    The API references on these pages are **auto-generated from source code docstrings**. When the source code changes, the documentation updates automatically on the next build.
