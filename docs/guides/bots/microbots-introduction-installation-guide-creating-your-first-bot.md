# Microbots : Introduction, Installation Guide and Creating Your First MicroBot

**Published on:** April 15, 2026 | **Author:** Siva Kannan

!!! warning "External Links Disclaimer"
    This document contains links to external documentation that may change or be removed over time. All external references were verified at the time of writing and are only considered valid as of the publication date.

## Introduction

Microbots is a lightweight, extensible AI agent framework for code comprehension and controlled file edits. It integrates cleanly into automation pipelines, mounting a target directory with explicit read-only or read/write permissions so LLMs can safely inspect, refactor, or generate files with least-privilege access. Every command an agent executes runs inside a disposable Docker container — your host machine, files, and credentials are never exposed.

## Safety Features

Microbots enforces safety through five reinforcing layers: **container isolation** that runs every command in a disposable Docker container, **OverlayFS** for copy-on-write filesystem protection, **OS-level permission labels** (`READ_ONLY` / `READ_WRITE`) on every mounted folder, a **dangerous command detection** validator that blocks destructive patterns before execution, and **iteration budget management** that prevents runaway costs from sub-agents. The core philosophy is simple — assume the LLM will eventually produce a harmful command, and architect the system so that it does not matter when it does.

!!! tip "Want to understand the details?"
    Read the [Microbots : Safety First Agentic Workflow](../../blog/microbots-safety-first-ai-agent.md) article for a deep dive into the architecture and all five layers of defense.

## Pre-requisites

### Python

Microbots requires **Python 3.10 or later**.

**Install Python:**

