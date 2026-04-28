# Output and Log Parsing

### Introduction

With the `log_analysis_bot.py` script in place, the next task is to execute it and interpret the output. Microbots emits two complementary streams: structured logger output that traces every container action and LLM iteration, and the bot's final analysis returned through `result.result`.

In this guide, you will run the script, inspect the full logger output to see how the bot reasons over the build log, and review the root-cause analysis that `LogAnalysisBot` produces.

## Prerequisites

To complete this guide, you will need:

- A `log_analysis_bot.py` script at the root of your project. See the [LogAnalysisBot](log-analysis-bot.md) guide.
- A `code/` folder containing `app.ts` and `build.log`. See the [Sample Project Creation and First Run](sample-project-and-first-run.md) guide.
- Docker running on your machine. See the [Pre-requisites](../getting-started/prerequisites.md#step-2-installing-docker) guide.

## Step 1 — Running the Bot

In this step, you will execute the script you created in the previous guide and let the `LogAnalysisBot` analyze the build log.

From the root of the `microbots-introduction` project, with your virtual environment activated, run:

```bash title="Terminal"
python3 log_analysis_bot.py
```

The `LogAnalysisBot` spins up a Docker container, mounts the `code` folder as read-only, copies `build.log` into `/var/log/` inside the container, and uses the LLM to analyze the log file and report the root cause.

## Step 2 — Tracing the Bot's Reasoning Through the Logger Output

In this step, you will read through the `INFO`-level logger output that Microbots emits during a run, broken into the six stages that make up the bot's lifecycle: container setup, task start, log inspection, source-file correlation, root-cause identification, and teardown. This trace is what `logging.basicConfig(level=logging.INFO)` enables in the script.

Tracing the logger output matters when you are **debugging** an unexpected result, **understanding** how a bot decomposes a task into shell commands, or **auditing** which files and commands the LLM touched inside the container. For day-to-day usage — where you only care about the final answer — you can rely on `result.result` alone.

!!! tip "Skip ahead if you only need the final answer"
    If you are not interested in the bot's internal reasoning trace, you can skip directly to [Step 3 — Reviewing the Root-Cause Analysis](#step-3-reviewing-the-root-cause-analysis), which covers the value returned in `result.result`.

Because the script sets `logging.basicConfig(level=logging.INFO)`, the run produces detailed step-by-step output. Rather than reproducing the full transcript, the snippets below walk through the run in order, with a short explanation of what is happening at each stage.

### 1. Environment setup

When the script starts, the `LocalDockerEnvironment` provisions an isolated working directory on the host, starts a fresh Docker container, sets up the read-only OverlayFS mount for the `code` folder, and copies `build.log` into the container's `/var/log/` directory:

```text title="Environment setup"
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗂️  Created working directory at /home/sikannan/MICROBOTS_WORKDIR_18da47d7
INFO:microbots.environment.local_docker.LocalDockerEnvironment:📦 Volume mapping: /mnt/c/Users/sikannan/codeBase/microbots-examples/code → /ro/code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🚀 Started container b4826a8d41b7 with image kavyasree261002/shell_server:latest on host port 35291
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🔒 Set up overlay mount for read-only directory at /workdir/code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:✅ Successfully copied /mnt/c/Users/sikannan/codeBase/microbots-examples/code/build.log to container:/var/log
```

### 2. Task starts and the LLM lists the log directory

The bot sends the task prompt to the LLM, which decides to begin by listing `/var/log` to find which file to inspect. Each iteration is logged as a `Step-N` block with the LLM's thoughts, the command it issued, and the command's output:

```text title="Step 1 — list /var/log"
INFO: MicroBot : ℹ️  TASK STARTED :
            Analyze the log file `/var/log`
INFO: MicroBot :-------------------- Step-1 --------------------
INFO: MicroBot : 💭  LLM thoughts: First, I need to see what log files exist in /var/log to determine which one to analyze.
INFO: MicroBot : ➡️  LLM tool call : "ls -1 /var/log"
INFO: MicroBot : ⬅️  Command output:
ShellCommunicator.log
build.log
dpkg.log
...
```

### 3. The LLM inspects `build.log`

Steps 2 and 3 show the LLM gauging the log size with `wc -l` and then reading the file with `cat`. The TypeScript compiler errors surface here, giving the LLM concrete error codes (`TS1005`, `TS1128`) and line numbers to follow:

```text title="Step 3 — read build.log"
INFO: MicroBot :-------------------- Step-3 --------------------
INFO: MicroBot : 💭  LLM thoughts: The build.log is small, so I can safely view it to check for errors.
INFO: MicroBot : ➡️  LLM tool call : "cat /var/log/build.log"
INFO: MicroBot : ⬅️  Command output:
app.ts(8,34): error TS1005: ',' expected.
app.ts(8,43): error TS1005: ',' expected.
app.ts(9,12): error TS1005: ':' expected.
app.ts(9,14): error TS1005: ',' expected.
app.ts(10,1): error TS1128: Declaration or statement expected.
```

### 4. The LLM correlates errors with the source file

Now that the LLM knows the error originates in `app.ts`, it lists the mounted `code` folder and reads `app.ts` with line numbers (`nl -ba`) so it can locate the exact malformed line:

```text title="Step 5 — read app.ts with line numbers"
INFO: MicroBot :-------------------- Step-5 --------------------
INFO: MicroBot : 💭  LLM thoughts: Open the TypeScript file to inspect the syntax around lines 8-10 where errors are reported.
INFO: MicroBot : ➡️  LLM tool call : "nl -ba //workdir/code/app.ts | sed -n '1,40p'"
INFO: MicroBot : ⬅️  Command output:
     7  // Missing closing parenthesis on the type annotation
     8  function add(a: number, b: number: number {
     9      return a + b;
    10  }
```

### 5. Root cause is identified and the task completes

The LLM has enough context to conclude. It returns `task_done: True` with a final reasoning trace that pinpoints the malformed signature on line 8 and proposes the corrected version. This is what later becomes `result.result`:

```text title="Final thoughts"
INFO: MicroBot : 💭  LLM final thoughts: Root cause identified from /var/log/build.log: TypeScript compilation fails due to a syntax error in //workdir/code/app.ts at line 8. The function declaration is malformed: `function add(a: number, b: number: number {` has an extra `: number` after `b` and is missing the closing parenthesis before the return type. Correct signature should be: `function add(a: number, b: number): number {`.
INFO: MicroBot :🔚 TASK COMPLETED
```

### 6. Container teardown

Finally, the environment unmounts the overlay, removes the overlay directories, and deletes the working directory — leaving no trace on the host:

```text title="Teardown"
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🛠️  Tearing down overlay mount for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:✅  Unmounted overlay for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🛑  Removing overlay dirs at //workdir/code and /workdir/overlay/
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗑️  Removed overlay directories for code
INFO:microbots.environment.local_docker.LocalDockerEnvironment:🗑️  Removed working directory at /home/sikannan/MICROBOTS_WORKDIR_18da47d7
```

## Step 3 — Reviewing the Root-Cause Analysis

In this step, you will inspect the value returned through `result.result`, which is the bot's final analysis. This is the artifact that downstream automation (a CI pipeline, a chat notification, an issue tracker) typically consumes.

The `print(result.result)` call at the end of the script writes output similar to the following:

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

The `LogAnalysisBot` read `build.log`, correlated the compiler errors with the source code in `app.ts`, identified the malformed type annotation as the root cause, and proposed a corrected function signature — without any human intervention.

!!! tip "DevOps Integration"
    This pattern integrates naturally into CI/CD pipelines. Point the `LogAnalysisBot` at build logs, test reports, or deployment logs from tools like GitHub Actions, Azure DevOps, Jenkins, or GitLab CI — and get instant root-cause analysis delivered as part of your pipeline output.

## Conclusion

In this guide, you executed the `log_analysis_bot.py` script, traced the bot's reasoning through the logger output, and reviewed the root-cause analysis returned in `result.result`. Continue to the [Conclusion](conclusion.md) guide to see what Microbots did under the hood and to explore the other bots available in the framework.
