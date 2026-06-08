#!/usr/bin/env python3
"""
Parse microbots info.log files into markdown trajectory files.

Usage:
    python multi_agent_log_parser.py <log_file> [output_dir] [--single-file]

Creates either:
    <name>_trajectory/
        main_agent.md
        sub_agent_1.md
        sub_agent_2.md
        ...
Or with --single-file:
    <name>_trajectory.md

The log file name (minus _info.log or .log suffix) determines the output name.
"""

import argparse
import re
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional


#  Data Classes 


@dataclass
class SetupInfo:
    """Captured setup information before the agent starts working."""
    container_id: str = ""
    image: str = ""
    host_port: str = ""
    working_dir: str = ""
    volume_mappings: List[str] = field(default_factory=list)
    tools_installed: List[str] = field(default_factory=list)
    files_copied: List[str] = field(default_factory=list)


@dataclass
class Step:
    """Represents a single step in an agent's execution."""
    number: int
    thought: str = ""
    command: str = ""
    output: str = ""
    is_blocked: bool = False
    blocked_reason: str = ""
    blocked_alternative: str = ""
    is_sub_agent_call: bool = False
    sub_agent_task: str = ""
    sub_agent_index: int = -1  # index into the test case's sub_agents list


@dataclass
class Agent:
    """Represents an agent (main or sub) and its execution steps."""
    task: str = ""
    steps: List[Step] = field(default_factory=list)
    is_main: bool = False
    final_thoughts: str = ""
    completed: bool = False
    max_iterations_reached: bool = False
    error_message: str = ""


@dataclass
class TestCase:
    """Represents a single test case with a main agent and sub-agents."""
    name: str = ""
    main_agent: Optional[Agent] = None
    sub_agents: List[Agent] = field(default_factory=list)
    setup: SetupInfo = field(default_factory=SetupInfo)


#  Log Parsing 

# Format: TIMESTAMP MODULE LEVEL CONTENT
# e.g. "2026-03-26 12:45:20,277 microbots.environment.local_docker.LocalDockerEnvironment INFO ..."
# e.g. "2026-03-26 12:46:35,819  MicroBot  INFO    TASK STARTED : ..."
# e.g. "2026-03-26 12:49:30,653   MicroBot-Sub INFO Sub-agent completed..."
LOG_LINE_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+(.*?)\s+(INFO|ERROR|WARNING|DEBUG)\s(.*)$'
)

# Legacy format: TIMESTAMP [LEVEL] CONTENT
LOG_LINE_LEGACY_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \[(INFO|ERROR|WARNING|DEBUG)\] (.*)$'
)


def parse_log_entries(log_path: str) -> List[dict]:
    """
    Parse a log file into a list of entries.
    Multi-line log entries (continuation lines without timestamps) are joined.
    Supports both the current log format (TIMESTAMP MODULE LEVEL CONTENT) and
    the legacy format (TIMESTAMP [LEVEL] CONTENT).

    Returns a list of dicts:
        {'timestamp': str, 'level': str, 'module': str, 'content': str, 'line_num': int}
    """
    entries = []
    current_entry = None

    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.rstrip('\n')

            # Try current format first, then legacy
            match = LOG_LINE_RE.match(line)
            if match:
                if current_entry is not None:
                    entries.append(current_entry)
                current_entry = {
                    'timestamp': match.group(1),
                    'module': match.group(2).strip(),
                    'level': match.group(3),
                    'content': match.group(4),
                    'line_num': line_num,
                }
            else:
                legacy = LOG_LINE_LEGACY_RE.match(line)
                if legacy:
                    if current_entry is not None:
                        entries.append(current_entry)
                    current_entry = {
                        'timestamp': legacy.group(1),
                        'module': '',
                        'level': legacy.group(2),
                        'content': legacy.group(3),
                        'line_num': line_num,
                    }
                else:
                    # Continuation of previous entry
                    if current_entry is not None:
                        current_entry['content'] += '\n' + line

    if current_entry is not None:
        entries.append(current_entry)

    return entries


