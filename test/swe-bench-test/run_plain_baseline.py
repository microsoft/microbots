"""Minimal, single-shot plain-agent baseline for a SWE-bench repo.

No orchestrator, no analyzer, no memory tool, no retries — this runs
``WritingBot`` exactly once per instance and scores the result using the
**official SWE-bench Docker evaluation harness**
(``swebench.harness.run_evaluation``, ``pip install swebench``). Docker
builds a per-instance image with the correct Python interpreter + deps for
that historical commit, so old instances (e.g. pre-3.8 code using the
removed ``imp`` module) are scored correctly without touching the host
Python at all — the host only needs Docker and the ``swebench`` pip package
(installed in this project's ``.venv``, never system-wide).

Usage
-----

    python run_plain_baseline.py \\
        --repo pytest-dev/pytest \\
        --model azure-openai/gpt-5 \\
        --max-bot-steps 40 \\
        --timeout-s 3600 \\
        [--limit 5] [--instance-id pytest-dev__pytest-5262]

Writes ``<out-dir>/results.json`` with one row per instance:
``{instance_id, resolved, bot_status, error}`` and prints a final
``resolved/total`` summary. Also leaves ``<out-dir>/predictions.jsonl`` and
the raw swebench harness report (``<out-dir>/<model>.<run_id>.json``) for
inspection.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from microbots.bot.WritingBot import WritingBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_TASK_TEMPLATE = """Fix the bug described below in the checked-out repository.
Your working directory holds a fresh clone at the buggy commit.

## Problem statement

{problem_statement}

{hints_block}
## Guidance

Produce a minimal patch that makes the target tests pass. Do NOT modify
files under `tests/` or `test/` unless the problem statement explicitly
requires it. Leave the working tree ready to be tested — do not commit.
"""


@dataclass
class InstanceResult:
    instance_id: str
    bot_status: bool
    bot_error: str | None
    resolved: bool
    elapsed_s: float


# ---------------------------------------------------------------------------
# Repo setup
# ---------------------------------------------------------------------------

def clone_and_checkout(repo: str, base_commit: str, dest: Path) -> None:
    if dest.exists():
        _force_remove_dir(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(dest)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "checkout", "--quiet", base_commit], check=True
    )


def _force_remove_dir(dest: Path) -> None:
    """Remove *dest*, tolerating root-owned leftovers from a prior Docker run.

    WritingBot mounts the repo dir into a container that runs as root, so any
    files the agent's process creates inside (e.g. __pycache__/*.pyc) land on
    the host owned by root and can't be removed by the current user. Falling
    back to deleting via a throwaway container (root only inside that single
    bind-mounted folder, nothing else on the host) avoids needing sudo.
    """
    result = subprocess.run(["rm", "-rf", str(dest)])
    if result.returncode == 0:
        return
    logger.warning(
        "Host rm -rf failed on %s (likely root-owned Docker leftovers); "
        "retrying via a throwaway container.", dest,
    )
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{dest}:/target",
            "alpine", "sh", "-c", "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null; true",
        ],
        check=True,
    )
    subprocess.run(["rm", "-rf", str(dest)], check=True)



# ---------------------------------------------------------------------------
# Docker-based scoring via the official swebench harness
# ---------------------------------------------------------------------------

_MODEL_NAME_OR_PATH = "microbots-plain-baseline"


def get_model_patch(repo_dir: Path) -> str:
    """Return the bot's edits as a unified diff (empty string if none)."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "diff"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def run_swebench_harness(
    predictions_path: Path,
    dataset: str,
    split: str,
    instance_ids: list[str],
    run_id: str,
    out_dir: Path,
    timeout_s: int,
    max_workers: int = 1,
) -> dict:
    """Invoke the official Docker-based swebench harness and return its report dict.

    Builds a per-instance Docker image with the correct Python interpreter +
    deps for that historical commit, applies the model patch + gold
    test_patch inside the container, and runs FAIL_TO_PASS/PASS_TO_PASS
    there — so this is immune to host Python version mismatches (e.g. the
    `imp` module removed in 3.12). The harness writes its report JSON into
    the current working directory, so we run it with cwd=out_dir.
    ``max_workers`` controls how many instance containers the harness runs
    concurrently — safe to raise since each instance is fully isolated in
    its own container.
    """
    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", dataset,
        "--split", split,
        "--predictions_path", str(predictions_path),
        "--max_workers", str(max_workers),
        "--run_id", run_id,
        "--timeout", str(timeout_s),
        "--instance_ids", *instance_ids,
    ]
    logger.info("Running swebench harness: %s", " ".join(cmd))
    subprocess.run(cmd, cwd=str(out_dir), check=True)

    report_path = out_dir / f"{_MODEL_NAME_OR_PATH}.{run_id}.json"
    if not report_path.exists():
        raise FileNotFoundError(
            f"swebench harness did not produce expected report at {report_path}"
        )
    return json.loads(report_path.read_text(encoding="utf-8"))


