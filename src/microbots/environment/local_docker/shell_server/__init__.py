"""Shell server that runs inside every LocalDockerEnvironment sandbox.

LocalDockerEnvironment copies this directory into a stock container image
when the environment starts, runs ``prepare.sh`` as root to install missing
prerequisites and create the unprivileged ``agent`` account, then starts
``dockerShell.py``.  It exposes a FastAPI endpoint that relays commands to a
persistent bash session managed by ``ShellCommunicator.py``.

The two Python files run inside the container as top-level scripts, so they
must only use the Python standard library plus fastapi, uvicorn and pydantic
(installed by ``prepare.sh`` into a root-owned venv).
"""
