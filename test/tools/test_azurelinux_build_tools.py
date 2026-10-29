"""Integration test: the Azure Linux build tools install in an Azure Linux sandbox with sudo access.

Requires Docker and network access (the stock AZURELINUX_IMAGE is prepared on
the fly, then the tools download packages and build azldev), so it is marked
slow.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from microbots.environment.local_docker.LocalDockerEnvironment import LocalDockerEnvironment
from microbots.environment.local_docker.images import AZURELINUX_IMAGE
from microbots.tools.tool_yaml_parser import parse_tool_definition
from microbots.utils.network import get_free_port


@pytest.mark.integration
@pytest.mark.docker
@pytest.mark.slow
def test_rpm_mock_and_azldev_install_on_azurelinux():
    env = LocalDockerEnvironment(port=get_free_port(), image=AZURELINUX_IMAGE, sudo_access=True)
    try:
        for name in ("rpm.yaml", "mock.yaml", "azldev.yaml"):
            tool = parse_tool_definition(name)
            tool.install_tool(env)
            tool.verify_tool_installation(env)

        ret = env.execute("azldev --version && mock --version && rpmbuild --version")
        assert ret.return_code == 0, ret.stderr
        assert "azldev version" in ret.stdout
    finally:
        env.stop()
