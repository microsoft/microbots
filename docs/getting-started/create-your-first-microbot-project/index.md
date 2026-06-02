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
├── log_analysis_bot.py
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

#### Constructing the bot

```python linenums="7"
my_bot = LogAnalysisBot(
    model="azure-openai/gpt-5-agent",
    folder_to_mount="code",
)
```

[`LogAnalysisBot(...)`](../../api-reference/microbots/bot/LogAnalysisBot.md) takes the following arguments:

- **`model`** — the LLM powering the bot, in `<provider>/<deployment-or-model-name>` format. For other providers, see the [Authentication Setup](../../advanced/authentication.md) guide.
- **`folder_to_mount`** — host folder the bot can access inside its Docker sandbox. Mounted **read-only** at `/workdir/<folder-name>/`.

#### Running the bot

```python linenums="12"
result = my_bot.run(
    file_name="code/build.log",
    timeout_in_seconds=600,
)
```

[`my_bot.run(...)`](../../api-reference/microbots/bot/LogAnalysisBot.md) takes the following arguments:

- **`file_name`** — path to the log file to analyze. The file is copied into the container at `/var/log/` for the bot to inspect.
- **`timeout_in_seconds`** — maximum time the bot may run before being terminated. `600` allows up to 10 minutes.

#### Reading the result

```python linenums="16"
print(result.result)
```

The `my_bot.run()` method returns a [`BotRunResult`](../../api-reference/microbots/MicroBot.md#microbots.MicroBot.BotRunResult) object with the following fields:

- **`status`** (`bool`) — `True` if the bot completed its task successfully, `False` otherwise.
- **`result`** (`str | None`) — the bot's final output (root-cause analysis here). `None` when the run fails before producing a result.
- **`error`** (`str | None`) — error details when `status` is `False`; `None` on success.

In this example, `print(result.result)` prints the root-cause analysis returned by the bot.

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
