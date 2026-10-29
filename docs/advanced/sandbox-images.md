# Sandbox Images

Every bot runs its commands inside a Docker sandbox created by `LocalDockerEnvironment`. The sandbox runs an **unmodified image from the Microsoft Container Registry**, and you choose it by passing `image`. Two images have constants in `microbots.environment.local_docker.images`:

| Constant | Image | Use it for |
|----------|-------|------------|
| `DEBIAN_IMAGE` (default) | `mcr.microsoft.com/devcontainers/python:3.11` | General work. Debian with Python and a full developer toolset. |
| `AZURELINUX_IMAGE` | `mcr.microsoft.com/azurelinux/base/core:3.0` | Azure Linux and RPM work. Its `tdnf` repos package `mock`, `rpm-build`, and `golang`. |

## How a stock image becomes a sandbox

There is no custom image to build. When an environment starts, Microbots:

1. Starts the image idle.
2. Copies its shell server (`local_docker/shell_server`) into `/opt/microbots`, owned by root.
3. Runs `shell_server/prepare.sh` as root. It installs anything missing (Python, `useradd`, `mount`, `git`) with `apt-get`, `tdnf`, `dnf`, or `yum`. It also creates the unprivileged `agent` account, removes the devcontainer's passwordless-sudo `vscode` user, and installs the server's dependencies (FastAPI, uvicorn, pydantic) into a root-owned venv.
4. Starts the shell server, which drops to the `agent` account before running any bot command.

Preparation needs network access for package and PyPI downloads. It takes about 10 seconds on `DEBIAN_IMAGE` and about 40 seconds on `AZURELINUX_IMAGE`, which also installs Python and the user tools.

## Choose an image

Pass `image` to any bot or to `LocalDockerEnvironment`:

```python
from microbots import WritingBot
from microbots.environment.local_docker.images import AZURELINUX_IMAGE

bot = WritingBot(
    model="azure-openai/your-deployment",
    folder_to_mount="/path/to/repo",
    image=AZURELINUX_IMAGE,
)
```

```python
from microbots.environment.local_docker.LocalDockerEnvironment import LocalDockerEnvironment

env = LocalDockerEnvironment(port=8080, image="mcr.microsoft.com/devcontainers/base:debian")
```

- Any image works if it has `sh` and `bash`, plus either `python3` or one of the supported package managers. Images that already include the prerequisites start faster.
- A bot's `image` only applies to the environment the bot creates. If you pass your own `environment`, choose the image when you create it; passing both raises `ValueError`.

## Tools and distros

You never declare the sandbox's distribution. Tools read it from the running container's `/etc/os-release` and pick their [distro-specific commands](tools/tesseract_ocr_tool_use.md#distro-specific-commands) from it. A tool that only defines `debian` commands, such as `cscope` or `browser-use`, fails to install on the Azure Linux image with `UnsupportedDistroError`.

## Sudo access

By default the sandbox shell drops to an unprivileged `agent` account that has your host user's uid, and the container blocks privilege escalation (`no-new-privileges`). Some tools, such as `mock`, need root for part of their work. Pass `sudo_access=True` to any bot or to `LocalDockerEnvironment` to give the agent passwordless `sudo`:

```python
bot = WritingBot(
    model="azure-openai/your-deployment",
    folder_to_mount="/path/to/repo",
    image=AZURELINUX_IMAGE,
    sudo_access=True,
)
```

- The agent's commands still run as your uid unless it explicitly uses `sudo`, so files it writes in a `READ_WRITE` mount stay owned by you. Files it writes through `sudo` are owned by root and are left that way.
- `sudo_access` applies to the environment the bot creates. If you pass your own `environment`, create it with `LocalDockerEnvironment(..., sudo_access=True)`.
- The container is started without `no-new-privileges`, so `sudo` and setuid helpers (such as `mock`'s launcher) work. If `sudo` doesn't work in the image, the environment fails to start with a `RuntimeError`.

!!! warning
    Sudo access turns the sandbox into a guardrail rather than an isolation boundary. Through `sudo` the agent has root with the container's `SYS_ADMIN` capability and AppArmor unconfined, so it can mount filesystems and reach host-wide kernel interfaces (for example `core_pattern` or a cgroup `release_agent`). A misbehaving or prompt-injected agent could therefore remount a `READ_ONLY` mount as writable, or gain root on the host. A `READ_ONLY` mount still works for a cooperative agent, and its changes are discarded with the sandbox. Enable sudo access only for trusted tasks and trusted repositories, skills, and instructions.
