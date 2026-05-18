# Microbots : Introduction

**Published on:** April 15, 2026 | **Author:** Siva Kannan

### Introduction

Microbots is a lightweight, extensible AI agent framework for code comprehension and controlled file edits. It is designed for developers who want to embed LLM-driven automation into their pipelines without exposing the host machine, source files, or credentials to the model.

## What Microbots Provides

Microbots mounts a target directory with explicit read-only or read/write permissions, so an LLM can inspect, refactor, or generate files with least-privilege access. Every command an agent executes runs inside a disposable Docker container, which means the host machine, files, and credentials are never directly exposed to the model.

## How It Works (At a Glance)

![Microbots overall architecture](../images/overall_architecture.png)

When a bot is invoked, Microbots provisions a containerized environment and mounts the specified directory with the permission level the bot requires (`READ_ONLY` or `READ_WRITE`). The LLM drives the bot in an iterative loop — issuing shell commands, reading their output, and reasoning over the results — but every command executes inside the container. This boundary is what keeps the AI agent operating within defined limits, protecting the local environment and giving you predictable, reviewable control over any code modifications.

## Safety Features

Microbots enforces safety through five reinforcing layers:

- **Container isolation** runs every command inside a disposable Docker container.
- **OverlayFS** provides copy-on-write filesystem protection, so changes never touch the underlying mount.
- **OS-level permission labels** (`READ_ONLY` and `READ_WRITE`) are enforced on every mounted folder.
- **Dangerous command detection** validates each command and blocks destructive patterns before execution.
- **Iteration budget management** caps sub-agent loops to prevent runaway costs.

The core philosophy is simple — assume the LLM will eventually produce a harmful command, and architect the system so that it does not matter when it does.

!!! tip "Want to understand the details?"
    Read the [Microbots : Safety First Agentic Workflow](../blog/microbots-safety-first-ai-agent.md) article for a deep dive into the architecture and all five layers of defense.

## Conclusion

In this article, you reviewed what Microbots is and the five-layer safety model that keeps every agent action contained. Next, set up the development environment by following the [Pre-requisites](../getting-started/prerequisites.md) guide to install Python and Docker, then continue with the [Microbot Installation](../getting-started/installation-guide.md) guide to install the package and configure your LLM provider.

