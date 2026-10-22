"""Integration tests for LocalDockerEnvironment(sudo_access=...) on the stock images.

Requires Docker and network access (the images are prepared on the fly).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.environment.local_docker.LocalDockerEnvironment import LocalDockerEnvironment
from microbots.environment.local_docker.images import AZURELINUX_IMAGE, DEBIAN_IMAGE
from microbots.extras.mount import Mount
from microbots.utils.network import get_free_port

IMAGES = pytest.mark.parametrize("image", [DEBIAN_IMAGE, AZURELINUX_IMAGE], ids=["debian", "azurelinux"])


@pytest.mark.integration
@pytest.mark.docker
class TestSudoAccess:

    @IMAGES
    def test_agent_keeps_host_uid_and_gets_passwordless_sudo(self, tmp_path, image):
        env = LocalDockerEnvironment(
            port=get_free_port(),
            image=image,
            sudo_access=True,
            folder_to_mount=Mount(str(tmp_path), f"{DOCKER_WORKING_DIR}/repo", PermissionLabels.READ_WRITE),
        )
        try:
            ret = env.execute("id -un && id -u && sudo -n id -u && echo written > new.txt")
            assert ret.return_code == 0, ret.stderr
            name, uid, sudo_uid = ret.stdout.split()
            assert name == "agent"
            assert sudo_uid == "0"
            if hasattr(os, "getuid") and os.getuid() != 0:
                assert uid == str(os.getuid())
        finally:
            env.stop()
        # Without sudo, files are written as the host user; no ownership fix-up is needed.
        if hasattr(os, "getuid"):
            assert (tmp_path / "new.txt").stat().st_uid == os.getuid()

    @IMAGES
    def test_no_sudo_by_default(self, image):
        env = LocalDockerEnvironment(port=get_free_port(), image=image)
        try:
            ret = env.execute("sudo -n true")
            assert ret.return_code != 0
        finally:
            env.stop()