#  Structure Building 


def extract_task_from_microbot_sub(command: str) -> str:
    """Extract the --task argument from a microbot_sub command."""
    normalized = command.replace('\\"', '"').replace('\\n', '\n')

    match = re.search(r'--task\s+"(.*?)"\s+--(?:iterations|timeout)', normalized, re.DOTALL)
    if match:
        return match.group(1).strip()

    match = re.search(r'--task\s+"(.*?)"\s*$', normalized, re.DOTALL)
    if match:
        return match.group(1).strip()

    match = re.search(r"--task\s+'(.*?)'\s+--(?:iterations|timeout)", normalized, re.DOTALL)
    if match:
        return match.group(1).strip()

    match = re.search(r'--task\s+"(.+)', normalized, re.DOTALL)
    if match:
        text = match.group(1)
        iter_match = re.search(r'"\s+--(?:iterations|timeout)', text)
        if iter_match:
            return text[:iter_match.start()].strip()
        quote_end = text.rfind('"')
        if quote_end > 0:
            return text[:quote_end].strip()
        return text.strip()
    return command


def _extract_setup_info(entries: List[dict]) -> SetupInfo:
    """Extract environment setup information from log entries before the first TASK STARTED."""
    setup = SetupInfo()
    for entry in entries:
        content = entry['content']
        if 'TASK STARTED' in content:
            break

        # Container start
        m = re.search(r'Started container (\w+) with image (\S+) on host port (\d+)', content)
        if m:
            setup.container_id = m.group(1)
            setup.image = m.group(2)
            setup.host_port = m.group(3)
            continue

        # Working directory
        m = re.search(r'Created working directory at (\S+)', content)
        if m:
            setup.working_dir = m.group(1)
            continue

        # Volume mapping
        if 'Volume mapping:' in content:
            setup.volume_mappings.append(content.split('Volume mapping:', 1)[1].strip())
            continue

        # Tool installed
        m = re.search(r'Successfully (?:installed|set up|setup) (?:external )?tool:\s*(\S+)', content)
        if m:
            tool_name = m.group(1)
            if tool_name not in setup.tools_installed:
                setup.tools_installed.append(tool_name)
            continue

        # Files copied to container
        m = re.search(r'Successfully copied (.+?) to container:(.+)', content)
        if m:
            setup.files_copied.append(f"{m.group(1).strip()}  {m.group(2).strip()}")
            continue

    return setup


