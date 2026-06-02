# Create Your First Microbot Project

In this short walkthrough, you'll build your first Microbot end-to-end. You'll:

1. Create a tiny C program with a deliberate bug.
2. Compile it and capture the build error in a log file.
3. Run a `LogAnalysisBot` that reads the log and explains the root cause for you.

By the end, you'll have a working Microbot script you can adapt to your own logs.

!!! note "Before you begin"
    You'll need `gcc` to compile the sample C file. It's preinstalled on most Linux distributions — if not, run `sudo apt install build-essential`.

## Step 1 — Create the Sample Project

From the root of your `microbots-introduction` project, create a `code/` folder:

```bash title="Terminal"
mkdir code
```

Next, add a small C file with a deliberate syntax error — this is what we'll ask the bot to analyze:

```c title="code/app.c" linenums="1"
--8<-- "docs/examples/microbots_introduction/code/app.c"
```

Notice line 5: it's missing the trailing `;` after `return a + b`. That's the bug — `gcc` will refuse to compile it, and we'll capture that error in the next step.

## Step 2 — Generate the Build Log

Now let's compile the file and redirect both standard output and standard error into a log file the bot can read:

```bash title="Terminal"
cd code
gcc app.c > build.log 2>&1
cd ..
```

The compilation will fail (as expected), and `code/build.log` will contain the compiler's complaint:

```log title="code/build.log" linenums="1"
app.c: In function ‘add’:
app.c:5:17: error: expected ‘;’ before ‘}’ token
    5 |     return a + b
      |                 ^
      |                 ;
    6 | }
      | ~ 
```

Once you complete the next step, your project layout will look like this:

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

Time to wire up the bot. Create `log_analysis_bot.py` at the project root:

```python title="log_analysis_bot.py" linenums="1"
--8<-- "docs/examples/microbots_introduction/log_analysis_bot.py"
```

This short script does three things: it imports [`LogAnalysisBot`](../../api-reference/microbots/bot/LogAnalysisBot.md), creates an instance of it, and invokes its `run()` method on the build log. Let's walk through each piece.

#### Constructing the bot

```python linenums="7"
my_bot = LogAnalysisBot(
    model="azure-openai/gpt-5-agent",
    folder_to_mount="code",
)
```

Here, [`LogAnalysisBot(...)`](../../api-reference/microbots/bot/LogAnalysisBot.md) takes two arguments:

- **`model`** — the LLM that powers the bot, in `<provider>/<deployment-or-model-name>` format. Using a different provider? See the [Authentication Setup](../../advanced/authentication.md) guide.
- **`folder_to_mount`** — the host folder the bot can access from inside its Docker sandbox. It's mounted **read-only** at `/workdir/<folder-name>/`, so the bot can inspect your source code but can't change it.

#### Running the bot

```python linenums="12"
result = my_bot.run(
    file_name="code/build.log",
    timeout_in_seconds=600,
)
```

[`my_bot.run(...)`](../../api-reference/microbots/bot/LogAnalysisBot.md) takes two arguments:

- **`file_name`** — path to the log file you want analyzed. The file is copied into the container at `/var/log/` so the bot can read it.
- **`timeout_in_seconds`** — a safety net: the maximum time the bot is allowed to run before being terminated. `600` gives it up to 10 minutes.

#### Reading the result

```python linenums="16"
print(result.result)
```

`my_bot.run()` returns a [`BotRunResult`](../../api-reference/microbots/MicroBot.md#microbots.MicroBot.BotRunResult) object with three fields:

- **`status`** (`bool`) — `True` if the bot completed its task successfully, `False` otherwise.
- **`result`** (`str | None`) — the bot's final output (the root-cause analysis, in our case). `None` if the run fails before producing a result.
- **`error`** (`str | None`) — error details when `status` is `False`; `None` on success.

So `print(result.result)` simply prints the root-cause analysis the bot came up with.

## Step 4 — Run the Bot

You're all set. From the project root, with your virtual environment activated, run:

```bash title="Terminal"
python3 log_analysis_bot.py
```

Give it a few seconds — the bot spins up its sandbox, inspects the log and the source, and then prints its analysis. You should see something like this:

```text title="Output"
Root cause identified: The build failed due to a syntax error in 
//workdir/code/app.c at line 5. The function add(int a, int b) has 
a missing semicolon after the return statement (`return a + b`). 
This matches the compiler error in /var/log/build.log: "error: 
expected ';' before '}' token". Fix by adding a semicolon: `return a + b;`.
```

And that's it — you've just run your first Microbot. With only a handful of lines of code, `LogAnalysisBot` pinpointed the bug in our C file and even suggested the fix.

Curious about what happened under the hood? The next article walks through the execution flow and shows you how to use logs to debug your own Microbots. Continue with [Microbots Execution Flow](../microbots-execution-flow.md).
