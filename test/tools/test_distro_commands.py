"""Unit tests for distro-aware tool commands."""

import os
import sys
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from microbots.environment.Environment import CmdReturn, Environment
from microbots.tools.external_tool import ExternalTool
from microbots.tools.internal_tool import Tool
from microbots.tools.tool import GENERIC_COMMANDS_KEY, UnsupportedDistroError
from microbots.tools.tool_yaml_parser import parse_tool_definition
from microbots.utils.os_release import distro_ids, host_distro_ids, parse_os_release

pytestmark = pytest.mark.unit


def _tool(cls=Tool, **commands):
    return cls(name="demo", description="d", usage_instructions_to_llm="u", **commands)


def _ids(*ids):
    return Mock(return_value=list(ids))


class TestResolveCommands:
    def test_list_is_generic_and_skips_distro_lookup(self):
        lookup = _ids("azurelinux")
        assert _tool(install_commands=["a", "b"]).resolve_commands("install", lookup) == ["a", "b"]
        lookup.assert_not_called()

    @pytest.mark.parametrize("value", [None, [], {}])
    def test_empty_or_missing_commands_resolve_to_nothing(self, value):
        tool = _tool(verify_commands=value) if value is not None else _tool()
        assert tool.resolve_commands("verify", _ids("debian")) == []

    def test_exact_id_wins_over_like_and_generic(self):
        tool = _tool(install_commands={"debian": ["apt"], "ubuntu": ["ubuntu-apt"], "generic": ["any"]})
        assert tool.resolve_commands("install", _ids("ubuntu", "debian")) == ["ubuntu-apt"]

    def test_id_like_used_before_generic(self):
        tool = _tool(install_commands={"debian": ["apt"], "generic": ["any"]})
        assert tool.resolve_commands("install", _ids("ubuntu", "debian")) == ["apt"]

    def test_generic_fallback(self):
        tool = _tool(setup_commands={"debian": ["apt"], GENERIC_COMMANDS_KEY: ["any"]})
        assert tool.resolve_commands("setup", _ids("azurelinux")) == ["any"]

    def test_known_distro_without_entry_fails_before_running(self):
        tool = _tool(uninstall_commands={"debian": ["apt"]})
        with pytest.raises(UnsupportedDistroError) as err:
            tool.resolve_commands("uninstall", _ids("azurelinux"))
        message = str(err.value)
        assert "Tool 'demo' has no uninstall commands for distro azurelinux" in message
        assert "['debian']" in message and "Add a 'azurelinux'" in message

    def test_unknown_distro_prefers_generic(self, caplog):
        tool = _tool(install_commands={"debian": ["apt"], "generic": ["any"]})
        with caplog.at_level("WARNING"):
            assert tool.resolve_commands("install", _ids()) == ["any"]
        assert "Could not detect" not in caplog.text

    def test_unknown_distro_tries_first_entry_with_warning(self, caplog):
        tool = _tool(install_commands={"azurelinux": ["tdnf"], "debian": ["apt"]})
        with caplog.at_level("WARNING"):
            assert tool.resolve_commands("install", _ids()) == ["tdnf"]
        assert "Could not detect the distro for tool 'demo'; trying its 'azurelinux' install commands" in caplog.text

    def test_distro_lookup_is_case_insensitive(self):
        tool = _tool(install_commands={" Debian ": ["apt"]})
        assert tool.install_commands == {"debian": ["apt"]}
        assert tool.resolve_commands("install", _ids("DEBIAN")) == ["apt"]

    @pytest.mark.parametrize("bad", [{"": ["x"]}, {"Debian": ["a"], "debian": ["b"]}, {"debian": "apt-get"}, "apt-get"])
    def test_invalid_command_maps_rejected(self, bad):
        with pytest.raises(ValidationError):
            _tool(install_commands=bad)