def build_test_cases(entries: List[dict]) -> List[TestCase]:
    """
    Walk through log entries and build a list of TestCase objects,
    each containing a main agent and its sub-agents.
    """
    test_cases = []
    current_test: Optional[TestCase] = None

    agent_stack: List[Agent] = []
    current_step: Optional[Step] = None
    pending_sub_agent_step: Optional[Step] = None
    current_field: Optional[str] = None

    def current_agent() -> Optional[Agent]:
        return agent_stack[-1] if agent_stack else None

    def finalize_test_case():
        nonlocal current_test, agent_stack, current_step, pending_sub_agent_step, current_field
        if current_test and current_test.main_agent:
            test_cases.append(current_test)
        current_test = None
        agent_stack = []
        current_step = None
        pending_sub_agent_step = None
        current_field = None

    for entry in entries:
        content = entry['content']
        level = entry['level']

        #  Skip noise 
        if 'HTTP Request:' in content:
            continue
        if content.startswith('The llm response is'):
            continue

        #  Test case boundary 
        test_dir_match = re.search(r'Test directory set up at:\s*\S+/(\S+)', content)
        if test_dir_match:
            finalize_test_case()
            test_name = test_dir_match.group(1)
            current_test = TestCase(name=test_name)
            continue

        #  Task started 
        if 'TASK STARTED' in content:
            task_text = content.split('TASK STARTED', 1)[1].lstrip(' :').strip()
            new_agent = Agent(task=task_text)

            if not current_test:
                current_test = TestCase(name="unknown")

            if not current_test.main_agent:
                new_agent.is_main = True
                current_test.main_agent = new_agent
                agent_stack = [new_agent]
            else:
                if pending_sub_agent_step and pending_sub_agent_step.sub_agent_task:
                    new_agent.task = pending_sub_agent_step.sub_agent_task
                elif task_text:
                    new_agent.task = task_text

                sub_idx = len(current_test.sub_agents)
                current_test.sub_agents.append(new_agent)

                if pending_sub_agent_step:
                    pending_sub_agent_step.sub_agent_index = sub_idx
                    pending_sub_agent_step = None

                agent_stack.append(new_agent)

            current_step = None
            current_field = None
            continue

        #  Task completed 
        if 'TASK COMPLETED' in content:
            agent = current_agent()
            if agent:
                agent.completed = True
            current_field = None
            continue

        #  Sub-agent completed message 
        if 'Sub-agent completed successfully with output:' in content:
            if len(agent_stack) > 1:
                agent_stack.pop()
            current_step = None
            current_field = None
            continue

        #  Sub-agent failed 
        if level == 'ERROR' and 'Sub-agent failed' in content:
            agent = current_agent()
            if agent and not agent.is_main:
                agent.max_iterations_reached = True
                agent.completed = False
                agent.error_message = content
            if len(agent_stack) > 1:
                agent_stack.pop()
            current_step = None
            current_field = None
            continue

        #  Failed to parse sub-agent command 
        if level == 'ERROR' and 'Failed to parse microbot_sub command' in content:
            if current_step:
                current_step.is_blocked = True
                current_step.blocked_reason = content
            pending_sub_agent_step = None
            current_field = None
            continue

        #  Max iterations reached 
        if level == 'ERROR' and 'Max iterations' in content:
            agent = current_agent()
            if agent:
                agent.max_iterations_reached = True
            continue

        #  Step boundary 
        step_match = re.search(r'-+ Step-(\d+) -+', content)
        if step_match:
            step_num = int(step_match.group(1))
            current_step = Step(number=step_num)
            agent = current_agent()
            if agent:
                agent.steps.append(current_step)
            current_field = None
            continue

        #  LLM final thoughts 
        if 'LLM final thoughts:' in content:
            text = content.split('LLM final thoughts:', 1)[1].strip()
            agent = current_agent()
            if agent:
                agent.final_thoughts = text
            current_field = 'final_thoughts'
            continue

        #  LLM thoughts 
        if 'LLM thoughts:' in content and 'final' not in content.split('LLM thoughts:')[0].lower():
            text = content.split('LLM thoughts:', 1)[1].strip()
            if current_step:
                current_step.thought = text
            current_field = 'thought'
            continue

        #  LLM tool call 
        if 'LLM tool call' in content and ':' in content.split('LLM tool call')[1]:
            cmd = content.split('LLM tool call', 1)[1].split(':', 1)[1].strip()
            if cmd.startswith('"') and cmd.endswith('"'):
                cmd = cmd[1:-1]
            if current_step:
                current_step.command = cmd
                if 'microbot_sub' in cmd:
                    current_step.is_sub_agent_call = True
                    current_step.sub_agent_task = extract_task_from_microbot_sub(cmd)
                    pending_sub_agent_step = current_step
            current_field = 'command'
            continue

        #  Command output 
        if 'Command output:' in content:
            text = content.split('Command output:', 1)[1].strip()
            if current_step:
                current_step.output = text
            current_field = 'output'
            continue

        #  Dangerous command blocked 
        if 'Dangerous command detected' in content:
            if current_step:
                current_step.is_blocked = True
                # Parse REASON/ALTERNATIVE from multi-line content
                lines = content.split('\n')
                current_step.blocked_reason = lines[0]
                for bline in lines[1:]:
                    if bline.startswith('REASON:'):
                        current_step.blocked_reason = bline
                    elif bline.startswith('ALTERNATIVE:'):
                        current_step.blocked_alternative = bline
            current_field = 'blocked'
            continue

        #  REASON / ALTERNATIVE for blocked commands (separate entries) 
        if current_field == 'blocked' and current_step:
            if content.startswith('REASON:'):
                current_step.blocked_reason = content
            elif content.startswith('ALTERNATIVE:'):
                current_step.blocked_alternative = content
            continue

        #  Invoking MicroBotSubAgent 
        if 'Invoking MicroBotSubAgent with task:' in content:
            continue

        #  Memory tool operations 
        if 'Memory file created:' in content or 'Memory file updated:' in content:
            continue

        #  Multi-line continuation for known fields 
        if current_field == 'output' and current_step:
            if current_step.output:
                current_step.output += '\n' + content
            else:
                current_step.output = content
            continue

        if current_field == 'thought' and current_step:
            if current_step.thought:
                current_step.thought += '\n' + content
            else:
                current_step.thought = content
            continue

        if current_field == 'command' and current_step:
            if current_step.command:
                current_step.command += '\n' + content
            else:
                current_step.command = content
            continue

        if current_field == 'final_thoughts':
            agent = current_agent()
            if agent:
                if agent.final_thoughts:
                    agent.final_thoughts += '\n' + content
                else:
                    agent.final_thoughts = content
            continue

    finalize_test_case()
    return test_cases


