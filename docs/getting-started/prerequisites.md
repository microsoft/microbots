# Pre-requisites

In this guide, you will install the two tools every Microbots project needs on your machine. By the end, your laptop will be ready to run any bot safely.

Install   
1. **Python** (the runtime)  
2. **Docker** (the sandboxed execution environment) before running any bot.

!!! note
    You only need Python and Docker installed system-wide on your machine. Microbots itself will be installed into a **project-specific Python virtual environment** in the [next article](project-setup-and-installation.md) — so nothing gets added to your system Python.

## Step 1 — Installing Python

Microbots requires **Python 3.11 or later** (Python 3.13 is supported).

Pick your OS:

| OS          | Install                                                                                                                                                                                                                                                                          |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Linux**   | Ubuntu / Debian:<br><pre><code>sudo apt update && sudo apt install python3 python3-pip python3-venv</code></pre>Fedora:<br><pre><code>sudo dnf install python3 python3-pip</code></pre>                                                                                          |
| **Windows** | Run inside a WSL 2 distribution (e.g. Ubuntu on WSL):<br><pre><code>sudo apt update && sudo apt install python3 python3-pip python3-venv</code></pre>Or use the [official Windows installer](https://www.python.org/downloads/windows/) if you must install on Windows directly. |
| **macOS**   | Use [Homebrew](https://brew.sh/):<br><pre><code>brew install python@3.12</code></pre>Or download from [python.org](https://www.python.org/downloads/macos/).                                                                                                                     |

Verify the installation — run on macOS, WSL on Windows, or Linux:

```bash title="Terminal"
python3 --version
pip3 --version
```

Confirm the version is **at least 3.11**.

## Step 2 — Installing Docker

Pick your OS:

| OS          | Install                                                                                      | Notes                                                                                                                                                                                                                                                                                                              |
| ----------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Linux**   | [Docker Engine installation guide](https://docs.docker.com/engine/install/)                  | After installing, run:<br><pre><code>sudo systemctl enable --now docker<br>sudo usermod -aG docker $USER<br>newgrp docker</code></pre>This starts the daemon, adds your user to the `docker` group, and activates it in the current shell. Without it, bots fail with `PermissionError` on `/var/run/docker.sock`. |
| **Windows** | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) | Enable the **WSL 2 backend** during setup, then run Microbots from inside a WSL 2 Linux distribution (e.g. Ubuntu on WSL). Running bot scripts directly from PowerShell or CMD is **not supported**. A dedicated Windows + WSL guide will be added later.                                                          |
| **macOS**   | [Docker Desktop](https://www.docker.com/products/docker-desktop/)                            | Install and launch it. No extra commands needed.                                                                                                                                                                                                                                                                   |

Verify the installation — run on macOS, WSL on Windows, or Linux:

```bash title="Terminal"
docker --version
docker ps              # should succeed without sudo (on Linux)
docker run hello-world
```

A "Hello from Docker!" message confirms the daemon is reachable.

That's it — with Python and Docker installed, your machine is ready to run Microbots in an isolated sandbox. Continue with the [Project Setup and Microbots Installation](project-setup-and-installation.md) guide to set up your first project.