- **Windows:** Download the latest installer from [python.org](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"**.
- **Linux:** Python is often pre-installed. If not, install it using your package manager:

    ```bash title="Terminal"
    # Ubuntu / Debian
    sudo apt update && sudo apt install python3 python3-pip python3-venv

    # Fedora
    sudo dnf install python3 python3-pip
    ```

After installation, verify Python is available:

```bash title="Terminal"
python --version   # or python3 --version on Linux
pip --version      # or pip3 --version on Linux
```

You should see a version **3.10 or higher**. If both commands succeed, Python is ready.

### Docker

Microbots runs all agent commands inside Docker containers, so Docker must be installed and running on your machine.

**Install Docker Desktop:**

- **Windows / macOS:** Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
- **Linux:** Follow the official [Docker Engine installation guide](https://docs.docker.com/engine/install/) for your distribution.

After installation, verify Docker is running:

```bash title="Terminal"
docker --version
docker run hello-world
```

If both commands succeed, Docker is ready.


## Creating Your First MicroBot


### Step 1 : Set up your project and install Microbots

Create a project folder for your bot and navigate into it:

```bash title="Terminal"
mkdir microbots-introduction
cd microbots-introduction
```

Create a Python virtual environment and install the `microbots` package:

```bash title="Terminal"
python -m venv .venv 
```

Then activate the virtual environment and install Microbots:
```bash title="Terminal"
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

And install Microbots:
```bash title="Terminal"
pip install microbots
```

### Step 2 Set up the llm provider details in the project



Microbots currently supports **Azure OpenAI**, **Anthropic**, and **Ollama** as LLM providers. In this guide, we will use **Azure OpenAI** as the provider.

You will need an **API Key** (`OPEN_AI_KEY`), an **Endpoint URL** (`OPEN_AI_END_POINT`), and a **deployed model name**.

Create a `.env` file in the root of your application with:

```env title=".env"
OPEN_AI_END_POINT=https://your-resource-name.openai.azure.com
OPEN_AI_KEY=your-api-key-here
OPEN_AI_API_VERSION=2023-03-15-preview
```

!!! note
    For advanced authentication options (Azure AD tokens, managed identity, service principals), see the [Authentication Guide](../advanced/authentication.md).

### Step 3: Prepare a sample project


Now create a code folder with a simple TypeScript file that has a deliberate syntax error, and a build log that captures the compiler errors when trying to compile it.

```bash title="Terminal"
mkdir code
```

Create `code/app.ts` with a deliberate syntax error:

```typescript title="code/app.ts" linenums="1"
--8<-- "docs/examples/microbots_introduction/code/app.ts"
```

The function `add` on line 8 has a malformed type annotation (`b: number: number` instead of `b: number): number`). Run the TypeScript compiler to generate the build log:

```bash title="Terminal"
cd code
tsc app.ts > build.log 2>&1
cd ..
```

This produces the following build log:

```log title="code/build.log"
app.ts(8,34): error TS1005: ',' expected.
app.ts(8,43): error TS1005: ',' expected.
app.ts(9,12): error TS1005: ':' expected.
app.ts(9,14): error TS1005: ',' expected.
app.ts(10,1): error TS1128: Declaration or statement expected.
```

Your folder structure should look like:

```
microbots-introduction/
├── .venv
├── .env
├── log_analysis_bot.py
└── code/
    ├── app.ts
    ├── app.js
    └── build.log
```

### Step 4: Analyze logs with a LogAnalysisBot

The `LogAnalysisBot` mounts the target folder as **read-only** and analyzes log files to identify the root cause of failures.

```python title="log_analysis_bot.py" linenums="1"
--8<-- "docs/examples/microbots_introduction/log_analysis_bot.py"
```

<details markdown="1">
<summary><strong>Code walkthrough — click to expand</strong></summary>

- **Lines 1–8:**
    ```python
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    ```
    Sets up logging and loads environment variables (your Azure OpenAI credentials) from the `.env` file using `dotenv`.

- **Line 10:**
    ```python
    from microbots import LogAnalysisBot
    ```
    Imports `LogAnalysisBot` from the `microbots` package.

- **Lines 12–15:**
    ```python
    my_bot = LogAnalysisBot(
        model="azure-openai/gpt-5-swe-agent",
        folder_to_mount="code",
    )
    ```
    Creates a `LogAnalysisBot` instance. Here's what each argument does:

    | Argument | Type | Required | Description |
    |----------|------|----------|-------------|
    | `model` | `str` | Yes | The LLM to use, in the format `<provider>/<model_name>`. Supported providers include `azure-openai`, `anthropic`, and `ollama`. |
    | `folder_to_mount` | `str` | Yes | Path to the local folder the bot can access. For `LogAnalysisBot`, this is mounted as **read-only** inside the Docker container so the bot can read source files but never modify them. |
    | `environment` | `any` | No | A custom execution environment. Defaults to a `LocalDockerEnvironment` if not provided. |
    | `additional_tools` | `list[ToolAbstract]` | No | Extra tools to install in the bot's environment, extending its capabilities beyond the built-in command execution. |
    | `token_provider` | `any` | No | A custom token provider for authentication (e.g., Azure AD tokens or managed identity). See the [Authentication Guide](../advanced/authentication.md). |

- **Lines 17–20:**
    ```python
    result = my_bot.run(
        file_name="code/build.log",
        timeout_in_seconds=600,
    )
    ```
    Calls `my_bot.run()`, pointing the bot at `code/build.log` with a 10-minute timeout. The bot spins up a container, reads the log, correlates errors with source files, and returns its analysis.

    The `run()` method accepts the following arguments:

    | Argument | Type | Default | Description |
    |----------|------|---------|-------------|
    | `file_name` | `str` | — | **(Required)** Path to the log file to analyze. The file is copied into the container as read-only. |
    | `max_iterations` | `int` | `20` | Maximum number of LLM reasoning/command loops before the bot stops. Each iteration is one round of the LLM issuing a command and receiving its output. |
    | `timeout_in_seconds` | `int` | `300` | Maximum wall-clock time (in seconds) for the entire run. If the bot exceeds this limit, it is terminated and returns with an error. |

    When `run()` is called, it:

    1. Copies the log file into the Docker container at a dedicated `/var/log/` path.
    2. Sends the task prompt (including the log file location) to the LLM.
    3. Enters an iterative loop where the LLM reads files, runs commands (e.g., `cat`, `grep`), and reasons about the output — up to `max_iterations` rounds.
    4. Returns a `BotRunResult` object once the LLM reaches a conclusion or a limit is hit.

- **Line 21:**
    ```python
    print(result.result)
    ```
    Prints the bot's root-cause analysis.

The `my_bot.run()` method returns a `BotRunResult` object with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `bool` | `True` if the bot completed successfully, `False` otherwise |
| `result` | `str \| None` | The bot's output — typically its analysis, explanation, or generated content |
| `error` | `str \| None` | Error message if the run failed, `None` on success |

</details>

Run it:

```bash title="Terminal"
python log_analysis_bot.py
```

The `LogAnalysisBot` will spin up a Docker container, mount the `code` folder as read-only, and use the LLM to analyze the log file and report the root cause.

If you're interested in seeing the full logger-enabled Microbots output — including environment setup, each LLM reasoning step, and container teardown — expand the section below:

<details markdown="1">
<summary><strong>Full logger-enabled output — click to expand</strong></summary>

Since we set `logging.basicConfig(level=logging.INFO)`, the full run produces detailed step-by-step output showing the bot's environment setup, each LLM reasoning iteration, and the final teardown:

```text title="Terminal output"
(.venv) $ python3 log_analysis_bot.py

INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗂️  Created working directory at /home/sikannan/MICROBOTS_WORKDIR_18da47d7
INFO:microbots.environment.local_docker.LocalDockerEnvironment:📦 Volume mapping: /mnt/c/Users/sikannan/codeBase/microbots-examples/code → /ro/code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🚀 Started container b4826a8d41b7 with image kavyasree261002/shell_server:latest on host port 35291
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🔒 Set up overlay mount for read-only directory at /workdir/code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:✅ Successfully copied /mnt/c/Users/sikannan/codeBase/microbots-examples/code/build.log to container:/var/log

INFO:httpx:HTTP Request: POST https://azlinux-chatbot-2025.openai.azure.com/openai/responses?api-version=2025-03-01-preview "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': False, 'thoughts': 'First, I need to see what log files exist in /var/log to determine which one to analyze.', 'command': 'ls -1 /var/log'}
INFO: MicroBot : ℹ️  TASK STARTED :
            Analyze the log file `/var/log`
        ...
INFO: MicroBot :-------------------- Step-1 --------------------
INFO: MicroBot : 💭  LLM thoughts: First, I need to see what log files exist in /var/log to determine which one to analyze.
INFO: MicroBot : ➡️  LLM tool call : "ls -1 /var/log"
INFO: MicroBot : ⬅️  Command output:
ShellCommunicator.log
alternatives.log
apt
btmp
build.log
dpkg.log
fontconfig.log
lastlog
wtmp
INFO:httpx:HTTP Request: POST https://azlinux-chatbot-2025.openai.azure.com/openai/responses?api-version=2025-03-01-preview "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': False, 'thoughts': "To identify failures, I'll start by checking build.log for errors. First, I'll see the line count to gauge its size.", 'command': 'wc -l /var/log/build.log'}
INFO: MicroBot :-------------------- Step-2 --------------------
INFO: MicroBot : 💭  LLM thoughts: To identify failures, I'll start by checking build.log for errors. First, I'll see the line count to gauge its size.
INFO: MicroBot : ➡️  LLM tool call : "wc -l /var/log/build.log"
INFO: MicroBot : ⬅️  Command output:
5 /var/log/build.log
INFO:httpx:HTTP Request: POST https://azlinux-chatbot-2025.openai.azure.com/openai/responses?api-version=2025-03-01-preview "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': False, 'thoughts': 'The build.log is small, so I can safely view it to check for errors.', 'command': 'cat /var/log/build.log'}
INFO: MicroBot :-------------------- Step-3 --------------------
INFO: MicroBot : 💭  LLM thoughts: The build.log is small, so I can safely view it to check for errors.
INFO: MicroBot : ➡️  LLM tool call : "cat /var/log/build.log"
INFO: MicroBot : ⬅️  Command output:
app.ts(8,34): error TS1005: ',' expected.
app.ts(8,43): error TS1005: ',' expected.
app.ts(9,12): error TS1005: ':' expected.
app.ts(9,14): error TS1005: ',' expected.
app.ts(10,1): error TS1128: Declaration or statement expected.
INFO:httpx:HTTP Request: POST https://azlinux-chatbot-2025.openai.azure.com/openai/responses?api-version=2025-03-01-preview "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': False, 'thoughts': "I'll inspect the code base to locate app.ts and review the relevant lines causing TypeScript syntax errors.", 'command': 'ls -1 //workdir/code'}
INFO: MicroBot :-------------------- Step-4 --------------------
INFO: MicroBot : 💭  LLM thoughts: I'll inspect the code base to locate app.ts and review the relevant lines causing TypeScript syntax errors.
INFO: MicroBot : ➡️  LLM tool call : "ls -1 //workdir/code"
INFO: MicroBot : ⬅️  Command output:
app.js
app.ts
build.log
INFO:httpx:HTTP Request: POST https://azlinux-chatbot-2025.openai.azure.com/openai/responses?api-version=2025-03-01-preview "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': False, 'thoughts': 'Open the TypeScript file to inspect the syntax around lines 8-10 where errors are reported.', 'command': "nl -ba //workdir/code/app.ts | sed -n '1,40p'"}
INFO: MicroBot :-------------------- Step-5 --------------------
INFO: MicroBot : 💭  LLM thoughts: Open the TypeScript file to inspect the syntax around lines 8-10 where errors are reported.
INFO: MicroBot : ➡️  LLM tool call : "nl -ba //workdir/code/app.ts | sed -n '1,40p'"
INFO: MicroBot : ⬅️  Command output:
     1  // app.ts — A simple greeting function with a syntax error
     2  function greet(name: string) {
     3      const message: string = `Hello, ${name}!`
     4      console.log(message)
     5  }
     6
     7  // Missing closing parenthesis on the type annotation
     8  function add(a: number, b: number: number {
     9      return a + b;
    10  }
    11
    12  greet("Microbots");
    13  console.log(add(2, 3));
INFO:httpx:HTTP Request: POST https://azlinux-chatbot-2025.openai.azure.com/openai/responses?api-version=2025-03-01-preview "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': True, 'thoughts': "Root cause identified from /var/log/build.log: TypeScript compilation fails due to a syntax error in //workdir/code/app.ts at line 8. The function declaration is malformed: `function add(a: number, b: number: number {` has an extra `: number` after `b` and is missing the closing parenthesis before the return type. This triggers TS1005 (',' expected) and subsequently TS1128 (Declaration or statement expected). Correct signature should be: `function add(a: number, b: number): number {`.", 'command': ''}
INFO: MicroBot : 💭  LLM final thoughts: Root cause identified from /var/log/build.log: TypeScript compilation fails due to a syntax error in //workdir/code/app.ts at line 8. The function declaration is malformed: `function add(a: number, b: number: number {` has an extra `: number` after `b` and is missing the closing parenthesis before the return type. This triggers TS1005 (',' expected) and subsequently TS1128 (Declaration or statement expected). Correct signature should be: `function add(a: number, b: number): number {`.
INFO: MicroBot :🔚 TASK COMPLETED :
            An...
Bot run completed. Result:---------------------------------------------------------------
Root cause identified from /var/log/build.log: TypeScript compilation fails due to a syntax error in //workdir/code/app.ts at line 8. The function declaration is malformed: `function add(a: number, b: number: number {` has an extra `: number` after `b` and is missing the closing parenthesis before the return type. This triggers TS1005 (',' expected) and subsequently TS1128 (Declaration or statement expected). Correct signature should be: `function add(a: number, b: number): number {`.
---------------------------------------------------------------------------------------
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🛠️  Tearing down overlay mount for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:✅  Unmounted overlay for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🛑  Removing overlay dirs at //workdir/code and /workdir/overlay/
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗑️  Removed overlay directories for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗑️  Removed working directory at /home/sikannan/MICROBOTS_WORKDIR_18da47d7
```

</details>

The output of `print(result.result)` will look something like:

```text title="Output"
Root cause identified from /var/log/build.log: TypeScript 
compilation fails due to a syntax error in //workdir/code/
app.ts at line 8. The function declaration is malformed:
 `function add(a: number, b: number: number {` 
 has an extra `: number` after `b` and is missing the closing 
 parenthesis before the return type. This triggers TS1005 
 (',' expected) and subsequently TS1128 (Declaration or 
 statement expected). Correct signature should be: 
 `function add(a: number, b: number): number {`.
 
```

The `LogAnalysisBot` read the `build.log`, correlated the compiler errors with the source code in `app.ts`, identified the malformed type annotation as the root cause, and provided a clear fix — all without any human intervention.

!!! tip "DevOps Integration"
    This pattern integrates naturally into CI/CD pipelines. Point the `LogAnalysisBot` at build logs, test reports, or deployment logs from tools like GitHub Actions, Azure DevOps, Jenkins, or GitLab CI — and get instant root-cause analysis delivered as part of your pipeline output.

### What just happened?

Behind the scenes, Microbots:

1. **Created a Docker container** with the `code` folder mounted using the appropriate permissions.
2. **Sent your task** to the LLM along with a system prompt tailored to the bot type.
3. **Executed commands** inside the container as directed by the LLM (e.g., `cat`, `grep`, `sed`).
4. **Returned the result** — the bot's analysis and root-cause report.

Your host filesystem was protected the entire time. The LogAnalysisBot physically could not write to your files — all within Docker's isolation boundary.

## Available Bots

Beyond the `LogAnalysisBot` used in this guide, Microbots provides several other bots tailored for different use cases — each with its own permission level to ensure least-privilege access.

| Bot | Permission | Description |
|-----|-----------|-------------|
| **ReadingBot** | Read-only | Reads files and extracts information based on instructions |
| **WritingBot** | Read-write | Reads and writes files to fix issues or generate code |
| **BrowsingBot** | — | Browses the web to gather information |
| **LogAnalysisBot** | Read-only | Analyzes logs for instant root-cause debugging |
| **AgentBoss** | — | Orchestrates multiple bots for complex multi-step tasks |