#  Markdown Generation 


def truncate_text(text: str, max_lines: int = 200) -> str:
    """Truncate text if it exceeds max_lines."""
    lines = text.split('\n')
    if len(lines) > max_lines:
        return '\n'.join(lines[:max_lines]) + f'\n\n... ({len(lines) - max_lines} more lines truncated)'
    return text


def generate_setup_md(setup: SetupInfo) -> str:
    """Generate markdown for the setup/environment section."""
    if not setup.container_id and not setup.tools_installed:
        return ""

    md = "##  Environment Setup\n\n"

    if setup.container_id:
        md += f"- **Container:** `{setup.container_id}` (image: `{setup.image}`, port: {setup.host_port})\n"
    if setup.working_dir:
        md += f"- **Working directory:** `{setup.working_dir}`\n"
    for vol in setup.volume_mappings:
        md += f"- **Volume:** {vol}\n"

    if setup.tools_installed:
        md += f"- **Tools:** {', '.join(setup.tools_installed)}\n"

    if setup.files_copied:
        md += "\n<details>\n<summary>Files copied to container</summary>\n\n"
        for fc in setup.files_copied:
            md += f"- {fc}\n"
        md += "\n</details>\n"

    md += "\n---\n\n"
    return md


def generate_step_md(step: Step, sub_agent_filename: str = "", heading_level: int = 3) -> str:
    """Generate markdown for a single step as a collapsible details section."""
    status = " Blocked" if step.is_blocked else ""
    if step.is_sub_agent_call:
        status = " Sub-Agent Call"

    summary = f"Step {step.number}"
    if status:
        summary += f"  {status}"

    if step.thought:
        first_line = step.thought.split('\n')[0]
        if len(first_line) > 120:
            first_line = first_line[:117] + "..."
        summary += f": {first_line}"

    h = '#' * heading_level

    md = f"<details>\n<summary><strong>{summary}</strong></summary>\n\n"

    if step.thought:
        md += f"{h}  Thought\n\n"
        md += f"{step.thought}\n\n"

    if step.is_blocked:
        md += f"{h}  Command Blocked\n\n"
        if step.blocked_reason:
            md += f"> {step.blocked_reason}\n"
        if step.blocked_alternative:
            md += f"> {step.blocked_alternative}\n"
        md += "\n"

    if step.command:
        md += f"{h}  Command\n\n"
        if step.is_sub_agent_call:
            md += "**Sub-agent invocation:**\n\n"
            if sub_agent_filename:
                md += f" **[View Sub-Agent Trajectory]({sub_agent_filename})**\n\n"
            if step.sub_agent_task:
                md += "<details>\n<summary>Sub-agent task description</summary>\n\n"
                md += f"```\n{step.sub_agent_task}\n```\n\n"
                md += "</details>\n\n"
        else:
            md += f"```bash\n{step.command}\n```\n\n"

    if step.output:
        md += f"{h}  Output\n\n"
        output_text = truncate_text(step.output)
        md += f"```\n{output_text}\n```\n\n"

    md += "</details>\n\n"
    return md


