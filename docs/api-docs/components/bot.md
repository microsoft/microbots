# Bot

The `MicroBot` class is the core autonomous agent. All specialized bots (`ReadingBot`, `WritingBot`, etc.) extend this class.

You can use `MicroBot` directly for custom bots or subclass it for specialized behavior.

## Quick Example

```python
from microbots import MicroBot
from microbots.extras.mount import Mount, MountType, PermissionLabels

bot = MicroBot(
    model="azure-openai/gpt-5-swe-agent",
    system_prompt="You are a helpful coding assistant.",
    folder_to_mount=Mount(
        host_path="code",
        mount_type=MountType.MOUNT,
        permission=PermissionLabels.READ_ONLY,
    ),
)

result = bot.run(task="Analyze the project structure")
print(result.status, result.result)
```

## API Reference

<!-- Auto-generated from source code -->

::: microbots.MicroBot.MicroBot
    options:
        show_source: false


::: microbots.MicroBot.BotRunResult
    options:
      show_source: false

::: microbots.constants.ModelProvider
    options:
      show_source: false

::: microbots.extras.mount.MountType
    options:
      show_source: false

::: microbots.extras.mount.Mount
    options:
      show_source: false
