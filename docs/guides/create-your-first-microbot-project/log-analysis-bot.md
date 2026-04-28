# LogAnalysisBot

### Introduction

The `LogAnalysisBot` is a read-only bot that mounts a target folder, inspects log files, and identifies the root cause of failures. Because the mount is read-only, the bot can correlate compiler errors with source code without ever modifying the project on disk.

In this guide, you will create the Python script that configures and runs a `LogAnalysisBot` against the `build.log` you generated earlier. By the end, the script will be ready to execute, and you will understand each constructor argument and `run()` parameter the bot exposes.

## Prerequisites

To complete this guide, you will need:

- A Microbots project with the package installed and an `.env` file configured. See the [Microbot Installation](../getting-started/installation-guide.md) guide.
- A `code/` folder containing `app.ts` and `build.log`. See the [Sample Project Creation and First Run](sample-project-and-first-run.md) guide.

## Step 1 — Creating the Bot Script

In this step, you will add a Python script at the root of the project that imports the `LogAnalysisBot` class, instantiates it, and points it at the build log.

Create a file named `log_analysis_bot.py` in the root of your `microbots-introduction` project with the following content:

```python title="log_analysis_bot.py" linenums="1"
--8<-- "docs/examples/microbots_introduction/log_analysis_bot.py"
```

The script does four things in order: it configures logging, imports `LogAnalysisBot`, instantiates the bot, and calls `run()` to analyze the log file. The next step explains each of these responsibilities and the arguments they accept.

## Step 2 — Understanding the Script

This step walks through the script section by section so you understand what each block does and how to adapt it to your own projects.

- **Lines 1–3:**
    ```python
    import logging

    logging.basicConfig(level=logging.INFO)
    ```
    Configures logging at the `INFO` level so you can see the bot's reasoning steps as it executes. Microbots automatically loads environment variables from a `.env` file in your project root, so no explicit `load_dotenv()` call is required.

- **Line 5:**
    ```python
    from microbots import LogAnalysisBot
    ```
    Imports `LogAnalysisBot` from the `microbots` package.

- **Lines 7–10:**
    ```python
    my_bot = LogAnalysisBot(
        model="azure-openai/gpt-5-swe-agent",
        folder_to_mount="code",
    )
    ```
    Creates a `LogAnalysisBot` instance configured with the Azure OpenAI model and the local `code/` folder. The folder is mounted as **read-only** inside the Docker container, so the bot can read source files but never modify them. For the full list of constructor arguments, defaults, and types, see the API Reference [`LogAnalysisBot`](../../api-reference/microbots/bot/LogAnalysisBot.md).

- **Lines 12–15:**
    ```python
    result = my_bot.run(
        file_name="code/build.log",
        timeout_in_seconds=600,
    )
    ```
    Calls `my_bot.run()`, pointing the bot at `code/build.log` with a 10-minute timeout. The bot spins up a container, reads the log, correlates errors with source files, and returns its analysis. For the full list of `run()` parameters (including `max_iterations` and other defaults), see the API Reference [`LogAnalysisBot`](../../api-reference/microbots/bot/LogAnalysisBot.md).

- **Line 16:**
    ```python
    print(result.result)
    ```
    Prints the bot's root-cause analysis. The `run()` method returns a `BotRunResult` object that exposes the bot's output, completion status, and any error encountered. For the complete field list, see the API Reference [`BotRunResult`](../../api-reference/microbots/MicroBot.md#microbots.MicroBot.BotRunResult).

## Conclusion

In this guide, you created the `log_analysis_bot.py` script that instantiates a `LogAnalysisBot`, points it at the `code/` folder, and calls `run()` against `build.log`. You also reviewed every constructor and `run()` argument the bot exposes. Continue to the [Output and Log Parsing](output-and-log-parsing.md) guide to execute the script and walk through the output the bot produces.