def _agent_status_str(agent: Agent) -> str:
    if agent.completed:
        return " Completed"
    if agent.max_iterations_reached:
        return " Failed (max iterations / timeout)"
    return " Unknown"


def generate_main_agent_md(test_case: TestCase) -> str:
    """Generate the main agent markdown file content."""
    md = f"#  Agent Trajectory: {test_case.name}\n\n"

    md += generate_setup_md(test_case.setup)

    if test_case.main_agent and test_case.main_agent.task:
        md += "## Task\n\n"
        task_text = test_case.main_agent.task
        if len(task_text) > 500:
            md += f"<details>\n<summary>Full task description</summary>\n\n{task_text}\n\n</details>\n\n"
        else:
            md += f"{task_text}\n\n"

    md += "---\n\n"
    md += "## Steps\n\n"

    if test_case.main_agent:
        agent = test_case.main_agent
        for step in agent.steps:
            sub_agent_file = ""
            if step.is_sub_agent_call and step.sub_agent_index >= 0:
                sub_agent_file = f"sub_agent_{step.sub_agent_index + 1}.md"
            md += generate_step_md(step, sub_agent_filename=sub_agent_file)

        md += "---\n\n"

        if agent.completed:
            md += "##  Task Completed\n\n"
            if agent.final_thoughts:
                md += f"{agent.final_thoughts}\n\n"
        elif agent.max_iterations_reached:
            md += "##  Max Iterations Reached\n\n"
            md += "The agent did not complete the task within the maximum allowed iterations.\n\n"

        if test_case.sub_agents:
            md += "##  Sub-Agents\n\n"
            md += "| # | Task | Status | Link |\n"
            md += "|---|------|--------|------|\n"
            for i, sub in enumerate(test_case.sub_agents):
                clean = clean_task_text(sub.task)
                first_line = clean.split('\n')[0]
                task_summary = first_line[:80] + "..." if len(first_line) > 80 else first_line
                task_summary = task_summary.replace('|', '\\|')
                status = _agent_status_str(sub)
                link = f"[sub_agent_{i + 1}.md](sub_agent_{i + 1}.md)"
                md += f"| {i + 1} | {task_summary} | {status} | {link} |\n"
            md += "\n"

    return md


def clean_task_text(task: str) -> str:
    """Clean up a task string: remove microbot_sub prefix, escaped quotes, etc."""
    text = task.strip()
    if text.startswith('microbot_sub'):
        match = re.search(r'--task\s+["\'](.+)', text, re.DOTALL)
        if match:
            text = match.group(1)
            text = re.sub(r'["\']\s*--(?:iterations|timeout).*$', '', text, flags=re.DOTALL)
            text = text.strip().strip('"').strip("'").strip()
    text = text.replace('\\"', '"').replace('\\n', '\n').replace("\\'", "'")
    return text


def generate_sub_agent_md(sub_agent: Agent, index: int, test_case_name: str) -> str:
    """Generate a sub-agent markdown file content."""
    clean_task = clean_task_text(sub_agent.task)
    task_heading = clean_task.split('\n')[0] if clean_task else f"Sub-Agent {index + 1}"
    if len(task_heading) > 150:
        task_heading = task_heading[:147] + "..."

    md = f"# {task_heading}\n\n"
    md += "**Parent:** [Main Agent](main_agent.md) | "
    md += f"**Test Case:** {test_case_name}\n\n"

    if clean_task and '\n' in clean_task:
        md += "<details>\n<summary>Full task description</summary>\n\n"
        md += f"```\n{clean_task}\n```\n\n"
        md += "</details>\n\n"

    md += "---\n\n"
    md += "## Steps\n\n"

    for step in sub_agent.steps:
        md += generate_step_md(step)

    md += "---\n\n"

    if sub_agent.completed:
        md += "##  Task Completed\n\n"
        if sub_agent.final_thoughts:
            md += f"{sub_agent.final_thoughts}\n\n"
    elif sub_agent.max_iterations_reached:
        md += "##  Max Iterations Reached\n\n"
        if sub_agent.error_message:
            md += f"> {sub_agent.error_message}\n\n"
        else:
            md += "The sub-agent did not complete the task within the maximum allowed iterations.\n\n"

    return md


