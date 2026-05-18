# Create Your First Microbot Project

Create a sample C project with a deliberate compile error, generate a build log, and run a `LogAnalysisBot` against it.

**Requires:** `gcc` (preinstalled on most Linux distributions, or `sudo apt install build-essential`).

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

```log title="code/build.log"
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

`LogAnalysisBot` is a read-only bot that mounts a folder and analyzes log files. Create `log_analysis_bot.py` at the project root:

```python title="log_analysis_bot.py" linenums="1"
--8<-- "docs/examples/microbots_introduction/log_analysis_bot.py"
```

The script mounts `code/` **read-only** inside Docker, runs `LogAnalysisBot` against `code/build.log` with a 10-minute timeout, and prints the root-cause analysis from `result.result` (a `BotRunResult`).

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

Continue with [Conclusion](../conclusion.md).
