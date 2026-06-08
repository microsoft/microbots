import argparse
import logging
import os
import shlex
import shutil
from pathlib import Path
from typing import Optional

from pydantic.dataclasses import dataclass, Field

from microbots.environment.Environment import CmdReturn
from microbots.tools.external_tool import ExternalTool

logger = logging.getLogger("  MemoryTool")


class _NoExitArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises ``ValueError`` instead of calling ``sys.exit``."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise ValueError(message)

INSTRUCTIONS_TO_LLM = """
Use this tool to persist information to files across steps.
All paths must be under /memories/.

MEMORY PROTOCOL:
1. ALWAYS run `memory view /memories` BEFORE doing anything else to check for
   earlier progress.
2. Record status, findings and intermediate results as you go.
3. Before completing a task, save your final results to memory.
4. Keep the memory folder organised  rename or delete stale files.

## Commands

View a file or list a directory:
  memory view <path>
  memory view <path> --start <line> --end <line>

Create a file:
  memory create <path> <content>

Replace a unique string in a file:
  memory str_replace <path> --old "<old_text>" --new "<new_text>"

Insert a line into a file (0 = prepend):
  memory insert <path> --line <line_number> --text "<text>"

Delete a file or directory:
  memory delete <path>

Rename / move a file:
  memory rename <old_path> <new_path>

Clear all memory:
  memory clear

## Examples

  memory view /memories
  memory create /memories/progress.md "## Progress\\n- Found bug in src/foo.py line 42"
  memory str_replace /memories/progress.md --old "line 42" --new "line 45"
  memory insert /memories/progress.md --line 0 --text "# Task Notes"
  memory view /memories/progress.md --start 1 --end 10
  memory delete /memories/old_notes.md
  memory rename /memories/draft.md /memories/final.md

## Notes
- Paths must start with /memories/.
- memory create overwrites if the file already exists.
- memory str_replace requires the old text to appear exactly once.
- In memory view, use --end -1 to read through the end of the file.
"""


