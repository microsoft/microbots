# API Reference Documentation Guide

This guide explains how to write Python docstrings in the Microbots project so that
the API reference documentation is generated correctly. Microbots uses
[mkdocstrings](https://mkdocstrings.github.io/) with the **NumPy docstring style**
to auto-generate API docs from source code.

> **Key Rule:** Write proper NumPy-style docstrings in your Python code. The
> documentation is generated directly from these docstrings — no manual markdown
> files are needed for API reference.

---

## Docstring Style: NumPy

All docstrings in this project **must** follow the
[NumPy docstring format](https://numpydoc.readthedocs.io/en/latest/format.html).

### Indentation Rules

This is the most common source of rendering issues. After a section header
(`Parameters`, `Attributes`, `Returns`, etc.):

- Parameter names must be at the **same indentation level** as the section header.
- Descriptions must be indented **one level deeper** than the parameter name.

```python
# ✅ CORRECT — parameter names aligned with section header
def my_function(name: str, count: int):
    """
    Do something useful.

    Parameters
    ----------
    name : str
        The name to use.
    count : int
        How many times to repeat.
    """

# ❌ WRONG — extra indent on parameter names
def my_function(name: str, count: int):
    """
    Do something useful.

    Parameters
    ----------
        name : str
            The name to use.
        count : int
            How many times to repeat.
    """
```

**Correct indentation renders as:**

> **Parameters:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `name` | `str` | The name to use. |
> | `count` | `int` | How many times to repeat. |

**Wrong indentation renders as:**

> **Parameters:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `name` | `str` | The name to use. count : int How many times to repeat. |
>
> *(Everything collapses into a single parameter's description!)*

The wrong indentation causes mkdocstrings to treat everything after the first
parameter as part of that parameter's description, resulting in a single wall of
text in the rendered docs.

---

## Classes

### Basic Class with Attributes

Use the `Attributes` section in the **class docstring** to document instance
attributes. Each attribute follows the format `name : type`.

```python
from enum import StrEnum


class ModelProvider(StrEnum):
    """
    Supported LLM provider backends.

    Attributes
    ----------
    OPENAI : str
        Azure OpenAI provider.
    OLLAMA_LOCAL : str
        Local Ollama instance.
    ANTHROPIC : str
        Anthropic Claude provider.
    """

    OPENAI = "azure-openai"
    OLLAMA_LOCAL = "ollama-local"
    ANTHROPIC = "anthropic"
```

**Renders as:**

> #### class `ModelProvider`
> *Bases:* `StrEnum`
>
> Supported LLM provider backends.
>
> **Attributes:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `OPENAI` | `str` | Azure OpenAI provider. |
> | `OLLAMA_LOCAL` | `str` | Local Ollama instance. |
> | `ANTHROPIC` | `str` | Anthropic Claude provider. |

### Dataclass

For `@dataclass` classes, document fields in the `Attributes` section of the
class docstring.

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mount:
    """
    Folder mount configuration for a microbot environment.

    All the folders and files to be presented for the Bot should be
    either mounted or copied to the Bot's sandbox environment using
    this class.

    Attributes
    ----------
    host_path : str
        The absolute path on the host machine to be mounted or copied.
    sandbox_path : str
        The absolute path inside the Bot's sandbox environment where the
        host_path will be mounted or copied.
    permission : PermissionLabels
        The permission level for the mounted/copied folder.
    mount_type : MountType
        The type of mount operation. Default is ``MountType.MOUNT``.
    """

    host_path: str
    sandbox_path: str
    permission: PermissionLabels
    mount_type: MountType = MountType.MOUNT
```

**Renders as:**

> #### class `Mount`
> *dataclass*
>
> Folder mount configuration for a microbot environment.
>
> All the folders and files to be presented for the Bot should be either mounted or copied to the Bot's sandbox environment using this class.
>
> **Attributes:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `host_path` | `str` | The absolute path on the host machine to be mounted or copied. |
> | `sandbox_path` | `str` | The absolute path inside the Bot's sandbox environment where the host_path will be mounted or copied. |
> | `permission` | `PermissionLabels` | The permission level for the mounted/copied folder. |
> | `mount_type` | `MountType` | The type of mount operation. Default is `MountType.MOUNT`. |

### Class with `__init__` Parameters

When a class has a non-trivial `__init__`, document **constructor parameters**
in the `__init__` docstring using `Parameters`, and document **public
attributes** in the class-level docstring using `Attributes`.

#### Why both `Attributes` and `Parameters`?

They serve different purposes in the documentation:

| | **Attributes** (class docstring) | **Parameters** (\_\_init\_\_ docstring) |
|---|---|---|
| **Purpose** | Documents what the object **has** after creation | Documents what the constructor **accepts** to create the object |
| **Audience** | Users who already have an instance and want to access its properties | Users who need to know how to **create** an instance |
| **Includes** | All public instance attributes, including computed or derived ones set in `__init__` or `__post_init__` | Only the arguments passed to the constructor |
| **Shows defaults** | No | Yes — the Default column shows each parameter's default value |
| **Location** | Class-level docstring (top of the class) | `__init__` method docstring |

**When are both needed?**

- A class may have **attributes that are not constructor parameters** (e.g., `iteration_count` is initialized internally but never passed in).
- A constructor may have **parameters that don't become attributes** (e.g., a `token_provider` that is consumed during init but not stored).
- The **descriptions differ** — Attributes describe what the property represents on the object, while Parameters describe what to pass and what happens with each value.

**When is only one needed?**

- **Dataclasses / simple classes:** If every constructor argument maps directly to an attribute with the same meaning, you can use just `Attributes` in the class docstring. mkdocstrings will pick up the fields automatically.
- **Functions / methods:** Only use `Parameters` (there are no attributes).

```python
class MicroBot:
    """
    The core Microbot class.

    MicroBot is the core class representing the autonomous agent.
    Other bots are extensions of this class.

    Attributes
    ----------
    model : str
        The model to use for the bot.
    bot_type : BotType
        The type of bot being created.
    system_prompt : Optional[str]
        The system prompt to guide the bot's behavior.
    environment : Optional[any]
        The execution environment for the bot.
    """

    def __init__(
        self,
        model: str,
        bot_type: BotType = BotType.CUSTOM_BOT,
        system_prompt: Optional[str] = None,
        environment: Optional[any] = None,
    ):
        """
        Initialize a MicroBot instance.

        Parameters
        ----------
        model : str
            The model to use, in the format ``<provider>/<model_name>``.
        bot_type : BotType
            The type of bot. Default is ``BotType.CUSTOM_BOT``.
        system_prompt : Optional[str]
            System prompt to guide behavior. Defaults to None.
        environment : Optional[any]
            The execution environment. If not provided, a default
            LocalDockerEnvironment will be created.
        """
        self.model = model
        self.bot_type = bot_type
```

**Renders as:**

> #### class `MicroBot`
>
> The core Microbot class.
>
> MicroBot is the core class representing the autonomous agent. Other bots are extensions of this class.
>
> **Attributes:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `model` | `str` | The model to use for the bot. |
> | `bot_type` | `BotType` | The type of bot being created. |
> | `system_prompt` | `Optional[str]` | The system prompt to guide the bot's behavior. |
> | `environment` | `Optional[any]` | The execution environment for the bot. |
>
> Initialize a MicroBot instance.
>
> **Parameters:**
>
> | Name | Type | Description | Default |
> |------|------|-------------|---------|
> | `model` | `str` | The model to use, in the format `<provider>/<model_name>`. | *required* |
> | `bot_type` | `BotType` | The type of bot. | `BotType.CUSTOM_BOT` |
> | `system_prompt` | `Optional[str]` | System prompt to guide behavior. | `None` |
> | `environment` | `Optional[any]` | The execution environment. If not provided, a default LocalDockerEnvironment will be created. | `None` |

> **Tip:** The `merge_init_into_class` option is enabled, so `__init__`
> parameters will appear on the same page as the class documentation.

---

## Functions and Methods

### Function with Parameters and Return Value

```python
def get_free_port() -> int:
    """
    Find and return an available TCP port on localhost.

    Scans for a free port by binding to port 0 and letting the OS
    assign one.

    Returns
    -------
    int
        An available port number.
    """
```

**Renders as:**

> #### function `get_free_port() → int`
>
> Find and return an available TCP port on localhost.
>
> Scans for a free port by binding to port 0 and letting the OS assign one.
>
> **Returns:**
>
> | Type | Description |
> |------|-------------|
> | `int` | An available port number. |

### Method with Parameters, Returns, and Raises

```python
def execute(self, command: str, timeout: Optional[int] = 300) -> CmdReturn:
    """
    Execute a shell command inside the environment.

    Parameters
    ----------
    command : str
        The shell command to execute.
    timeout : Optional[int]
        Maximum seconds to wait for the command to complete.
        Defaults to 300.

    Returns
    -------
    CmdReturn
        An object containing stdout, stderr, and return_code.

    Raises
    ------
    TimeoutError
        If the command exceeds the timeout duration.
    ConnectionError
        If the environment is not running.
    """
```

**Renders as:**

> #### method `execute(command, timeout=300) → CmdReturn`
>
> Execute a shell command inside the environment.
>
> **Parameters:**
>
> | Name | Type | Description | Default |
> |------|------|-------------|---------|
> | `command` | `str` | The shell command to execute. | *required* |
> | `timeout` | `Optional[int]` | Maximum seconds to wait for the command to complete. | `300` |
>
> **Returns:**
>
> | Type | Description |
> |------|-------------|
> | `CmdReturn` | An object containing stdout, stderr, and return_code. |
>
> **Raises:**
>
> | Type | Description |
> |------|-------------|
> | `TimeoutError` | If the command exceeds the timeout duration. |
> | `ConnectionError` | If the environment is not running. |

---

## Abstract Base Classes

Use the same docstring conventions. mkdocstrings will display the class
with its abstract methods.

```python
from abc import ABC, abstractmethod


class Environment(ABC):
    """
    Abstract base class for all execution environments.

    Subclasses must implement ``start``, ``stop``, and ``execute``.
    """

    @abstractmethod
    def start(self):
        """Start the environment."""

    @abstractmethod
    def stop(self):
        """Stop and clean up the environment."""

    @abstractmethod
    def execute(self, command: str) -> CmdReturn:
        """
        Execute a command in the environment.

        Parameters
        ----------
        command : str
            The command to run.

        Returns
        -------
        CmdReturn
            The command result.
        """
```

**Renders as:**

> #### class `Environment`
> *Bases:* `ABC`
>
> Abstract base class for all execution environments.
>
> Subclasses must implement `start`, `stop`, and `execute`.
>
> ---
>
> ##### method `start()` · *abstract*
> Start the environment.
>
> ##### method `stop()` · *abstract*
> Stop and clean up the environment.
>
> ##### method `execute(command) → CmdReturn` · *abstract*
> Execute a command in the environment.
>
> **Parameters:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `command` | `str` | The command to run. |
>
> **Returns:**
>
> | Type | Description |
> |------|-------------|
> | `CmdReturn` | The command result. |

---

## Enums

Document each member in the `Attributes` section.

```python
from enum import StrEnum


class BotType(StrEnum):
    """
    Types of bots available in the Microbots framework.

    Attributes
    ----------
    READING_BOT : str
        A bot specialized in reading and comprehending code.
    WRITING_BOT : str
        A bot that can make controlled file edits.
    BROWSING_BOT : str
        A bot with web browsing capabilities.
    CUSTOM_BOT : str
        A general-purpose custom bot.
    """

    READING_BOT = "READING_BOT"
    WRITING_BOT = "WRITING_BOT"
    BROWSING_BOT = "BROWSING_BOT"
    CUSTOM_BOT = "CUSTOM_BOT"
```

**Renders as:**

> #### class `BotType`
> *Bases:* `StrEnum`
>
> Types of bots available in the Microbots framework.
>
> **Attributes:**
>
> | Name | Type | Description |
> |------|------|-------------|
> | `READING_BOT` | `str` | A bot specialized in reading and comprehending code. |
> | `WRITING_BOT` | `str` | A bot that can make controlled file edits. |
> | `BROWSING_BOT` | `str` | A bot with web browsing capabilities. |
> | `CUSTOM_BOT` | `str` | A general-purpose custom bot. |

---

## Module-Level Constants

Module-level variables are documented with an inline comment or a docstring
immediately following the assignment.

```python
WORKING_DIR = str(Path.home() / "MICROBOTS_WORKDIR")
"""Default working directory on the host machine."""

DOCKER_WORKING_DIR = "/workdir"
"""Working directory inside the Docker container."""
```

**Renders as:**

> **module-attribute** `WORKING_DIR = str(Path.home() / "MICROBOTS_WORKDIR")`
>
> Default working directory on the host machine.
>
> ---
>
> **module-attribute** `DOCKER_WORKING_DIR = "/workdir"`
>
> Working directory inside the Docker container.

---

## Available Sections

The following section headers are recognized by mkdocstrings (NumPy style):

| Section        | Use for                                      |
|----------------|----------------------------------------------|
| `Parameters`   | Function/method arguments                    |
| `Attributes`   | Class or instance attributes                 |
| `Returns`      | Return values                                |
| `Yields`       | Values yielded by generators                 |
| `Raises`       | Exceptions that may be raised                |
| `Notes`        | Additional implementation notes              |
| `Examples`     | Usage examples (rendered as code blocks)     |
| `See Also`     | Cross-references to related objects          |
| `References`   | Citations or external links                  |
| `Warnings`     | Important warnings for users                 |

Each section header must be followed by a line of dashes of equal length:

```
Parameters
----------
```

---

## Cross-Referencing Other Classes

You can link to any documented class, method, or function from within a
docstring using backtick references. mkdocstrings with autorefs will
automatically resolve these.

```python
class ReadingBot(MicroBot):
    """
    A bot specialized in reading and comprehending code.

    Extends `MicroBot` with read-only permissions.
    See `Mount` for folder configuration details.
    """
```

In standalone markdown files (guides, blogs), use bracket syntax:

```markdown
See the [MicroBot][microbots.MicroBot.MicroBot] class for details.
Configure folders with [Mount][microbots.extras.mount.Mount].
```

---

## Quick Checklist

Before submitting a PR, verify your docstrings follow these rules:

- [ ] **NumPy style** — Use `Parameters`, `Attributes`, `Returns`, etc. with dashed underlines
- [ ] **Correct indentation** — Parameter names at the same indent as the section header
- [ ] **Type annotations** — Include types in both the signature and the docstring (`name : str`)
- [ ] **All public members documented** — Every public class, method, and function has a docstring
- [ ] **Module-level variables** — Have a docstring on the line immediately after assignment
- [ ] **No bare code blocks** — Descriptions should be prose, not raw code dumps
- [ ] **Cross-references** — Use backticks around class/function names to enable auto-linking

---

## How It Works

1. Each Python module has a corresponding `.md` stub file in `docs/api-reference/` containing only a mkdocstrings directive (e.g., `::: microbots.MicroBot`)
2. During `zensical build`, mkdocstrings reads the source code and docstrings
3. It generates fully rendered HTML documentation with class hierarchies, parameter tables, source code links, and cross-references
4. The CI pipeline in `.github/workflows/pages.yml` auto-generates stub files for any new Python modules before building
