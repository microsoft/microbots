FROM mcr.microsoft.com/devcontainers/python:3.11

WORKDIR /app

# Install required runtime dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Bind-mounted repos are owned by the host user, not whoever runs inside the
# container, which trips git's "dubious ownership" safety check on every git
# command.
RUN git config --system --add safe.directory '*'

# Copy application files
COPY src/microbots/environment/local_docker/image_builder/dockerShell.py .
COPY src/microbots/environment/local_docker/image_builder/ShellCommunicator.py .

EXPOSE 8080

CMD ["python", "dockerShell.py"]