#  Single-File Mode 


def generate_single_file_md(test_case: TestCase) -> str:
    """Generate a single markdown file containing the main agent and all sub-agents."""
    md = f"#  Agent Trajectory: {test_case.name}\n\n"

    md += generate_setup_md(test_case.setup)

    # Table of contents
    if test_case.sub_agents:
        md += "##  Table of Contents\n\n"
        md += "- [Main Agent](#main-agent)\n"
        for i, sub in enumerate(test_case.sub_agents):
            clean = clean_task_text(sub.task)
            first_line = clean.split('\n')[0][:60]
            md += f"- [Sub-Agent {i + 1}: {first_line}](#sub-agent-{i + 1})\n"
        md += "\n---\n\n"

    # Main agent section
    md += "## Main Agent\n\n"

    if test_case.main_agent and test_case.main_agent.task:
        md += "### Task\n\n"
        task_text = test_case.main_agent.task
        if len(task_text) > 500:
            md += f"<details>\n<summary>Full task description</summary>\n\n{task_text}\n\n</details>\n\n"
        else:
            md += f"{task_text}\n\n"

    md += "---\n\n"
    md += "### Steps\n\n"

    if test_case.main_agent:
        agent = test_case.main_agent
        for step in agent.steps:
            sub_ref = ""
            if step.is_sub_agent_call and step.sub_agent_index >= 0:
                sub_ref = f"#sub-agent-{step.sub_agent_index + 1}"
            md += generate_step_md(step, sub_agent_filename=sub_ref, heading_level=4)

        md += "---\n\n"

        if agent.completed:
            md += "###  Task Completed\n\n"
            if agent.final_thoughts:
                md += f"{agent.final_thoughts}\n\n"
        elif agent.max_iterations_reached:
            md += "###  Max Iterations Reached\n\n"

        # Sub-agent summary table
        if test_case.sub_agents:
            md += "###  Sub-Agents Summary\n\n"
            md += "| # | Task | Status |\n"
            md += "|---|------|--------|\n"
            for i, sub in enumerate(test_case.sub_agents):
                clean = clean_task_text(sub.task)
                first_line = clean.split('\n')[0]
                task_summary = first_line[:80] + "..." if len(first_line) > 80 else first_line
                task_summary = task_summary.replace('|', '\\|')
                status = _agent_status_str(sub)
                md += f"| [{i + 1}](#sub-agent-{i + 1}) | {task_summary} | {status} |\n"
            md += "\n"

    # Sub-agent sections
    for i, sub in enumerate(test_case.sub_agents):
        clean_task = clean_task_text(sub.task)
        task_heading = clean_task.split('\n')[0] if clean_task else f"Sub-Agent {i + 1}"
        if len(task_heading) > 120:
            task_heading = task_heading[:117] + "..."

        md += f"\n---\n\n## Sub-Agent {i + 1}\n\n"
        md += f"**{task_heading}**\n\n"

        if clean_task and '\n' in clean_task:
            md += "<details>\n<summary>Full task description</summary>\n\n"
            md += f"```\n{clean_task}\n```\n\n"
            md += "</details>\n\n"

        md += "### Steps\n\n"

        for step in sub.steps:
            md += generate_step_md(step, heading_level=4)

        md += "---\n\n"

        if sub.completed:
            md += "###  Task Completed\n\n"
            if sub.final_thoughts:
                md += f"{sub.final_thoughts}\n\n"
        elif sub.max_iterations_reached:
            md += "###  Max Iterations Reached\n\n"
            if sub.error_message:
                md += f"> {sub.error_message}\n\n"

    return md


#  Main 


