# LogAnalysisBot

The `LogAnalysisBot` analyzes log files and identifies root causes of failures. It mounts a code directory as read-only context and copies the target log file into the container for analysis.

## Quick Example

```python
from microbots import LogAnalysisBot

bot = LogAnalysisBot(
    model="azure-openai/gpt-4.1",
    folder_to_mount="/path/to/source/code",
)

result = bot.run(file_name="/path/to/error.log")
print(result.status, result.result)
```

## How It Works

1. The source code directory is mounted **read-only** at the sandbox path for context.
2. The log file is **copied** into `/var/log/` inside the container.
3. The bot analyzes the log, cross-references with the source code, and identifies the root cause.

## API Reference

<!-- Auto-generated from source code -->

::: microbots.bot.LogAnalysisBot.LogAnalysisBot
