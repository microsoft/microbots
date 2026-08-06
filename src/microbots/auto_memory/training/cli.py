"""Programmatic and CLI entry points for the training framework.

Programmatic:

    from microbots.auto_memory.training import run_training

    # Local directory as source (legacy shape still works):
    summary = run_training(
        source_path="/path/to/source",
        memory_dir="/path/to/memory",
        model="azure-openai/gpt-4o",
    )

    # Git repo as source:
    from microbots.auto_memory.training import TrainingSource
    summary = run_training(
        source=TrainingSource(type="git", url="https://github.com/foo/bar.git",
                          ref="main"),
        memory_dir="/path/to/memory",
        model="azure-openai/gpt-4o",
    )

CLI:

    python -m microbots.auto_memory.training \
        --source /path/to/source \
        --memory /path/to/memory \
        --model azure-openai/gpt-5 \
        [--source-git-url https://github.com/foo/bar.git] \
        [--source-ref main] \
        [--source-cache-dir /path/to/clone] \
        [--agents-md /path/to/AGENTS.md] \
        [--iterations 3] \
        [--config path/to/training.yaml] \
        [--workdir path/to/workdir] \
        [--reset-memory]

The framework is domain-agnostic: the source can be any directory the
agent should learn from (a source-code repo, a docs tree, a dataset, an
example gallery, …) or a git repository URL that is cloned before the
run. What the agent actually does with it is defined by the
``AGENTS.md`` file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from microbots.auto_memory.errors import ConfigError
from microbots.auto_memory.training.config import TrainingConfig
from microbots.auto_memory.training.orchestrator import (
    TrainingOrchestrator,
    TrainingSummary,
)
from microbots.auto_memory.training.training_source import TrainingSource


# ---------------------------------------------------------------------------
# Programmatic API
# ---------------------------------------------------------------------------


def run_training(
    *,
    source: TrainingSource | dict | None = None,
    source_path: str | Path | None = None,
    memory_dir: str | Path,
    model: str,
    agents_md_path: str | Path | None = None,
    iterations: int = 3,
    per_iteration_timeout: int = 900,
    total_timeout_min: int = 0,
    max_bot_steps: int = 40,
    reset_memory: bool = False,
    workdir: str | Path | None = None,
) -> TrainingSummary:
    """Build a :class:`TrainingConfig`, wire the orchestrator, and run it.

    Provide exactly one of ``source`` or ``source_path``. ``source`` is the
    new nested form (:class:`TrainingSource` or an equivalent mapping) and lets
    you point at a git repo; ``source_path`` remains as a shortcut for a
    local directory (or a bare git URL, which is auto-detected).

    Other parameters mirror the fields of :class:`TrainingConfig`.
    ``workdir`` is where ``training_meta.json`` and ``training_run.jsonl``
    are written; it defaults to
    ``<memory_dir>/.training-run-<UTC-timestamp>/``.

    Parameters
    ----------
    source : TrainingSource | dict | None, optional
        Structured source specification or equivalent mapping.
    source_path : str | Path | None, optional
        Legacy local directory or git URL. Mutually exclusive with ``source``.
    memory_dir : str | Path
        Host directory backing the agent's persistent memory.
    model : str
        Model identifier in ``<provider>/<name>`` form.
    agents_md_path : str | Path | None, optional
        Custom training instructions file.
    iterations : int, optional
        Number of training iterations to run.
    per_iteration_timeout : int, optional
        Wall-clock limit for each iteration, in seconds.
    total_timeout_min : int, optional
        Wall-clock limit for the full run, in minutes. Zero disables it.
    max_bot_steps : int, optional
        Maximum internal bot steps per iteration.
    reset_memory : bool, optional
        Whether to clear existing memory before training.
    workdir : str | Path | None, optional
        Directory for training metadata and logs.

    Returns
    -------
    TrainingSummary
        Summary of the completed run.
    """
    if source is not None and source_path is not None:
        raise ConfigError(
            "Pass either 'source' or 'source_path', not both."
        )
    if source is None and source_path is None:
        raise ConfigError("One of 'source' or 'source_path' is required.")

    if source is not None:
        if isinstance(source, TrainingSource):
            source_spec = source
        elif isinstance(source, dict):
            source_spec = TrainingSource.from_mapping(source, base_dir=Path.cwd())
        else:
            raise ConfigError(
                "'source' must be a TrainingSource or mapping, got "
                f"{type(source).__name__}"
            )
    else:
        source_spec = TrainingSource.from_legacy_source_path(
            source_path, base_dir=Path.cwd()  # type: ignore[arg-type]
        )

    cfg_kwargs: dict = {
        "source": source_spec,
        "memory_dir": Path(memory_dir).resolve(),
        "model": model,
        "iterations": iterations,
        "per_iteration_timeout": per_iteration_timeout,
        "total_timeout_min": total_timeout_min,
        "max_bot_steps": max_bot_steps,
        "reset_memory": reset_memory,
    }
    if agents_md_path is not None:
        cfg_kwargs["agents_md_path"] = Path(agents_md_path).resolve()

    config = TrainingConfig(**cfg_kwargs)
    config.validate()

    if workdir is None:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        workdir = config.memory_dir.parent / f".training-run-{stamp}"

    orchestrator = TrainingOrchestrator(config=config, workdir=Path(workdir))
    return orchestrator.run()


def run_training_from_yaml(
    yaml_path: str | Path,
    *,
    workdir: str | Path | None = None,
) -> TrainingSummary:
    """Load a training YAML config and execute the orchestrator.

    Parameters
    ----------
    yaml_path : str | Path
        Path to the YAML file describing the training run.
    workdir : str | Path | None, optional
        Where to persist meta/log files. Defaults to
        ``<memory_dir>/.training-run-<UTC-timestamp>/``.

    Returns
    -------
    TrainingSummary
        Summary of the completed run.
    """
    config = TrainingConfig.load_from_yaml(yaml_path)

    if workdir is None:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        workdir = config.memory_dir.parent / f".training-run-{stamp}"

    orchestrator = TrainingOrchestrator(config=config, workdir=Path(workdir))
    return orchestrator.run()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Parser configured for the training command.
    """
    p = argparse.ArgumentParser(
        prog="microbots.auto_memory.training",
        description=(
            "Run a training loop: point an agent at a source directory plus "
            "an AGENTS.md prompt, and let it populate a persistent "
            "/memories/ tree. The source can be any directory (source-code "
            "repo, docs tree, dataset, example gallery, …) — what the "
            "agent learns is defined by AGENTS.md."
        ),
    )
    p.add_argument(
        "--config",
        type=Path,
        help=(
            "Path to a training YAML config. When provided, most other "
            "flags are ignored (only --workdir and --verbose still apply)."
        ),
    )
    p.add_argument(
        "--source",
        type=Path,
        help=(
            "Local directory the agent should learn from. Mutually exclusive "
            "with --source-git-url."
        ),
    )
    p.add_argument(
        "--source-git-url",
        type=str,
        default=None,
        help=(
            "Git remote URL to clone as the source. When set, --source is "
            "used (if given) as the clone destination; otherwise the loop "
            "clones into <workdir>/source/."
        ),
    )
    p.add_argument(
        "--source-ref",
        type=str,
        default=None,
        help="Branch, tag, or commit to check out for --source-git-url.",
    )
    p.add_argument(
        "--source-cache-dir",
        type=Path,
        default=None,
        help=(
            "Explicit clone destination for --source-git-url. Set this to "
            "reuse a checkout across runs."
        ),
    )
    p.add_argument(
        "--memory",
        type=Path,
        help="Host directory backing the agent's /memories/ tree.",
    )
    p.add_argument("--model", type=str, help="Model id, e.g. azure-openai/gpt-4o.")
    p.add_argument(
        "--agents-md",
        type=Path,
        default=None,
        help="Custom AGENTS.md file (defaults to the one shipped in this package).",
    )
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--per-iteration-timeout", type=int, default=900)
    p.add_argument("--total-timeout-min", type=int, default=0)
    p.add_argument("--max-bot-steps", type=int, default=40)
    p.add_argument(
        "--reset-memory",
        action="store_true",
        help="Wipe the memory directory before starting.",
    )
    p.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Where to write training_meta.json and training_run.jsonl.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    """Run the training command-line interface.

    Parameters
    ----------
    argv : list[str] | None, optional
        Arguments to parse. Uses :data:`sys.argv` when omitted.

    Returns
    -------
    int
        Process exit code, with zero indicating completion.
    """
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.config is not None:
            summary = run_training_from_yaml(args.config, workdir=args.workdir)
        else:
            if args.memory is None or args.model is None:
                missing = [
                    name
                    for name, val in (
                        ("--memory", args.memory),
                        ("--model", args.model),
                    )
                    if val is None
                ]
                print(
                    f"error: missing required flag(s): {', '.join(missing)} "
                    "(or pass --config).",
                    file=sys.stderr,
                )
                return 2

            # Build the source: either a local path (--source) or a git URL
            # (--source-git-url). --source alone → local; --source-git-url
            # → git, optionally with --source as the clone destination.
            if args.source_git_url:
                source_kwarg: dict = {
                    "source": TrainingSource(
                        type="git",
                        url=args.source_git_url,
                        ref=args.source_ref,
                        path=args.source.resolve() if args.source else None,
                        cache_dir=(
                            args.source_cache_dir.resolve()
                            if args.source_cache_dir
                            else None
                        ),
                    )
                }
            elif args.source is not None:
                source_kwarg = {"source_path": args.source}
            else:
                print(
                    "error: missing required flag(s): --source or "
                    "--source-git-url (or pass --config).",
                    file=sys.stderr,
                )
                return 2

            summary = run_training(
                **source_kwarg,
                memory_dir=args.memory,
                model=args.model,
                agents_md_path=args.agents_md,
                iterations=args.iterations,
                per_iteration_timeout=args.per_iteration_timeout,
                total_timeout_min=args.total_timeout_min,
                max_bot_steps=args.max_bot_steps,
                reset_memory=args.reset_memory,
                workdir=args.workdir,
            )
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    print(
        f"training {summary.final_status}: "
        f"iterations={summary.iterations_run} "
        f"elapsed={summary.elapsed_s:.1f}s "
        f"memory_dir={summary.memory_dir}"
    )
    if summary.error_message:
        print(f"last error: {summary.error_message}", file=sys.stderr)
    return 0
