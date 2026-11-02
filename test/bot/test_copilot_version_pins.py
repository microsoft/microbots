"""
Keep the github-copilot-sdk pin (``ghcp`` extra in pyproject.toml) and the
copilot-cli pin (copilot-cli.yaml) in step: each SDK release targets one CLI
version, recorded as ``CLI_VERSION`` in the SDK's ``copilot/_cli_version.py``.
"""

import re
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_CLI_YAML = _REPO_ROOT / "src/microbots/tools/tool_definitions/copilot-cli.yaml"


def _sdk_pin() -> str:
    extras = tomllib.loads(_PYPROJECT.read_text())["project"]["optional-dependencies"]
    (requirement,) = extras["ghcp"]
    match = re.fullmatch(r"github-copilot-sdk==(\d+\.\d+\.\d+)", requirement)
    assert match, f"ghcp extra must pin an exact github-copilot-sdk version, got {requirement!r}"
    return match.group(1)


def _cli_pins() -> set[str]:
    install_commands = yaml.safe_load(_CLI_YAML.read_text())["install_commands"]
    pins = set()
    for commands in install_commands.values():
        for command in commands:
            pins.update(re.findall(r"@github/copilot@(\S+)", command))
    return pins


@pytest.mark.unit
def test_sdk_and_cli_are_pinned_to_exact_versions():
    _sdk_pin()
    pins = _cli_pins()
    assert len(pins) == 1, f"every distro must install the same copilot-cli version, got {pins}"
    assert re.fullmatch(r"\d+\.\d+\.\d+", pins.pop())


@pytest.mark.ghcp
def test_installed_sdk_matches_pins():
    try:
        sdk = distribution("github-copilot-sdk")
    except PackageNotFoundError:
        pytest.skip("github-copilot-sdk not installed (pip install microbots[ghcp])")

    assert sdk.version == _sdk_pin()
    cli_version_file = Path(sdk.locate_file("copilot/_cli_version.py"))
    match = re.search(r'^CLI_VERSION\b[^=\n]*=\s*"([^"]+)"', cli_version_file.read_text(), re.M)
    assert match, f"CLI_VERSION not found in {cli_version_file}"
    assert _cli_pins() == {match.group(1)}, (
        f"github-copilot-sdk {sdk.version} targets copilot-cli {match.group(1)}; "
        "update the @github/copilot pin in copilot-cli.yaml"
    )
