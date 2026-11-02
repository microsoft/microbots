"""
Integration test: CopilotBot uses a third-party repository's agent skills.

The Azure Linux repository ships ``AGENTS.md`` plus ``azldev-*`` skills under
``.agents/skills``.  This test mounts the checkout into an Azure Linux
sandbox with sudo access (``mock`` needs it), installs the ``rpm``, ``mock`` and ``azldev``
tool definitions, points the Copilot session at the repository's skills via
``session_options`` and asks the agent to upgrade the ``util-linux`` component.

By default the checkout is mounted READ_ONLY: the agent works on an overlay and
its changes are discarded with the sandbox, so the host checkout is unchanged.
Set ``AZURELINUX_KEEP_CHANGES=1`` to mount it READ_WRITE and keep the agent's
changes in the checkout for review.

Prerequisites:
  - Docker daemon, ``pip install microbots[ghcp]``
  - Copilot auth: COPILOT_BYOK_* (see test_copilot_bot.py) or GitHub auth
  - An Azure Linux checkout at ``AZURELINUX_REPO_PATH`` (default /mnt/azurelinux)
  - Network access: the stock Azure Linux image (AZURELINUX_IMAGE) is prepared on
    the fly. Set MICROBOTS_SHELL_IMAGE to try a different image.

Usage:
  pytest test/bot/test_copilot_bot_azurelinux_skills.py -m "integration and ghcp" -v
"""

import logging
import os
import re
import shutil
import subprocess
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from microbots.constants import DOCKER_WORKING_DIR, PermissionLabels
from microbots.environment.local_docker.images import AZURELINUX_IMAGE
from microbots.tools.tool_yaml_parser import parse_tool_definition

logger = logging.getLogger(__name__)

AZURELINUX_REPO = Path(os.environ.get("AZURELINUX_REPO_PATH", "/mnt/azurelinux"))
COMPONENT = "util-linux"
RENDERED_SPEC = f"specs/u/{COMPONENT}/{COMPONENT}.spec"
LOCK_FILE = f"locks/{COMPONENT}.lock"
COMP_DIR = f"base/comps/{COMPONENT}"
KEEP_CHANGES = os.environ.get("AZURELINUX_KEEP_CHANGES", "").strip().lower() in ("1", "true", "yes")

UPGRADE_TASK = f"""
You are working in the Azure Linux repository (your current working directory).
Upgrade the `{COMPONENT}` component to the newest {COMPONENT} version that Fedora
provides upstream (Fedora rawhide). Follow AGENTS.md and use the azldev-* skills
available to you (in particular azldev-comp-toml and azldev-update-component).

Requirements:
- Change only what is needed under {COMP_DIR}/ to pick up the newer upstream
  version, with a TOML comment explaining why.
- Refresh the lock with `azldev comp update -p {COMPONENT}` and re-render with
  `azldev comp render -p {COMPONENT}`.
- Confirm {RENDERED_SPEC} now reports the new Version. If it still shows the old
  Version, fix the component's source resolution (for example the upstream
  snapshot it inherits) and re-run update and render until it does.
- This is an automated validation run on a machine with limited disk space:
  do NOT run `azldev comp build`, mock smoke tests, `git commit` or `git push`.
- Finish with a short summary of the old and new versions and the files you changed.
"""


def _copilot_sdk_installed():
    try:
        from importlib.metadata import version
        version("github-copilot-sdk")
        return True
    except Exception:
        return False


def _copilot_auth_configured():
    if os.environ.get("COPILOT_BYOK_BASE_URL") and os.environ.get("COPILOT_BYOK_PROVIDER_TYPE"):
        return True
    if any(os.environ.get(v) for v in ("COPILOT_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")):
        return True
    if shutil.which("gh"):
        try:
            return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10).returncode == 0
        except Exception:
            pass
    return False


def _docker_available():
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


def _use_real_copilot_sdk():
    """Drop the SDK mocks other test modules install in sys.modules."""
    for key in [k for k in sys.modules if k == "copilot" or k.startswith("copilot.")]:
        del sys.modules[key]
    sys.modules.pop("microbots.bot.CopilotBot", None)


def _spec_version(spec_text: str) -> tuple[int, ...]:
    match = re.search(r"^Version:\s*(\S+)", spec_text, re.MULTILINE)
    assert match, "rendered spec has no Version tag"
    return tuple(int(part) for part in re.findall(r"\d+", match.group(1)))


