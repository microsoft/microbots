# Sample Project Creation and First Run

### Introduction

Before running a Microbot, you need a target project for it to analyze. In this guide, you will create a small TypeScript project that contains a deliberate syntax error and capture the resulting compiler errors in a build log. The error and log together give the `LogAnalysisBot` something concrete to reason about in the next guide.

By the end of this guide, you will have a `code/` folder with a broken TypeScript source file and a `build.log` file that records the failed compilation — the inputs the bot will use to demonstrate root-cause analysis.

## Prerequisites

To complete this guide, you will need:

- A working Microbots project directory with the package installed and an `.env` file configured. See the [Microbot Installation](../getting-started/installation-guide.md) guide.
- The **TypeScript compiler** (`tsc`) available on your `PATH`. Install it globally with `npm install -g typescript`. See the [TypeScript installation guide](https://www.typescriptlang.org/download) for details.

## Step 1 — Creating the Code Directory

In this step, you will add a sub-directory inside your Microbots project where the sample source files will live. Keeping the sample code in a dedicated folder lets you mount only that folder into the bot's container later.

From the root of your `microbots-introduction` project, create a `code` directory:

```bash title="Terminal"
mkdir code
```

The `mkdir` command creates a new folder named `code` next to the `.venv` and `.env` files you created earlier.

## Step 2 — Adding a TypeScript File With a Deliberate Error

In this step, you will add a TypeScript file that contains a malformed function signature. The error is intentional — it is what the `LogAnalysisBot` will diagnose later.

Create a file named `code/app.ts` with the following content:

```typescript title="code/app.ts" linenums="1"
--8<-- "docs/examples/microbots_introduction/code/app.ts"
```

The function `add` on line 8 has a malformed type annotation: `b: number: number` instead of `b: number): number`. The closing parenthesis is missing before the return-type annotation, so the TypeScript compiler will fail to parse the function.

## Step 3 — Generating the Build Log

In this step, you will run the TypeScript compiler against `app.ts` and capture both standard output and standard error into a `build.log` file. The bot will read this log to identify what went wrong.

Before invoking the compiler, confirm that **Node.js** and the **TypeScript compiler (`tsc`)** are installed and reachable from your terminal:

```bash title="Terminal"
node --version
tsc --version
```

Both commands should print a version number. `node --version` prints the installed Node.js runtime (for example, `v20.11.0`), and `tsc --version` prints the TypeScript compiler version (for example, `Version 5.4.5`).

!!! note "If either command is missing"
    - **Node.js not found** — Install it from [nodejs.org](https://nodejs.org/) (the LTS release is recommended) and re-open your terminal.
    - **`tsc` not found** — Install the TypeScript compiler globally with `npm install -g typescript`, then re-run `tsc --version` to confirm it is on your `PATH`.

From the project root, run the compiler and redirect its output to `build.log`:

```bash title="Terminal"
cd code
tsc app.ts > build.log 2>&1
cd ..
```

The `tsc app.ts` command invokes the TypeScript compiler on `app.ts`. The redirection `> build.log 2>&1` writes both standard output (`stdout`) and standard error (`stderr`) into the same file, so any compiler diagnostics are captured.

Open `code/build.log` to confirm it contains the compiler errors:

```log title="code/build.log"
app.ts(8,34): error TS1005: ',' expected.
app.ts(8,43): error TS1005: ',' expected.
app.ts(9,12): error TS1005: ':' expected.
app.ts(9,14): error TS1005: ',' expected.
app.ts(10,1): error TS1128: Declaration or statement expected.
```

Your project folder should now have the following structure:

```text title="Project layout"
microbots-introduction/
├── .venv
├── .env
└── code/
    ├── app.ts
    ├── app.js
    └── build.log
```

## Conclusion

In this guide, you created a `code/` directory, added a TypeScript file with a deliberate syntax error, and generated a `build.log` file that captures the compilation failure. With these inputs in place, continue to the [LogAnalysisBot](log-analysis-bot.md) guide to write the script that points a bot at this log and produces a root-cause analysis.

