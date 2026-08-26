"""Minimal SWE-bench-verified eval task.

Loads instances from the SWE-bench-verified dataset, checks out each
instance's repo at its base commit, has the agent attempt a fix, and
verifies the result via ``swebench.harness.run_evaluation``.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

from datasets import load_dataset
import argparse
from microbots.auto_memory.task import CallbackResult, EvalTask
from microbots.auto_memory.orchestrator import run_train_eval_loop

logger = getLogger(__name__)

SWE_BENCH_SUITE = "SWE-bench/SWE-bench_Verified"


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
    dataset_name: str = SWE_BENCH_SUITE,
    repo: str | None = None,
) -> list[SweBenchInstance]:
    """Load all dataset instances, optionally filtered to a single repo.

    Parameters
    ----------
    dataset_name : str
        Hugging Face dataset name to load. Defaults to
        ``SWE_BENCH_SUITE``.
    repo : str | None
        If given, only instances whose ``repo`` matches this value are
        returned, e.g. ``"django/django"``. If ``None``, all instances
        are returned.

    Returns
    -------
    list[SweBenchInstance]
        The matching instances.
    """
    rows = load_dataset(dataset_name, split="test")
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

def load_instance_using_id(instance_id: str, dataset_name: str = SWE_BENCH_SUITE) -> SweBenchInstance:
    """Load a single dataset instance by its instance ID.

    Parameters
    ----------
    instance_id : str
        The instance ID to look up, e.g. ``"django__django-11099"``.
    dataset_name : str
        Hugging Face dataset name to load. Defaults to
        ``SWE_BENCH_SUITE``.

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
    rows = load_dataset(dataset_name, split="test")
    for row in rows:
        if row["instance_id"] == instance_id:
            return SweBenchInstance(
                instance_id=row["instance_id"],
                repo=row["repo"],
                base_commit=row["base_commit"],
                problem_statement=row["problem_statement"],
            )
    raise ValueError(f"instance_id not found: {instance_id}")

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

    def __init__(self, instance: SweBenchInstance):
        """Initialize the task for a single dataset instance.

        Parameters
        ----------
        instance : SweBenchInstance
            The dataset instance this task evaluates against.
        """
        self.instance = instance

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

    def build_prompt(self, repo_path: str) -> str:
        """Return the instance's issue text as the agent's prompt.

        Parameters
        ----------
        repo_path : str
            Absolute path to the repo the agent will operate on.

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
        model_name_or_path = "microbots-eval-agent"
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
                 "--dataset_name", SWE_BENCH_SUITE,
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


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help='e.g. "django/django"')
    parser.add_argument("--instance-id", help='e.g. "django__django-11099"')
    parser.add_argument("--model", default="azure-openai/gpt-5.5")
    parser.add_argument("--max-rounds", type=int, default=5)
    args = parser.parse_args()

    if args.instance_id:
        instances = [load_instance_using_id(args.instance_id)]
    else:
        instances = load_instances_of_repo(repo=args.repo)

    for instance in instances:
        task = SweBenchVerifiedTask(instance)
        result = run_train_eval_loop(
            repo_path=tempfile.mkdtemp(),
            memory_dir="memory",
            model=args.model,
            task=task,
            max_rounds=args.max_rounds,
        )
        logger.info("%s: passed=%s", instance.instance_id, result.passed)
