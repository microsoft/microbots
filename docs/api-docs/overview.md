# API Documentation

This section provides comprehensive API references for Microbots, auto-generated from source code docstrings. When the source code changes, the documentation updates automatically on the next build.

## Components

The foundational building blocks of Microbots.

- **[Bot](components/bot.md)** — The core `MicroBot` class that powers all autonomous agents. Covers the base class, `BotRunResult`, `BotType`, and the agent execution loop.

## Bots

Specialized bot implementations, each tailored for a specific use case.

- **[LogAnalysisBot](bots/log-analysis-bot.md)** — Analyzes log files inside a sandboxed container and identifies root causes by cross-referencing with source code.
