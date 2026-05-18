# Create Your First Microbot Project

Create a sample TypeScript project with a deliberate compile error, generate a build log, and run a `LogAnalysisBot` against it.

**Requires:** A configured Microbots project (see [Microbot Installation](../installation-guide.md)) plus **Node.js** and **TypeScript** (`npm install -g typescript`).

## Step 1 — Create the Sample Project

From the root of your `microbots-introduction` project, create a `code/` folder:

```bash title="Terminal"
mkdir code
```

Add a TypeScript file with a deliberate syntax error:

```typescript title="code/app.ts" linenums="1"
--8<-- "docs/examples/microbots_introduction/code/app.ts"
```

Line 8 has a malformed signature (`b: number: number` instead of `b: number): number`), so `tsc` will fail.

## Step 2 — Generate the Build Log

```bash title="Terminal"
cd code
tsc app.ts > build.log 2>&1
cd ..
```

`code/build.log` should contain:

```log title="code/build.log"
app.ts(8,34): error TS1005: ',' expected.
app.ts(8,43): error TS1005: ',' expected.
app.ts(9,12): error TS1005: ':' expected.
app.ts(9,14): error TS1005: ',' expected.
app.ts(10,1): error TS1128: Declaration or statement expected.
```

Project layout:

```text title="Project layout"
microbots-introduction/
├── .venv
├── .env
└── code/
    ├── app.ts
    ├── app.js
    └── build.log
```

## Step 3 — Write the Bot Script

`LogAnalysisBot` is a read-only bot that mounts a folder and analyzes log files. Create `log_analysis_bot.py` at the project root:

```python title="log_analysis_bot.py" linenums="1"
--8<-- "docs/examples/microbots_introduction/log_analysis_bot.py"
```

The script mounts `code/` **read-only** inside Docker, runs `LogAnalysisBot` against `code/build.log` with a 10-minute timeout, and prints the root-cause analysis from `result.result` (a `BotRunResult`).

See the API Reference for all parameters: [`LogAnalysisBot`](../../api-reference/microbots/bot/LogAnalysisBot.md), [`BotRunResult`](../../api-reference/microbots/MicroBot.md#microbots.MicroBot.BotRunResult).

Continue to the [Output and Log Parsing](output-and-log-parsing.md) guide to run the script and inspect the output.


