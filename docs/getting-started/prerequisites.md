# Pre-requisites

Install **Python** (the runtime) and **Docker** (the sandboxed execution environment) before running any bot.

!!! warning "External Links Disclaimer"
    External references were verified at the time of writing and may change over time.

## Step 1 — Installing Python

Microbots requires **Python 3.10 or later, but below 3.13** (some dependencies lack 3.13-compatible wheels).

On Linux, install Python with your distribution's package manager.

Ubuntu / Debian:

```bash title="Terminal"
sudo apt update && sudo apt install python3 python3-pip python3-venv
```

Fedora:

```bash title="Terminal"
sudo dnf install python3 python3-pip
```

Verify the installation:

```bash title="Terminal"
python3 --version
pip3 --version
```

Confirm the version is **at least 3.10 and below 3.13**.

## Step 2 — Installing Docker

On macOS, install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and launch it.

On Linux, follow the [Docker Engine installation guide](https://docs.docker.com/engine/install/), then enable the daemon and add your user to the `docker` group:

```bash title="Terminal"
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

Without this, bots fail with `PermissionError: [Errno 13] Permission denied` on `/var/run/docker.sock`.

Verify the installation:

```bash title="Terminal"
docker --version
docker ps              # should succeed without sudo
docker run hello-world
```

A "Hello from Docker!" message confirms the daemon is reachable.

Continue with the [Microbot Installation](installation-guide.md) guide.

