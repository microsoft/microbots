#!/bin/sh
# Prepare a stock image to host the Microbots shell server.
#
# LocalDockerEnvironment copies this directory to /opt/microbots/shell_server
# and runs this script as root before starting dockerShell.py. It is
# idempotent, so images that already provide everything start faster.
set -eu

MICROBOTS_HOME=/opt/microbots
AGENT_USER=agent
AGENT_UID="${AGENT_UID:-1001}"
AGENT_GID="${AGENT_GID:-1001}"
# 1 = give the agent passwordless sudo (LocalDockerEnvironment(sudo_access=True)).
AGENT_SUDO="${AGENT_SUDO:-0}"

log() { echo "[microbots-prepare] $*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---- Packages the server and the privilege drop need, installed only if missing.
missing=""
have python3 || missing="$missing python3"
{ have useradd && have usermod && have groupmod; } || missing="$missing shadow"
have mount || missing="$missing mount"
have git || missing="$missing git"
python3 -c "import venv, ensurepip" >/dev/null 2>&1 || missing="$missing venv"
if [ "$AGENT_SUDO" = 1 ] && ! have sudo; then missing="$missing sudo"; fi

if [ -n "$missing" ]; then
    log "installing:$missing"
    pkgs=""
    if have apt-get; then
        for m in $missing; do case $m in
            python3|venv) pkgs="$pkgs python3 python3-venv";;
            shadow) pkgs="$pkgs passwd";;
            mount) pkgs="$pkgs mount";;
            git) pkgs="$pkgs git";;
            sudo) pkgs="$pkgs sudo";;
        esac; done
        # Stale third-party sources with expired keys would break apt-get update.
        rm -f /etc/apt/sources.list.d/yarn.list
        apt-get update -qq
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
            $pkgs ca-certificates >/dev/null
    elif have tdnf || have dnf || have yum; then
        pm=$(command -v tdnf || command -v dnf || command -v yum)
        for m in $missing; do case $m in
            python3|venv) pkgs="$pkgs python3 python3-pip";;
            shadow) pkgs="$pkgs shadow-utils";;
            mount) pkgs="$pkgs util-linux";;
            git) pkgs="$pkgs git";;
            sudo) pkgs="$pkgs sudo";;
        esac; done
        "$pm" install -y $pkgs ca-certificates >/dev/null
    else
        # Unknown distro: carry on and let the first command that needs a
        # missing tool report the failure.
        log "no supported package manager (apt-get, tdnf, dnf, yum) to install:$missing"
    fi
fi

# ---- Agent account. Other non-root accounts holding the agent's uid/gid are
# removed so the agent cannot inherit them, along with devcontainer images'
# passwordless-sudo 'vscode' user.
remove_user() {
    log "removing user $1"
    userdel -r "$1" >/dev/null 2>&1 || userdel "$1"
    rm -f "/etc/sudoers.d/$1"
}
id vscode >/dev/null 2>&1 && remove_user vscode
while IFS=: read -r name _ uid _; do
    if [ "$uid" = "$AGENT_UID" ] && [ "$name" != "$AGENT_USER" ] && [ "$uid" != 0 ]; then
        remove_user "$name"
    fi
done < /etc/passwd
while IFS=: read -r name _ gid _; do
    if [ "$gid" = "$AGENT_GID" ] && [ "$name" != "$AGENT_USER" ] && [ "$gid" != 0 ]; then
        log "removing group $name"
        groupdel "$name" || log "could not remove group $name"
    fi
done < /etc/group
if ! id "$AGENT_USER" >/dev/null 2>&1; then
    getent group "$AGENT_USER" >/dev/null || groupadd -g "$AGENT_GID" "$AGENT_USER"
    useradd -m -u "$AGENT_UID" -g "$AGENT_USER" -s /bin/bash "$AGENT_USER"
fi
mkdir -p /var/log/microbots

# ---- Optional passwordless sudo for the agent. Commands still run as the
# host uid unless the agent explicitly uses sudo.
if [ "$AGENT_SUDO" = 1 ]; then
    mkdir -p /etc/sudoers.d
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$AGENT_USER" > /etc/sudoers.d/microbots-agent
    chmod 0440 /etc/sudoers.d/microbots-agent
    # Some images (e.g. Azure Linux) ship /etc/shadow with mode 0000, which
    # sudo's PAM account check cannot read inside a container.
    if [ -f /etc/shadow ]; then chmod u+r /etc/shadow; fi
fi

# Bind-mounted repos are owned by the host user, not whoever runs inside the
# container, which trips git's "dubious ownership" safety check.
if have git && ! git config --system --get-all safe.directory 2>/dev/null | grep -qx '\*'; then
    git config --system --add safe.directory '*'
fi

# ---- Root-owned venv with the server's dependencies, isolated from the
# agent's Python. Root ownership also keeps the bot from patching its server.
if ! "$MICROBOTS_HOME/venv/bin/python" -c "import fastapi, uvicorn, pydantic" >/dev/null 2>&1; then
    log "creating $MICROBOTS_HOME/venv"
    python3 -m venv "$MICROBOTS_HOME/venv"
    "$MICROBOTS_HOME/venv/bin/pip" install --no-cache-dir --disable-pip-version-check -q \
        fastapi uvicorn pydantic
fi
log "ready"
