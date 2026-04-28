# Pre-requisites

### Introduction

Before installing the `microbots` package, you must prepare your machine with the two tools the framework depends on: **Python** for the runtime, and **Docker** for the sandboxed execution environment that isolates every agent command.

In this guide, you will install a supported Python version (3.10 or later, but below 3.13), install Docker, and verify that both tools are available from your terminal. Once you finish, your environment will be ready for the [Microbot Installation](installation-guide.md) guide.

!!! warning "External Links Disclaimer"
    This document contains links to external documentation that may change or be removed over time. All external references were verified at the time of writing and are only considered valid as of the publication date.

## Step 1 — Installing Python

Microbots requires **Python 3.10 or later, but below 3.13** (for example, 3.10, 3.11, or 3.12). Python 3.13 is not yet supported because some `microbots` dependencies have not released 3.13-compatible wheels. In this step, you will install Python and confirm it is on your `PATH`.

Choose the instructions that match your operating system:

- **Windows:** Download the latest installer from [python.org](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"** so that `python` and `pip` are available from any terminal.
- **Linux:** Python is often pre-installed. If it is not, install it using your distribution's package manager:

    ```bash title="Terminal"
    # Ubuntu / Debian
    sudo apt update && sudo apt install python3 python3-pip python3-venv

    # Fedora
    sudo dnf install python3 python3-pip
    ```

    The `python3-venv` package is required on Debian-based systems so you can create isolated virtual environments later.

After installation, verify that Python and `pip` are available:

```bash title="Terminal"
python --version   # or python3 --version on Linux
pip --version      # or pip3 --version on Linux
```

You should see a version that is **at least 3.10 and below 3.13**. If both commands succeed, Python is ready, and you can move on to installing Docker.

## Step 2 — Installing Docker

Microbots runs all agent commands inside Docker containers, which means Docker must be installed and running before any bot can execute. In this step, you will install Docker and verify that the daemon is reachable.

Choose the instructions that match your operating system:

- **Windows / macOS:** Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/). After installation, launch Docker Desktop so that the daemon is running in the background.
- **Linux:** Follow the official [Docker Engine installation guide](https://docs.docker.com/engine/install/) for your distribution. After installation, you must start the Docker daemon and grant your user permission to access the Docker socket — otherwise running a bot will fail with `PermissionError: [Errno 13] Permission denied` on `/var/run/docker.sock`.

    ```bash title="Terminal"
    # Start the Docker daemon now and on every boot
    sudo systemctl enable --now docker

    # Add your user to the docker group so you don't need sudo
    sudo usermod -aG docker $USER

    # Apply the new group in the current shell (alternatively, log out and back in)
    newgrp docker
    ```

After installation, verify that Docker is installed and the daemon is responsive:

```bash title="Terminal"
docker --version
docker ps              # should succeed without sudo
docker run hello-world
```

The first command prints the installed Docker version. `docker ps` confirms your user can talk to the daemon without `sudo`. The last command pulls the `hello-world` image and runs it in a container — if you see a "Hello from Docker!" message, the daemon is reachable.

## Conclusion

In this guide, you installed a supported Python version (3.10 or later, but below 3.13) and Docker, and you confirmed both tools are working from your terminal. Your machine is now ready to install the `microbots` package. Continue with the [Microbot Installation](installation-guide.md) guide to set up your project and configure an LLM provider.

