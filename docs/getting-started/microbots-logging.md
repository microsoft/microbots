# Configure Logging in Microbots

Microbots uses standard Python logging, so you can enable logs directly in your bot script and inspect execution details during debugging.

## 1. Enable Logging in Your Script

At the **top of your bot script** (before importing `microbots` or creating a bot), add:

```python
import logging

logging.basicConfig(level=logging.INFO)  # change to logging.DEBUG for deeper diagnostics
```

That's it — Microbots picks up Python's root logger automatically, so the rest of your script stays unchanged.

`logging.basicConfig` accepts other parameters too — `format`, `datefmt`, `filename`, `filemode`, `handlers`, `stream`, and more — that let you customize message format, write logs to a file, or attach custom handlers. See the official Python reference for the full list: [`logging.basicConfig`](https://docs.python.org/3/library/logging.html#logging.basicConfig).

## 2. Two Levels of Microbots Logging

Microbots supports two practical logging levels:

| Level   | What it shows                                                                                | When to use                               |
| ------- | -------------------------------------------------------------------------------------------- | ----------------------------------------- |
| `INFO`  | The bot's steps, LLM thoughts, tool calls, and command outputs.                              | To follow **what the bot is doing**.      |
| `DEBUG` | `INFO` plus internals — Docker calls, container execution details, and raw LLM HTTP traffic. | To troubleshoot **why something failed**. |

## 3. What `INFO` Logging Shows

Excerpts below are from a real Microbots run, with host paths, container IDs, ports, and endpoint URLs replaced by placeholders like `<container-id>`, `<host-port>`, and `<your-endpoint>`.

The excerpts are grouped to match the phases of the [execution flow diagram](microbots-execution-flow.md#what-just-happened) you saw in the previous article — **SETUP**, **LOOP**, and **RESULT** — so each block of logs lines up with a specific part of the picture.

### SETUP — environment setup

Working directory creation, the host-to-container volume mapping, container startup, and the read-only overlay mount.

```log
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗂️  Created working directory at /home/user/MICROBOTS_WORKDIR_<id>
INFO:microbots.environment.local_docker.LocalDockerEnvironment:📦 Volume mapping: /home/user/microbots-introduction/code → /ro/code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🚀 Started container <container-id> with image microbots/shell_server:latest on host port <host-port>
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🔒 Set up overlay mount for read-only directory at /workdir/code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:✅ Successfully copied /home/user/microbots-introduction/code/build.log to container:/var/log
```

### LOOP — task lifecycle and per-step activity

`TASK STARTED`, numbered execution steps (`Step-1`, `Step-2`, …), the LLM's thoughts, the tool call, the command output, and finally `TASK COMPLETED`.

```log
INFO: MicroBot : ℹ️  TASK STARTED : 
            Analyze the log file `/var/log`
INFO: MicroBot :-------------------- Step-1 --------------------
INFO: MicroBot : 💭  LLM thoughts: Start by listing the contents of /var/log to identify the relevant log file to analyze.
INFO: MicroBot : ➡️  LLM tool call : "ls -1 /var/log"
INFO: MicroBot : ⬅️  Command output:
ShellCommunicator.log
alternatives.log
build.log
dpkg.log
...
INFO: MicroBot :🔚 TASK COMPLETED : 
```

### LOOP — LLM API activity

One-line `HTTP 200 OK` markers for each request to the model, followed by the parsed LLM response.

```log
INFO:httpx:HTTP Request: POST https://<your-endpoint>.openai.azure.com/openai/v1/responses "HTTP/1.1 200 OK"
INFO:microbots.llm.llm:The llm response is {'task_done': False, 'thoughts': 'Start by listing the contents of /var/log to identify the relevant log file to analyze.', 'command': 'ls -1 /var/log'}
```

### RESULT — teardown and cleanup

Overlay unmount and cleanup of the working directory once the run completes.

```log
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🛠️  Tearing down overlay mount for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:✅  Unmounted overlay for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🛑  Removing overlay dirs at //workdir/code and /workdir/overlay/
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗑️  Removed overlay directories for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗑️  Removed working directory at /home/user/MICROBOTS_WORKDIR_<id>
```

This view is usually enough to follow what the bot is doing and why. Switch to `DEBUG` only when you need to inspect Docker API calls, raw LLM request/response bodies, or low-level container execution details.

With logging enabled, every Microbots run is no longer a black box — you can see the exact steps, decisions, and commands behind each result. From here, you can build your own bots with confidence, knowing exactly what's happening under the hood.

## Further Reading

Now that you can read what Microbots is doing, dive deeper into how it's built:

- [Microbots Customizability](../blog/microbots-customizability.md) — how to tailor bots, tools, and environments to your own use cases.
- [RBAC & Authentication](../blog/rbac-authentication.md) — using Azure managed identity and role-based access control with Microbots.