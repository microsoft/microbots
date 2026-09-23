FROM mcr.microsoft.com/devcontainers/python:3.11

WORKDIR /app

# Install required runtime dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Bind-mounted repos are owned by the host user, not whoever runs inside the
# container, which trips git's "dubious ownership" safety check on every git
# command.
RUN git config --system --add safe.directory '*'

# The bot shell runs as this unprivileged account. The devcontainer base image
# ships a 'vscode' user with NOPASSWD sudo, which would hand root straight back.
RUN (userdel -r vscode 2>/dev/null || true) && \
    rm -f /etc/sudoers.d/vscode && \
    groupadd -g 1001 agent && \
    useradd -m -u 1001 -g 1001 -s /bin/bash agent && \
    mkdir -p /var/log/microbots && \
    chown agent:agent /var/log/microbots

# Copy application files. These stay root-owned so the bot cannot patch the
# shell server it talks to.
COPY src/microbots/environment/local_docker/image_builder/dockerShell.py .
COPY src/microbots/environment/local_docker/image_builder/ShellCommunicator.py .

EXPOSE 8080

CMD ["python", "dockerShell.py"]