class FakeEnv(Environment):
    def __init__(self, os_release="ID=ubuntu\nID_LIKE=debian\n", code=0):
        self.privileged = Mock(return_value=CmdReturn(os_release, "", code))
        self.execute = Mock(return_value=CmdReturn("", "", 0))

    def start(self):
        pass

    def stop(self):
        pass

    def execute(self, command, timeout=300, sensitive=False):  # replaced per instance
        raise NotImplementedError

    def execute_privileged(self, command, timeout=300, sensitive=False):
        return self.privileged(command)


class TestEnvironmentDistroIds:
    def test_reads_and_caches_os_release(self):
        env = FakeEnv()
        assert env.get_distro_ids() == ["ubuntu", "debian"]
        assert env.get_distro_ids() == ["ubuntu", "debian"]
        env.privileged.assert_called_once_with("cat /etc/os-release")

    def test_unknown_when_os_release_missing_and_retries_later(self):
        env = FakeEnv(os_release="", code=1)
        assert env.get_distro_ids() == []
        assert env.get_distro_ids() == []
        assert env.privileged.call_count == 2

    def test_internal_tool_installs_distro_commands_and_fails_without_them(self):
        env = FakeEnv(os_release='ID="azurelinux"\n')
        tool = _tool(install_commands={"azurelinux": ["tdnf install -y x"], "debian": ["apt-get install -y x"]})
        tool.install_tool(env)
        assert env.privileged.call_args_list[-1].args == ("tdnf install -y x",)

        debian_only = _tool(install_commands={"debian": ["apt-get install -y x"]})
        calls = env.privileged.call_count
        with pytest.raises(UnsupportedDistroError):
            debian_only.install_tool(env)
        assert env.privileged.call_count == calls  # nothing was run

    @pytest.mark.parametrize("kind, method", [("verify", "verify_tool_installation"), ("setup", "setup_tool")])
    def test_internal_tool_bot_channel_commands_are_resolved(self, kind, method):
        env = FakeEnv(os_release="ID=debian\n")
        tool = _tool(**{f"{kind}_commands": {"debian": ["x --version"], "generic": ["y"]}})
        getattr(tool, method)(env)
        env.execute.assert_called_once_with("x --version")


class TestExternalToolUsesHostDistro:
    def test_resolves_against_host(self):
        tool = _tool(ExternalTool, install_commands={"plan9": ["p9"], "generic": ["echo generic"]})
        with patch("microbots.tools.external_tool.host_distro_ids", return_value=["plan9"]) as host, \
             patch.object(ExternalTool, "_run_host_command", return_value=Mock(returncode=0)) as run:
            tool.install_tool(Mock())
        host.assert_called_once_with()
        run.assert_called_once_with("p9")


class TestOsRelease:
    def test_parse_handles_quotes_comments_and_garbage(self):
        text = '# comment\nNAME="Azure Linux"\nID=azurelinux\nID_LIKE="fedora rhel"\nBROKEN\nBAD="unterminated\n'
        fields = parse_os_release(text)
        assert fields["NAME"] == "Azure Linux"
        assert distro_ids(fields) == ["azurelinux", "fedora", "rhel"]
        assert "BAD" not in fields

    def test_distro_ids_dedupes_and_lowercases(self):
        assert distro_ids({"ID": "Debian", "ID_LIKE": "debian DEBIAN"}) == ["debian"]
        assert distro_ids({}) == []

    def test_host_distro_ids(self):
        with patch("platform.freedesktop_os_release", return_value={"ID": "ubuntu", "ID_LIKE": "debian"}):
            assert host_distro_ids() == ["ubuntu", "debian"]
        with patch("platform.freedesktop_os_release", side_effect=OSError):
            assert host_distro_ids() == []


def test_bundled_apt_tools_are_debian_only():
    for name in ("cscope.yaml", "browser-use.yaml"):
        tool = parse_tool_definition(name)
        assert set(tool.install_commands) == {"debian"}
        with pytest.raises(UnsupportedDistroError):
            tool.resolve_commands("install", lambda: ["azurelinux"])
