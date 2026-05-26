# Create Your First Microbot Project

Create a sample C project with a deliberate compile error.
Generate a build log. Run a `LogAnalysisBot` against it.

**Requires:** `gcc` (preinstalled on most Linux distributions, or `sudo apt install build-essential`).

The sample C project files and `LogAnalysisBot` script used in this guide are available in the Microbots examples directory at `examples/microbots_introduction/`. Clone or download the Microbots repository and use those files to follow along.

## Step 1 — Create the Sample Project

From the root of your `microbots-introduction` project, create a `code/` folder:

```bash title="Terminal"
mkdir code
```

Add a C file with a deliberate syntax error:

```c title="code/app.c" linenums="1"
--8<-- "docs/examples/microbots_introduction/code/app.c"
```

Line 5 is missing the trailing `;` after `return a + b`, so `gcc` will fail.

## Step 2 — Generate the Build Log

```bash title="Terminal"
cd code
gcc app.c > build.log 2>&1
cd ..
```

`code/build.log` should contain:

```log title="code/build.log" linenums="1"
app.c: In function ‘add’:
app.c:5:17: error: expected ‘;’ before ‘}’ token
    5 |     return a + b
      |                 ^
      |                 ;
    6 | }
      | ~ 
```

Project layout:

```text title="Project layout"
microbots-introduction/
├── .venv
├── .env
└── code/
    ├── app.c
    └── build.log
```

## Step 3 — Write the Bot Script

Create `log_analysis_bot.py` at the project root:

```python title="log_analysis_bot.py" linenums="1"
--8<-- "docs/examples/microbots_introduction/log_analysis_bot.py"
```

The script imports [`LogAnalysisBot`](../../api-reference/microbots/bot/LogAnalysisBot.md), instantiates it, and invokes its `run()` method on the build log.

**Constructing the bot** — [`LogAnalysisBot(...)`](../../api-reference/microbots/bot/LogAnalysisBot.md):

- **`model`** — the LLM that powers the bot, in `<provider>/<deployment-or-model-name>` format. Here, `azure-openai/gpt-5-agent` points to a deployment named `gpt-5-agent` on the Azure OpenAI resource configured in `.env` For other providers, see the [Authentication Setup](../../advanced/authentication.md) guide.
- **`folder_to_mount`** — a path on your host that the bot can read inside its Docker sandbox. The folder is mounted **read-only** at `/workdir/<folder-name>/` inside the container, so the bot can inspect your source code but cannot modify it. Here, `"code"` mounts the local `code/` folder to `/workdir/code/` of the container.

**Running the bot** — [`my_bot.run(...)`](../../api-reference/microbots/bot/LogAnalysisBot.md):

- **`file_name`** — path to the log file to analyze. The file is copied into the container at `/var/log/` and the bot is instructed to identify the root cause of any failures it contains. Here, `"code/build.log"` is the gcc build log produced in Step 2.
- **`timeout_in_seconds`** — maximum time the bot is allowed to run before being terminated. Here, `600` gives the bot up to 10 minutes to finish its analysis.

The call returns a [`BotRunResult`](../../api-reference/microbots/MicroBot.md); `result.result` holds the final root-cause analysis produced by the bot.

## Step 4 — Run the Bot

From the project root, with your virtual environment activated:

```bash title="Terminal"
python3 log_analysis_bot.py
```

`print(result.result)` outputs the root-cause analysis:

```text title="Output"
Root cause identified: The build failed due to a syntax error in 
//workdir/code/app.c at line 5. The function add(int a, int b) has 
a missing semicolon after the return statement (`return a + b`). 
This matches the compiler error in /var/log/build.log: "error: 
expected ';' before '}' token". Fix by adding a semicolon: `return a + b;`.
```

In this walkthrough, we created buggy code and successfully analyzed it with Microbots. Based on the analysis output, `LogAnalysisBot` correctly identified the bug in the code and explained the fix as well.

Please read the next article to understand what happens behind the scenes and how to debug Microbots code with logs. Continue with [Microbots Execution Flow](../microbots-execution-flow.md).
