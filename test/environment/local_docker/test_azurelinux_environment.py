"""Integration tests for the stock Azure Linux image (AZURELINUX_IMAGE).

Requires Docker and network access: the image has no Python or user tools,
so LocalDockerEnvironment installs them with tdnf when it starts.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.environment.local_docker.LocalDockerEnvironment import LocalDockerEnvironment
from microbots.environment.local_docker.images import AZURELINUX_IMAGE
from microbots.extras.mount import Mount
from microbots.tools.internal_tool import Tool
from microbots.tools.tool import UnsupportedDistroError
from microbots.tools.tool_yaml_parser import parse_tool_definition
from microbots.utils.network import get_free_port


@pytest.mark.integration
@pytest.mark.docker
class TestAzureLinuxEnvironment:

    @pytest.fixture
    def repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "hello.txt").write_text("hello\n")
        return repo

    @pytest.mark.parametrize("permission", [PermissionLabels.READ_ONLY, PermissionLabels.READ_WRITE])
    def test_unprivileged_shell_with_mount(self, repo, permission):
        env = LocalDockerEnvironment(
            port=get_free_port(),
            image=AZURELINUX_IMAGE,
            folder_to_mount=Mount(str(repo), f"{DOCKER_WORKING_DIR}/repo", permission),
        )
        try:
            assert env.get_distro_ids() == ["azurelinux"]
            ret = env.execute("id -un && pwd && cat hello.txt && echo written > new.txt")
            assert ret.return_code == 0, ret.stderr
            assert ret.stdout.split() == ["agent", f"{DOCKER_WORKING_DIR}/repo", "hello"]
            assert env.execute("tdnf --version").return_code == 0
        finally:
            env.stop()
        # READ_ONLY writes stay in the overlay; READ_WRITE writes reach the host.
        assert (repo / "new.txt").exists() is (permission == PermissionLabels.READ_WRITE)

    def test_distro_specific_tool_commands(self):
        env = LocalDockerEnvironment(port=get_free_port(), image=AZURELINUX_IMAGE)
        try:
            tool = Tool(
                name="jq",
                description="jq",
                usage_instructions_to_llm="jq",
                install_commands={"azurelinux": ["tdnf install -y jq"], "debian": ["apt-get install -y jq"]},
                verify_commands=["jq --version"],
            )
            tool.install_tool(env)
            tool.verify_tool_installation(env)

            with pytest.raises(UnsupportedDistroError):
                parse_tool_definition("cscope.yaml").install_tool(env)
        finally:
            env.stop()
