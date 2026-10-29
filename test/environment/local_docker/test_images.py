"""Unit tests for the stock image constants and the image preparation script."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from microbots.environment.local_docker import shell_server
from microbots.environment.local_docker.images import AZURELINUX_IMAGE, DEBIAN_IMAGE, DEFAULT_IMAGE

pytestmark = pytest.mark.unit

PREPARE = Path(shell_server.__file__).parent / "prepare.sh"


def test_default_image_is_stock_mcr_debian():
    assert DEFAULT_IMAGE == DEBIAN_IMAGE
    assert DEBIAN_IMAGE.startswith("mcr.microsoft.com/")


def test_azurelinux_image_is_stock_mcr():
    assert AZURELINUX_IMAGE == "mcr.microsoft.com/azurelinux/base/core:3.0"


def test_prepare_script_is_executable_posix_sh():
    assert os.access(PREPARE, os.X_OK)
    assert PREPARE.read_text().startswith("#!/bin/sh\n")


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")
def test_prepare_script_parses():
    subprocess.run(["sh", "-n", str(PREPARE)], check=True)


def test_prepare_script_installs_server_dependencies_into_root_venv():
    text = PREPARE.read_text()
    assert 'python3 -m venv "$MICROBOTS_HOME/venv"' in text
    assert "fastapi uvicorn pydantic" in text
    # The devcontainer image's passwordless-sudo account must not survive.
    assert "remove_user vscode" in text