def parse_and_generate(log_path: str, output_base_dir: str = None, single_file: bool = False):
    """
    Parse an info.log file and generate markdown trajectory files.

    Args:
        log_path: Path to the info.log file
        output_base_dir: Base directory for output. If None, uses the log file's directory.
        single_file: If True, generate a single markdown file instead of a directory.
    """
    if not os.path.isfile(log_path):
        print(f"Error: Log file not found: {log_path}")
        sys.exit(1)

    basename = os.path.basename(log_path)
    if basename.endswith('_info.log'):
        default_test_name = basename[:-len('_info.log')]
    elif basename.endswith('.log'):
        default_test_name = basename[:-len('.log')]
    else:
        default_test_name = os.path.splitext(basename)[0]

    if output_base_dir is None:
        output_base_dir = os.path.dirname(os.path.abspath(log_path))

    print(f"Parsing log file: {log_path}")

    entries = parse_log_entries(log_path)
    print(f"  Parsed {len(entries)} log entries")

    # Extract setup info before building test cases
    setup = _extract_setup_info(entries)

    test_cases = build_test_cases(entries)
    print(f"  Found {len(test_cases)} test case(s)")

    if not test_cases:
        print("  No test case boundaries found, treating entire log as one test case")
        test_cases = _build_single_test_case(entries, default_test_name)

    # Attach setup info to first test case
    if test_cases:
        test_cases[0].setup = setup

    for tc in test_cases:
        tc_name = tc.name if tc.name != "unknown" else default_test_name
        tc.name = tc_name

        main_steps = len(tc.main_agent.steps) if tc.main_agent else 0
        sub_count = len(tc.sub_agents)
        print(f"\n  Test case: {tc_name}")
        print(f"  Main agent: {main_steps} steps, {sub_count} sub-agent(s)")

        if single_file:
            # Single file mode
            md = generate_single_file_md(tc)
            out_path = os.path.join(output_base_dir, f"{tc_name}_trajectory.md")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"  Created: {out_path}")
        else:
            # Multi-file mode
            trajectory_dir = os.path.join(output_base_dir, f"{tc_name}_trajectory")
            os.makedirs(trajectory_dir, exist_ok=True)
            print(f"  Output directory: {trajectory_dir}")

            main_md = generate_main_agent_md(tc)
            main_path = os.path.join(trajectory_dir, "main_agent.md")
            with open(main_path, 'w', encoding='utf-8') as f:
                f.write(main_md)
            print(f"  Created: main_agent.md ({main_steps} steps)")

            for i, sub in enumerate(tc.sub_agents):
                sub_md = generate_sub_agent_md(sub, i, tc_name)
                sub_path = os.path.join(trajectory_dir, f"sub_agent_{i + 1}.md")
                with open(sub_path, 'w', encoding='utf-8') as f:
                    f.write(sub_md)
                print(f"  Created: sub_agent_{i + 1}.md ({len(sub.steps)} steps)")

    print(f"\nDone! Generated trajectory for {len(test_cases)} test case(s).")
    return test_cases


def _build_single_test_case(entries: List[dict], name: str) -> List[TestCase]:
    """
    Build a single test case when no test directory boundaries are found.
    Injects a fake test case boundary entry and delegates to build_test_cases.
    """
    fake_boundary = {
        'timestamp': '2000-01-01 00:00:00,000',
        'module': '',
        'level': 'INFO',
        'content': f'Test directory set up at: /fake/{name}',
        'line_num': 0,
    }
    return build_test_cases([fake_boundary] + entries)


def main():
    parser = argparse.ArgumentParser(
        description="Parse microbots info.log files into markdown trajectory files."
    )
    parser.add_argument("log_file", help="Path to the info.log file to parse")
    parser.add_argument("output_dir", nargs="?", default=None,
                        help="Output directory (default: same directory as log file)")
    parser.add_argument("--single-file", action="store_true",
                        help="Generate a single markdown file instead of a directory with separate files")

    args = parser.parse_args()
    parse_and_generate(args.log_file, args.output_dir, args.single_file)


if __name__ == '__main__':
    main()
