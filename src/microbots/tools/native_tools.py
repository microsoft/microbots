"""Tools the LLM calls natively through tool calling instead of writing commands as text.

Each tool is defined in a YAML file under ``tool_definitions/`` whose
``parameters`` field is the JSON schema of the tool arguments. Each LLM
client converts these definitions to its provider's format. MicroBot runs
``run_command`` like any other command; the file tools are run here, through the
sandbox shell, so they have the same permissions as the bot's commands.
"""
import base64
import posixpath
import shlex

from microbots.environment.Environment import CmdReturn, Environment
from microbots.tools.tool_yaml_parser import parse_tool_definition

# Runs plain shell commands, so it works for every provider that calls tools.
RUN_COMMAND_TOOL = parse_tool_definition("run_command.yaml")

OPENAI_NATIVE_TOOLS = [RUN_COMMAND_TOOL] + [
    parse_tool_definition(f"{name}.yaml")
    for name in ("view_file", "create_file", "str_replace")
]


def run_file_tool(name: str, arguments: dict, env: Environment) -> CmdReturn:
    """
    Run a file tool call in the sandbox.

    Parameters
    ----------
    name : str
        The tool name: ``view_file``, ``create_file`` or ``str_replace``.
    arguments : dict
        The arguments of the call, matching the tool's JSON schema.
    env : Environment
        The sandbox to run the tool in.

    Returns
    -------
    CmdReturn
        The tool output, or an error with a non-zero return code.
    """
    handlers = {
        "view_file": view_file,
        "create_file": create_file,
        "str_replace": str_replace,
    }
    if name not in handlers:
        return _error(f"Unknown tool: {name}")
    try:
        return handlers[name](env, **arguments)
    except ValueError as e:
        return _error(str(e))


def view_file(env: Environment, path: str, start_line: int | None, end_line: int | None) -> CmdReturn:
    """
    Show a file, or a range of its lines, with line numbers.

    Parameters
    ----------
    env : Environment
        The sandbox that holds the file.
    path : str
        Path of the file in the sandbox.
    start_line : int | None
        First line to show, counting from 1, or None to start at the first line.
    end_line : int | None
        Last line to show, inclusive, or None to show up to the last line.

    Returns
    -------
    CmdReturn
        The numbered lines.
    """
    lines = _read_file(env, path).splitlines()
    start = max(start_line or 1, 1)
    end = end_line or len(lines)
    numbered = [f"{number:6}\t{line}" for number, line in enumerate(lines[start - 1:end], start)]
    return CmdReturn(stdout="\n".join(numbered), stderr="", return_code=0)


def create_file(env: Environment, path: str, content: str) -> CmdReturn:
    """
    Create or overwrite a file.

    Parameters
    ----------
    env : Environment
        The sandbox to write the file in.
    path : str
        Path of the file in the sandbox.
    content : str
        The full content of the file.

    Returns
    -------
    CmdReturn
        A confirmation message.
    """
    _write_file(env, path, content)
    return CmdReturn(stdout=f"Created {path}", stderr="", return_code=0)


def str_replace(env: Environment, path: str, old_str: str, new_str: str) -> CmdReturn:
    """
    Replace the single occurrence of ``old_str`` in a file with ``new_str``.

    Parameters
    ----------
    env : Environment
        The sandbox that holds the file.
    path : str
        Path of the file in the sandbox.
    old_str : str
        The exact text to replace. It must appear exactly once in the file.
    new_str : str
        The replacement text.

    Returns
    -------
    CmdReturn
        A confirmation message, or an error if ``old_str`` does not appear exactly once.
    """
    content = _read_file(env, path)
    count = content.count(old_str)
    if count != 1:
        return _error(f"old_str must appear exactly once in {path}, but it appears {count} times.")
    _write_file(env, path, content.replace(old_str, new_str))
    return CmdReturn(stdout=f"Edited {path}", stderr="", return_code=0)


# File contents travel base64-encoded so shell quoting can't alter any character.
def _read_file(env: Environment, path: str) -> str:
    """
    Read a UTF-8 text file from the sandbox.

    Parameters
    ----------
    env : Environment
        The sandbox that holds the file.
    path : str
        Path of the file in the sandbox.

    Returns
    -------
    str
        The file content.

    Raises
    ------
    ValueError
        If the file can't be read or isn't UTF-8 text.
    """
    result = env.execute(f"base64 {shlex.quote(path)}")
    if result.return_code != 0:
        raise ValueError(result.stderr.strip() or f"Could not read {path}")
    try:
        return base64.b64decode(result.stdout).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"{path} is not a UTF-8 text file") from None


def _write_file(env: Environment, path: str, content: str) -> None:
    """
    Write a text file in the sandbox, creating missing parent directories.

    Parameters
    ----------
    env : Environment
        The sandbox to write the file in.
    path : str
        Path of the file in the sandbox.
    content : str
        The full content of the file.

    Raises
    ------
    ValueError
        If the file can't be written.
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    directory = posixpath.dirname(path) or "."
    result = env.execute(
        f"mkdir -p {shlex.quote(directory)} && printf '%s' {encoded} | base64 -d > {shlex.quote(path)}"
    )
    if result.return_code != 0:
        raise ValueError(result.stderr.strip() or f"Could not write {path}")


def _error(message: str) -> CmdReturn:
    """
    Build a failed tool result.

    Parameters
    ----------
    message : str
        What went wrong.

    Returns
    -------
    CmdReturn
        A result with the message on stderr and return code 1.
    """
    return CmdReturn(stdout="", stderr=message, return_code=1)