def write_prediction(predictions_path: Path, instance_id: str, model_patch: str) -> None:
    """Append/replace one instance's prediction in the shared predictions.jsonl."""
    existing: list[dict] = []
    if predictions_path.exists():
        existing = [json.loads(line) for line in predictions_path.read_text().splitlines() if line]
    existing = [p for p in existing if p["instance_id"] != instance_id]
    existing.append({
        "instance_id": instance_id,
        "model_name_or_path": _MODEL_NAME_OR_PATH,
        "model_patch": model_patch,
    })
    predictions_path.write_text(
        "\n".join(json.dumps(p) for p in existing) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def run_agent_once(
    instance: dict,
    *,
    model: str,
    work_root: Path,
    max_bot_steps: int,
    timeout_s: int,
) -> tuple[Path, "bool | None", str | None, float]:
    """Clone + checkout + run WritingBot once. Returns
    (repo_dir, bot_status, bot_error, elapsed_s). Scoring happens separately.
    """
    instance_id = instance["instance_id"]
    repo_dir = work_root / instance_id
    started = time.monotonic()

    logger.info("=== %s: cloning + checkout (base_commit only, no test_patch) ===", instance_id)
    clone_and_checkout(instance["repo"], instance["base_commit"], repo_dir)

    hints = (instance.get("hints_text") or "").strip()
    hints_block = f"## Hints from maintainers\n\n{hints}\n\n" if hints else ""
    task = _TASK_TEMPLATE.format(
        problem_statement=instance["problem_statement"],
        hints_block=hints_block,
    )

    logger.info("=== %s: running plain agent (1 shot, max_bot_steps=%d) ===",
                instance_id, max_bot_steps)
    bot = WritingBot(model=model, folder_to_mount=str(repo_dir))
    try:
        bot_result = bot.run(task=task, max_iterations=max_bot_steps, timeout_in_seconds=timeout_s)
    finally:
        if bot.environment is not None:
            bot.environment.stop()

    elapsed = time.monotonic() - started
    return repo_dir, bot_result.status, bot_result.error, elapsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    p.add_argument("--split", default="test")
    p.add_argument("--repo", default=None,
                    help='e.g. "pytest-dev/pytest". Required unless --instance-id is given.')
    p.add_argument("--instance-id", default=None, help="Run just this one instance.")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", required=True, help="e.g. azure-openai/gpt-5")
    p.add_argument("--max-bot-steps", type=int, default=40,
                    help="WritingBot's own step budget for the single attempt.")
    p.add_argument("--timeout-s", type=int, default=3600,
                    help="Both the bot's wall-clock budget and the harness's per-test timeout.")
    p.add_argument("--work-dir", type=Path, default=Path("/tmp/plain_baseline"))
    p.add_argument("--out-dir", type=Path, default=Path("/tmp/plain_baseline_results"))
    p.add_argument("--run-id", default=None,
                    help="swebench harness run_id (default: 'plain-baseline-<timestamp>').")
    p.add_argument("--max-workers", type=int, default=1,
                    help="Concurrent Docker containers for the scoring phase (default: 1). "
                         "Each instance is fully isolated, so raising this is safe as long "
                         "as your machine has the CPU/RAM/disk to build+run that many images "
                         "at once.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.instance_id and not args.repo:
        print("Must pass --repo or --instance-id", file=sys.stderr)
        return 2

    from datasets import load_dataset

    ds = load_dataset(args.dataset, split=args.split)
    if args.instance_id:
        instances = [dict(r) for r in ds if r["instance_id"] == args.instance_id]
    else:
        instances = [dict(r) for r in ds if r["repo"] == args.repo]
        if args.limit is not None:
            instances = instances[: args.limit]

    if not instances:
        print(f"No instances found for repo={args.repo!r}", file=sys.stderr)
        return 1

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = args.out_dir / "predictions.jsonl"
    run_id = args.run_id or f"plain-baseline-{int(time.time())}"

    # --- Phase 1: run the plain agent once per instance, collect patches ---
    bot_meta: dict[str, dict] = {}
    for i, inst in enumerate(instances, start=1):
        instance_id = inst["instance_id"]
        logger.info("--- agent %d/%d: %s ---", i, len(instances), instance_id)
        try:
            repo_dir, bot_status, bot_error, elapsed = run_agent_once(
                inst,
                model=args.model,
                work_root=args.work_dir,
                max_bot_steps=args.max_bot_steps,
                timeout_s=args.timeout_s,
            )
            model_patch = get_model_patch(repo_dir) if bot_status else ""
        except Exception as exc:  # noqa: BLE001 — one bad instance shouldn't kill the batch
            logger.exception("%s: unhandled error during agent run", instance_id)
            bot_status, bot_error, elapsed, model_patch = False, f"{type(exc).__name__}: {exc}", 0.0, ""

        bot_meta[instance_id] = {
            "bot_status": bool(bot_status),
            "bot_error": bot_error,
            "elapsed_s": elapsed,
        }
        write_prediction(predictions_path, instance_id, model_patch)

    # --- Phase 2: score every instance in one Docker harness invocation ---
    instance_ids = [inst["instance_id"] for inst in instances]
    logger.info("=== scoring %d instance(s) via swebench Docker harness ===", len(instance_ids))
    try:
        report = run_swebench_harness(
            predictions_path, args.dataset, args.split, instance_ids,
            run_id, args.out_dir, args.timeout_s, max_workers=args.max_workers,
        )
    except Exception:
        logger.exception("swebench harness invocation failed")
        report = {"resolved_ids": [], "error_ids": instance_ids}

    resolved_ids = set(report.get("resolved_ids", []))
    error_ids = set(report.get("error_ids", []))

    # --- Combine + report ---
    results: list[InstanceResult] = []
    for inst in instances:
        instance_id = inst["instance_id"]
        meta = bot_meta.get(instance_id, {})
        resolved = instance_id in resolved_ids
        results.append(InstanceResult(
            instance_id=instance_id,
            bot_status=meta.get("bot_status", False),
            bot_error=meta.get("bot_error") or ("harness_error" if instance_id in error_ids else None),
            resolved=resolved,
            elapsed_s=meta.get("elapsed_s", 0.0),
        ))

    (args.out_dir / "results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8"
    )

    resolved_count = sum(1 for r in results if r.resolved)
    print()
    print(f"{'instance_id':45s}  resolved  bot_ok  elapsed")
    print("-" * 80)
    for r in results:
        print(f"{r.instance_id:45s}  {str(r.resolved):8s}  {str(r.bot_status):6s}  {r.elapsed_s:6.0f}s")
    print("-" * 80)
    print(f"resolved: {resolved_count}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

