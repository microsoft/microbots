"""SWE-bench-verified eval task.

Loads instances from the SWE-bench-verified dataset, checks out each
instance's repo at its base commit, has the agent attempt a fix, and
verifies the result via ``swebench.harness.run_evaluation``.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from functools import lru_cache
from logging import getLogger
from pathlib import Path

from datasets import load_dataset
from microbots.auto_memory.evalTask import CallbackResult, EvalOutcome, EvalTask
from microbots.auto_memory.task_registry import register_task
from microbots.bot.WritingBot import WritingBot
from microbots.tools.tool_definitions.memory_tool import MemoryTool

logger = getLogger(__name__)

SWE_BENCH_VERIFIED = "SWE-bench/SWE-bench_Verified"
EVAL_AGENT_MODEL_NAME = "microbots-eval-agent"


@lru_cache(maxsize=None)
def _load_dataset_rows(dataset_name: str):
    """Load and cache ``dataset_name``'s ``test`` split for the process's lifetime.

    ``load_dataset`` caches the downloaded files on disk, but still
    re-reads and rebuilds the in-memory ``Dataset`` object on every
    call. Since ``load_instances_of_repo``/``load_instance_using_id``
    may each be called many times (e.g. once per eval task instance),
    this wraps ``load_dataset`` with an in-memory cache keyed by
    ``dataset_name``, so the dataset is only loaded once per process.

    Parameters
    ----------
    dataset_name : str
        Hugging Face dataset name to load.

    Returns
    -------
    datasets.Dataset
        The loaded ``test`` split.
    """
    return load_dataset(dataset_name, split="test")


@dataclass
class SweBenchInstance:
    """A single SWE-bench-verified dataset row.

    Attributes
    ----------
    instance_id : str
        Unique identifier for the instance, e.g. ``"django__django-11099"``.
    repo : str
        The GitHub repo this instance belongs to, e.g. ``"django/django"``.
    base_commit : str
        Commit hash representing the repo state before the issue's fix.
    problem_statement : str
        The GitHub issue title and body describing the bug to fix.
    """

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str


def load_instances_of_repo(
    dataset_name: str = SWE_BENCH_VERIFIED,
    repo: str | None = None,
) -> list[SweBenchInstance]:
    """Load all dataset instances, optionally filtered to a single repo.

    Parameters
    ----------
    dataset_name : str
        Hugging Face dataset name to load. Defaults to
        ``SWE_BENCH_VERIFIED``.
    repo : str | None
        If given, only instances whose ``repo`` matches this value are
        returned, e.g. ``"django/django"``. If ``None``, all instances
        are returned.

    Returns
    -------
    list[SweBenchInstance]
        The matching instances.
    """
    rows = _load_dataset_rows(dataset_name)
    instances = [
        SweBenchInstance(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
        )
        for row in rows
        if repo is None or row["repo"] == repo
    ]
    return instances

def load_instance_using_id(instance_id: str, dataset_name: str = SWE_BENCH_VERIFIED) -> SweBenchInstance:
    """Load a single dataset instance by its instance ID.

    Parameters
    ----------
    instance_id : str
        The instance ID to look up, e.g. ``"django__django-11099"``.
    dataset_name : str
        Hugging Face dataset name to load. Defaults to
        ``SWE_BENCH_VERIFIED``.

    Returns
    -------
    SweBenchInstance
        The matching instance.

    Raises
    ------
    ValueError
        If no instance with the given ``instance_id`` exists in the
        dataset.
    """
    rows = _load_dataset_rows(dataset_name)
    for row in rows:
        if row["instance_id"] == instance_id:
            return SweBenchInstance(
                instance_id=row["instance_id"],
                repo=row["repo"],
                base_commit=row["base_commit"],
                problem_statement=row["problem_statement"],
            )
    raise ValueError(f"instance_id not found: {instance_id}")

@register_task("swebenchverified")
class SweBenchVerifiedTask(EvalTask):
    """Eval task that verifies a fix against one SWE-bench-verified instance.

    Checks out the instance's repo at its base commit, gives the agent
    the issue's problem statement, and verifies the agent's patch using
    the official SWE-bench evaluation harness.

    Parameters
    ----------
    instance : SweBenchInstance
        The dataset instance this task evaluates against.
    """

    def __init__(self, instance: SweBenchInstance | None = None):
        """Initialize the task, optionally for a single dataset instance.

        Parameters
        ----------
        instance : SweBenchInstance | None
            The dataset instance this task evaluates against. May be
            omitted and set later via ``self.instance``, but must be
            set before any other method on this task is called.
        """
        self.instance = instance

    @staticmethod
    def add_cli_args(parser: argparse.ArgumentParser) -> None:
        """Register this task's CLI flags on ``parser``.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            The CLI's argument parser to add task-specific flags to.
        """
        parser.add_argument(
            "--instance-id",
            help='SWE-bench-verified instance ID, e.g. "django__django-11099".',
        )
        parser.add_argument(
            "--swebench-repo",
            help='Restrict to instances for this repo, e.g. "django/django". '
            "Ignored if --instance-id is given.",
        )

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> list["SweBenchVerifiedTask"]:
        """Build task(s) from parsed CLI args.

        Parameters
        ----------
        args : argparse.Namespace
            Parsed CLI args, expected to include ``instance_id`` and/or
            ``swebench_repo`` (see ``add_cli_args``).

        Returns
        -------
        list[SweBenchVerifiedTask]
            One task per matching dataset instance. A single-element
            list when ``--instance-id`` is given.
        """
        if getattr(args, "instance_id", None):
            instances = [load_instance_using_id(args.instance_id)]
        else:
            instances = load_instances_of_repo(repo=getattr(args, "swebench_repo", None))
        return [cls(instance) for instance in instances]

    @classmethod
    def from_config(cls, task_args: dict) -> list["SweBenchVerifiedTask"]:
        """Build task(s) from a config's ``task_args`` dict.

        Parameters
        ----------
        task_args : dict
            Task-specific config values, expected to include
            ``instance_id`` and/or ``swebench_repo`` (mirrors
            ``add_cli_args``'s flags).

        Returns
        -------
        list[SweBenchVerifiedTask]
            One task per matching dataset instance. A single-element
            list when ``instance_id`` is given.
        """
        if task_args.get("instance_id"):
            instances = [load_instance_using_id(task_args["instance_id"])]
        else:
            instances = load_instances_of_repo(repo=task_args.get("swebench_repo"))
        return [cls(instance) for instance in instances]

    @property
    def task_id(self) -> str:
        """Return this instance's SWE-bench-verified ``instance_id``.

        Returns
        -------
        str
            The dataset instance's ``instance_id``.
        """
        return self.instance.instance_id

    def build_result(self, outcome: EvalOutcome) -> dict:
        """Summarize a round's outcome, including the instance's dataset fields.

        Parameters
        ----------
        outcome : EvalOutcome
            The round's outcome to summarize.

        Returns
        -------
        dict
            ``passed``/``reason`` plus ``instance_id``, ``repo``, and
            ``base_commit`` identifying which dataset row this is.
        """
        return {
            "passed": outcome.result.passed,
            "reason": outcome.result.reason,
            "instance_id": self.instance.instance_id,
            "repo": self.instance.repo,
            "base_commit": self.instance.base_commit,
        }

    def setup(self, repo_path: str) -> None:
        """Clone the instance's repo and check out its base commit.

        Parameters
        ----------
        repo_path : str
            Absolute path to clone the repo into.
        """
        subprocess.run(
            ["git", "clone", f"https://github.com/{self.instance.repo}.git", repo_path],
            check=True,
        )
        subprocess.run(
            ["git", "checkout", self.instance.base_commit], cwd=repo_path, check=True
        )

    def build_prompt(self) -> str:
        """Return the instance's issue text as the agent's prompt.

        Returns
        -------
        str
            The instance's ``problem_statement``.
        """
        return self.instance.problem_statement

    def check(self, repo_path: str, agent_output: str, log_path: str) -> CallbackResult:
        """Verify the agent's patch using the SWE-bench evaluation harness.

        Captures the agent's changes as a git diff, submits it as a
        prediction to ``swebench.harness.run_evaluation``, and checks
        whether the harness marked this instance as resolved.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo the agent operated on.
        agent_output : str
            The agent's raw output/result text. Unused here, since
            verification is based on the repo's git diff, not the
            agent's textual output.
        log_path : str
            Path to a log file to append the harness's output to.

        Returns
        -------
        CallbackResult
            Whether the harness marked this instance as resolved.
        """
        diff = subprocess.run(
            ["git", "diff"], cwd=repo_path, capture_output=True, text=True
        ).stdout

        run_id = f"microbots-{uuid.uuid4().hex[:8]}"
        model_name_or_path = EVAL_AGENT_MODEL_NAME
        pred_path = Path(tempfile.mktemp(suffix=".json"))
        report_dir = Path(tempfile.mkdtemp())
        pred_path.write_text(json.dumps([{
            "instance_id": self.instance.instance_id,
            "model_patch": diff,
            "model_name_or_path": model_name_or_path,
        }]))

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "swebench.harness.run_evaluation",
                 "--dataset_name", SWE_BENCH_VERIFIED,
                 "--max_workers", "1",
                 "--predictions_path", str(pred_path),
                 "--run_id", run_id,
                 "--report_dir", str(report_dir),
                 "--instance_ids", self.instance.instance_id],
                 #can add timeout if needed
                capture_output=True, text=True,
                cwd=report_dir,
            )
            with open(log_path, "a") as f:
                f.write(proc.stdout + proc.stderr)

            report_file = report_dir / f"{model_name_or_path}.{run_id}.json"
            passed = False
            if report_file.exists():
                report = json.loads(report_file.read_text())
                passed = self.instance.instance_id in report.get("resolved_ids", [])
        finally:
            pred_path.unlink(missing_ok=True)
            shutil.rmtree(report_dir, ignore_errors=True)

        return CallbackResult(passed=passed, reason="resolved" if passed else "not resolved")

    def teardown(self, repo_path: str) -> None:
        """Remove the cloned repo working directory.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo cloned by ``setup``.
        """
        subprocess.run(["rm", "-rf", repo_path], check=False)

    def run(self, repo_path: str, memory_dir: str, model: str, log_path: str) -> EvalOutcome:
        """Run one eval iteration: setup -> build_prompt -> WritingBot -> check -> teardown.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo to run the eval round against.
        memory_dir : str
            Directory containing memory files to give the agent via
            ``MemoryTool``.
        model : str
            The model to use, in the format ``<provider>/<model_name>``.
        log_path : str
            Path to write this round's log to. Caller-provided, so the
            log persists under the run's own layout.

        Returns
        -------
        EvalOutcome
            The result of this eval round, including the agent's output,
            the check verdict, and the round's log file path.
        """
        self.setup(repo_path)
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("")

        try:
            try:
                prompt = self.build_prompt()
                bot = WritingBot(
                    model=model,
                    folder_to_mount=repo_path,
                    additional_tools=[MemoryTool(memory_dir=memory_dir)],
                )
                bot_result = bot.run(prompt)

                with open(log_path, "a") as f:
                    f.write(f"Agent output:\n{bot_result.result}\n")

                if not bot_result.status:
                    reason = f"Bot run failed: {bot_result.error}"
                    with open(log_path, "a") as f:
                        f.write(f"\n{reason}\n")
                    result = CallbackResult(passed=False, reason=reason)
                else:
                    result = self.check(repo_path, bot_result.result or "", log_path)

                return EvalOutcome(
                    passed=result.passed,
                    output=bot_result.result,
                    result=result,
                    log_path=log_path,
                )
            except Exception as exc:
                logger.exception(
                    "SweBenchVerifiedTask.run: iteration raised %s", type(exc).__name__
                )
                with open(log_path, "a") as f:
                    f.write(f"\nException during eval iteration: {type(exc).__name__}: {exc}\n")
                return EvalOutcome(
                    passed=False,
                    output=None,
                    result=CallbackResult(
                        passed=False, reason=f"{type(exc).__name__}: {exc}"
                    ),
                    log_path=log_path,
                )
        finally:
            try:
                self.teardown(repo_path)
            except Exception:
                logger.exception("SweBenchVerifiedTask.run: teardown() raised exception; ignoring")


