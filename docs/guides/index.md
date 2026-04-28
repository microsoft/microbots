# Guides

Explore the Microbots guides to learn what the framework provides, how to install it, how to build your first project, and how to extend it with custom tools and advanced authentication. The guides are grouped by purpose so you can pick the right starting point for your task.

If you are new to Microbots, start with the [Microbots Introduction](introduction.md), then walk through the [Installation Guide](#installation-guide) and [Create Your First Microbot Project](#create-your-first-microbot-project) end-to-end.

## Microbots Introduction

Read the [Microbots Introduction](introduction.md) to learn what Microbots is and the five-layer safety model that keeps every agent action contained.

## Installation Guide

Install the prerequisites and set up the `microbots` package with your LLM provider. Read these articles in order.

| # | Guide | Description |
|---|-------|-------------|
| 1 | [Pre-requisites](getting-started/prerequisites.md) | Install Python 3.10+ and Docker, and verify both are available from your terminal. |
| 2 | [Microbot Installation](getting-started/installation-guide.md) | Create a project, set up a virtual environment, install the `microbots` package, and configure Azure OpenAI credentials. |

## Create Your First Microbot Project

Build a complete project that runs the `LogAnalysisBot` against a deliberately broken TypeScript build log. Read these articles in order after finishing the Getting Started section.

| # | Guide | Description |
|---|-------|-------------|
| 1 | [Sample Project Creation and First Run](create-your-first-microbot-project/sample-project-and-first-run.md) | Create a sample TypeScript project with a deliberate syntax error and capture the compiler output in `build.log`. |
| 2 | [LogAnalysisBot](create-your-first-microbot-project/log-analysis-bot.md) | Write the Python script that instantiates a `LogAnalysisBot` and points it at the build log. |
| 3 | [Output and Log Parsing](create-your-first-microbot-project/output-and-log-parsing.md) | Run the bot, trace its reasoning through the logger output, and review the root-cause analysis. |
| 4 | [Conclusion](create-your-first-microbot-project/conclusion.md) | Recap what happened under the hood and survey the other bots available in the framework. |

## Bots

Reference guides for individual bot types beyond the ones used in the walkthrough.

| Guide | Description |
|-------|-------------|
| [CopilotBot](bots/copilot-bot.md) | Use `CopilotBot` for AI-assisted coding workflows. |

## Tools

Extend a bot's capabilities with your own tools.

| Guide | Description |
|-------|-------------|
| [Custom Tool Integration Walkthrough](tools/tesseract_ocr_tool_use.md) | Build and integrate a custom tool (Tesseract OCR) into a Microbots workflow. |

## Advanced

Deeper configuration topics for production deployments.

| Guide | Description |
|-------|-------------|
| [Authentication](advanced/authentication.md) | Configure Azure AD tokens, managed identity, and service principals. |

## Contributing to the Docs

Before authoring or editing documentation, read the [Technical Writing Guidelines](technical-writing-guidelines.md) — they define the style, structure, formatting, and terminology conventions used across every Microbots article.
