import os
import logging
import subprocess
from typing import Tuple

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from ShellCommunicator import ShellCommunicator

# Configure logging to see all logs including ShellCommunicator
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Ensure logs go to stdout
    ]
)

# Set specific logger levels
logging.getLogger('ShellCommunicator').setLevel(logging.DEBUG)
logging.getLogger('uvicorn').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Must match the account created in the Dockerfile.
AGENT_USER = "agent"
DEFAULT_AGENT_UID = 1001
DEFAULT_AGENT_GID = 1001
AGENT_OWNED_PATHS = ("/home/agent", "/var/log/microbots")


def _align_agent_with_host_user() -> Tuple[int, int]:
    """Re-number the agent account to the host uid so files it writes to the
    bind-mounted working directory stay removable by the host user."""
    uid = int(os.getenv("AGENT_UID") or DEFAULT_AGENT_UID)
    gid = int(os.getenv("AGENT_GID") or DEFAULT_AGENT_GID)

    if (uid, gid) != (DEFAULT_AGENT_UID, DEFAULT_AGENT_GID):
        subprocess.run(["groupmod", "-g", str(gid), AGENT_USER], check=True)
        subprocess.run(["usermod", "-u", str(uid), "-g", str(gid), AGENT_USER], check=True)

    workdir = os.getenv("BOT_WORKDIR")
    for path in AGENT_OWNED_PATHS + ((workdir,) if workdir else ()):
        subprocess.run(["chown", "-R", f"{uid}:{gid}", path], check=False)
    return uid, gid


def _drop_privileges(uid: int, gid: int) -> None:
    """Irreversibly drop this process (and therefore the bot's shell) to the
    agent account. Root work happens over the docker exec control channel."""
    os.setgroups([gid])
    os.setgid(gid)
    os.setuid(uid)
    os.environ.update(HOME="/home/agent", USER=AGENT_USER, LOGNAME=AGENT_USER)
    logger.info("🔻 Dropped to unprivileged user %s (%s:%s)", AGENT_USER, uid, gid)


if os.geteuid() == 0:
    _drop_privileges(*_align_agent_with_host_user())

shell = ShellCommunicator("bash")
shell.start_session()


class Message(BaseModel):
    message: str


app = FastAPI()


@app.post("/")
async def receive_message(message: Message):
    command_output = shell.send_command(message.message)
    return {"status": "success", "output": command_output}


if __name__ == "__main__":
    # Prefer BOT_PORT, else default 8080
    port = int(os.getenv("BOT_PORT") or 8080)
    uvicorn.run(app, host="0.0.0.0", port=port)