def _tree_digest(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for rel in paths:
        target = root / rel
        files = sorted(target.rglob("*")) if target.is_dir() else [target]
        for f in files:
            if f.is_file():
                digest.update(str(f.relative_to(root)).encode())
                digest.update(f.read_bytes())
    return digest.hexdigest()


@pytest.mark.skipif(not _copilot_sdk_installed(), reason="github-copilot-sdk not installed (pip install microbots[ghcp])")
@pytest.mark.skipif(not _copilot_auth_configured(), reason="No Copilot auth (COPILOT_BYOK_* or GitHub auth)")
@pytest.mark.skipif(
    not (AZURELINUX_REPO / "AGENTS.md").is_file() or not (AZURELINUX_REPO / ".agents" / "skills").is_dir(),
    reason=f"Azure Linux checkout with AGENTS.md and .agents/skills not found at {AZURELINUX_REPO}",
)
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.docker
@pytest.mark.ghcp
class TestCopilotBotAzureLinuxSkills:
    """CopilotBot follows Azure Linux's AGENTS.md and azldev-* skills end to end."""

    def test_upgrade_util_linux_with_azldev_skills(self):
        _use_real_copilot_sdk()
        from microbots.bot.CopilotBot import CopilotBot

        tracked = [COMP_DIR, LOCK_FILE, f"specs/u/{COMPONENT}"]
        host_digest = _tree_digest(AZURELINUX_REPO, tracked)
        original_version = _spec_version((AZURELINUX_REPO / RENDERED_SPEC).read_text())
        permission = PermissionLabels.READ_WRITE if KEEP_CHANGES else PermissionLabels.READ_ONLY

        sandbox_repo = f"{DOCKER_WORKING_DIR}/{AZURELINUX_REPO.name}"

        bot = CopilotBot(
            model=os.environ.get("COPILOT_BYOK_MODEL", "gpt-4.1"),
            folder_to_mount=str(AZURELINUX_REPO),
            permission=permission,
            image=os.environ.get("MICROBOTS_SHELL_IMAGE", AZURELINUX_IMAGE),
            sudo_access=True,
            additional_tools=[parse_tool_definition(name) for name in ("rpm.yaml", "mock.yaml", "azldev.yaml")],
            session_options={
                "working_directory": sandbox_repo,
                "skill_directories": [f"{sandbox_repo}/.agents/skills"],
            },
        )

        try:
            result = bot.run(UPGRADE_TASK, timeout_in_seconds=2400)
            logger.info("Agent summary:\n%s", result.result)
            assert result.status is True, f"CopilotBot run failed: {result.error}"

            azldev_skills = [s for s in bot.invoked_skills if s.startswith("azldev-")]
            assert azldev_skills, f"No azldev-* skill was invoked (invoked: {bot.invoked_skills})"

            changed = bot.environment.execute(
                f"git -C {sandbox_repo} status --porcelain -- {COMP_DIR} {LOCK_FILE} {RENDERED_SPEC}"
            )
            assert changed.return_code == 0, changed.stderr
            assert LOCK_FILE in changed.stdout, f"Lock was not refreshed:\n{changed.stdout}"
            assert RENDERED_SPEC in changed.stdout, f"Spec was not re-rendered:\n{changed.stdout}"

            spec = bot.environment.execute(f"cat {sandbox_repo}/{RENDERED_SPEC}")
            assert spec.return_code == 0, spec.stderr
            new_version = _spec_version(spec.stdout)
            assert new_version > original_version, (
                f"{COMPONENT} was not upgraded: {original_version} -> {new_version}"
            )
        finally:
            bot.stop()

        if KEEP_CHANGES:
            assert _tree_digest(AZURELINUX_REPO, tracked) != host_digest
            # The agent runs azldev/mock as the host user, so it leaves no root-owned files.
            if os.getuid() != 0:
                root_owned = [
                    p for rel in tracked
                    for p in [AZURELINUX_REPO / rel, *(AZURELINUX_REPO / rel).rglob("*")]
                    if p.exists() and p.lstat().st_uid == 0
                ]
                assert not root_owned, f"Root-owned files left in the checkout: {root_owned[:5]}"
        else:
            # READ_ONLY: every change stayed in the sandbox overlay.
            assert _tree_digest(AZURELINUX_REPO, tracked) == host_digest