@dataclass
class MemoryTool(ExternalTool):
    """
    File-backed memory tool that dispatches through the text command loop and
    works consistently across providers.

    Subclass of ``ExternalTool``  all command lists are empty so
    ``install_tool``, ``setup_tool``, ``verify_tool_installation``, and
    ``uninstall_tool`` are all effective no-ops inherited from ``ExternalTool``.

    All files are stored under ``memory_dir`` on the host (default
    ``~/.microbots/memory``).  The LLM uses paths like ``/memories/notes.md``
    which are resolved relative to ``memory_dir``.
    """

    name: str = Field(default="memory")
    description: str = Field(
        default="File-backed memory store  view, create, edit, delete files under /memories/."
    )
    usage_instructions_to_llm: str = Field(default=INSTRUCTIONS_TO_LLM)
    memory_dir: Optional[str] = Field(default=None)

    def __post_init__(self):
        base = Path(self.memory_dir) if self.memory_dir else Path.home() / ".microbots" / "memory"
        self._memory_dir = base
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._parser = self._build_parser()

    def _build_parser(self) -> _NoExitArgumentParser:
        """Build the argparse parser with subparsers for each memory subcommand."""
        parser = _NoExitArgumentParser(prog="memory", add_help=False)
        subs = parser.add_subparsers(dest="subcommand")

        p_view = subs.add_parser("view", add_help=False)
        p_view.add_argument("path")
        p_view.add_argument("--start", type=int, default=None)
        p_view.add_argument("--end", type=int, default=None)

        p_create = subs.add_parser("create", add_help=False)
        p_create.add_argument("path")
        p_create.add_argument("content", nargs=argparse.REMAINDER)

        p_str = subs.add_parser("str_replace", add_help=False)
        p_str.add_argument("path")
        p_str.add_argument("--old", required=True)
        p_str.add_argument("--new", required=True)

        p_ins = subs.add_parser("insert", add_help=False)
        p_ins.add_argument("path")
        p_ins.add_argument("--line", type=int, required=True)
        p_ins.add_argument("--text", required=True)

        p_del = subs.add_parser("delete", add_help=False)
        p_del.add_argument("path")

        p_ren = subs.add_parser("rename", add_help=False)
        p_ren.add_argument("old_path")
        p_ren.add_argument("new_path")

        subs.add_parser("clear", add_help=False)

        return parser

    # ---------------------------------------------------------------------- #
    # Path helpers
    # ---------------------------------------------------------------------- #

    def _resolve(self, path: str) -> Path:
        """Resolve a /memories/ path to an absolute host path."""
        if not path.startswith("/"):
            raise ValueError(
                f"Invalid memory path: {path!r}. Paths must start with /memories/."
            )

        stripped = path.lstrip("/")

        # Reject any path containing '..' components before resolving
        if ".." in Path(stripped).parts:
            raise ValueError(f"Path traversal not allowed: {path!r}")

        if stripped != "memories" and not stripped.startswith("memories/"):
            raise ValueError(
                f"Invalid memory path: {path!r}. Paths must start with /memories/."
            )

        if stripped == "memories":
            rel = ""
        else:
            rel = stripped[len("memories/"):]

        resolved = (self._memory_dir / rel).resolve() if rel else self._memory_dir.resolve()
        # Use trailing separator to prevent prefix confusion with sibling dirs
        memory_root = str(self._memory_dir.resolve())
        if resolved != self._memory_dir.resolve() and not str(resolved).startswith(memory_root + os.sep):
            raise ValueError(f"Path traversal not allowed: {path!r}")
        return resolved

    # ---------------------------------------------------------------------- #
    # ToolAbstract interface
    # ---------------------------------------------------------------------- #

    def is_invoked(self, command: str) -> bool:
        cmd = command.strip()
        return cmd == "memory" or cmd.startswith("memory ")

    def invoke(self, command: str, parent_bot) -> CmdReturn:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return CmdReturn(stdout="", stderr=f"Parse error: {exc}", return_code=1)

        try:
            args = self._parser.parse_args(tokens[1:])  # skip "memory"
        except ValueError as exc:
            return CmdReturn(stdout="", stderr=str(exc), return_code=1)

        if args.subcommand is None:
            return CmdReturn(stdout="", stderr="Usage: memory <subcommand> ...", return_code=1)

        dispatch = {
            "view": self._view,
            "create": self._create,
            "str_replace": self._str_replace,
            "insert": self._insert,
            "delete": self._delete,
            "rename": self._rename,
        }

        try:
            if args.subcommand == "clear":
                return self._clear()
            return dispatch[args.subcommand](args)
        except (OSError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
            logger.error(" MemoryTool error: %s", exc)
            return CmdReturn(stdout="", stderr=str(exc), return_code=1)

    # ---------------------------------------------------------------------- #
    # Subcommand handlers
    # ---------------------------------------------------------------------- #

    def _view(self, args: argparse.Namespace) -> CmdReturn:
        resolved = self._resolve(args.path)
        if not resolved.exists():
            return CmdReturn(stdout="", stderr=f"Path not found: {args.path!r}", return_code=1)

        if resolved.is_dir():
            items = [
                (f"{item.name}/" if item.is_dir() else item.name)
                for item in sorted(resolved.iterdir())
                if not item.name.startswith(".")
            ]
            result = f"Directory: {args.path}\n" + "\n".join(f"- {i}" for i in items)
            return CmdReturn(stdout=result, stderr="", return_code=0)

        lines = resolved.read_text(encoding="utf-8").splitlines()
        if args.start is not None or args.end is not None:
            s = max(0, (args.start or 1) - 1)
            e = len(lines) if (args.end is None or args.end == -1) else args.end
            lines = lines[s:e]
            base_num = s + 1
        else:
            base_num = 1
        numbered = "\n".join(f"{i + base_num:4d}: {line}" for i, line in enumerate(lines))
        return CmdReturn(stdout=numbered, stderr="", return_code=0)

    def _create(self, args: argparse.Namespace) -> CmdReturn:
        if not args.content:
            return CmdReturn(stdout="", stderr="Usage: memory create <path> <content>", return_code=1)
        content = " ".join(args.content)
        resolved = self._resolve(args.path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        logger.info(" Memory file created: %s", args.path)
        return CmdReturn(stdout=f"File created: {args.path}", stderr="", return_code=0)

    def _str_replace(self, args: argparse.Namespace) -> CmdReturn:
        resolved = self._resolve(args.path)
        if not resolved.is_file():
            return CmdReturn(stdout="", stderr=f"File not found: {args.path!r}", return_code=1)
        content = resolved.read_text(encoding="utf-8")
        count = content.count(args.old)
        if count == 0:
            return CmdReturn(stdout="", stderr=f"Text not found in {args.path!r}", return_code=1)
        if count > 1:
            return CmdReturn(stdout="", stderr=f"Text appears {count} times in {args.path!r} - must be unique", return_code=1)
        resolved.write_text(content.replace(args.old, args.new, 1), encoding="utf-8")
        return CmdReturn(stdout=f"File {args.path} has been edited.", stderr="", return_code=0)

    def _insert(self, args: argparse.Namespace) -> CmdReturn:
        resolved = self._resolve(args.path)
        if not resolved.is_file():
            return CmdReturn(stdout="", stderr=f"File not found: {args.path!r}", return_code=1)
        file_lines = resolved.read_text(encoding="utf-8").splitlines()
        if args.line < 0 or args.line > len(file_lines):
            return CmdReturn(stdout="", stderr=f"Invalid line number {args.line}. Must be 0 - {len(file_lines)}.", return_code=1)
        file_lines.insert(args.line, args.text.rstrip("\n"))
        resolved.write_text("\n".join(file_lines) + "\n", encoding="utf-8")
        return CmdReturn(stdout=f"Text inserted at line {args.line} in {args.path}.", stderr="", return_code=0)

    def _delete(self, args: argparse.Namespace) -> CmdReturn:
        resolved = self._resolve(args.path)
        if resolved == self._memory_dir.resolve():
            return CmdReturn(stdout="", stderr="Cannot delete the /memories root directory", return_code=1)
        if resolved.is_file():
            resolved.unlink()
            logger.info(" Memory file deleted: %s", args.path)
            return CmdReturn(stdout=f"Deleted: {args.path}", stderr="", return_code=0)
        if resolved.is_dir():
            shutil.rmtree(resolved)
            logger.info(" Memory directory deleted: %s", args.path)
            return CmdReturn(stdout=f"Deleted directory: {args.path}", stderr="", return_code=0)
        return CmdReturn(stdout="", stderr=f"Path not found: {args.path!r}", return_code=1)

    def _rename(self, args: argparse.Namespace) -> CmdReturn:
        old_resolved = self._resolve(args.old_path)
        new_resolved = self._resolve(args.new_path)
        memory_root = self._memory_dir.resolve()
        if old_resolved == memory_root:
            return CmdReturn(stdout="", stderr="Cannot rename the /memories root directory", return_code=1)
        if new_resolved == memory_root:
            return CmdReturn(stdout="", stderr="Cannot overwrite the /memories root directory", return_code=1)
        if not old_resolved.exists():
            return CmdReturn(stdout="", stderr=f"Source not found: {args.old_path!r}", return_code=1)
        if new_resolved.exists():
            return CmdReturn(stdout="", stderr=f"Destination already exists: {args.new_path!r}", return_code=1)
        new_resolved.parent.mkdir(parents=True, exist_ok=True)
        old_resolved.rename(new_resolved)
        logger.info(" Memory renamed: %s  %s", args.old_path, args.new_path)
        return CmdReturn(stdout=f"Renamed {args.old_path} to {args.new_path}.", stderr="", return_code=0)

    def _clear(self) -> CmdReturn:
        if self._memory_dir.exists():
            shutil.rmtree(self._memory_dir)
            self._memory_dir.mkdir(parents=True, exist_ok=True)
        logger.info(" Memory cleared.")
        return CmdReturn(stdout="Memory cleared.", stderr="", return_code=0)
