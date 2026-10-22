# Developer Contribution Guidance

Welcome, contributor. This series walks you through everything you need to
contribute to Microbots — from preparing your machine to following the project's
code and documentation standards.

> Before you write any code, review the
> [Contributing](https://github.com/microsoft/microbots/blob/main/CONTRIBUTING.md)
> file for the Contributor License Agreement (CLA) and the Code of Conduct. You
> only need to sign the CLA once across all Microsoft repositories.

## What this series covers

This guidance is split into three articles. Read them in order the first time:

1. **Environment Setup** (this article) — prepare prerequisites and clone the repository.
2. **[Pre-commit Setup](pre-commit-setup.md)** — install the local quality checks that run before every commit.
3. **[Docstring & Writing Guidelines](docstring-and-writing-guidelines.md)** — write docstrings and documentation that meet the project's standards.

---

## Step 1 — Install the Prerequisites

Microbots needs two tools on your machine before you can run or contribute to it:

1. **Python** — the runtime that Microbots is written in.
2. **Docker** — the sandboxed environment in which bots execute.

If you have not installed these yet, follow the dedicated
**[Pre-requisites](../../getting-started/prerequisites.md)** article. It provides
per-operating-system instructions for installing the correct Python version and
setting up Docker, then verifying both.

> Return here once `python3 --version` and `docker ps` both succeed. The rest of
> this series assumes those tools are installed and working.

---

## Step 2 — Clone the Repository

With the prerequisites in place, you will now obtain the source code. Each command
below is in its own block so you can copy them individually.

**Clone the repository** to your machine.

```bash
git clone https://github.com/microsoft/microbots.git
```

**Move into the project directory.** All remaining commands are run from here.

```bash
cd microbots
```

---

## Step 3 — Create an Isolated Environment

You will install Microbots into a project-specific virtual environment. This keeps
its dependencies separate from your system Python, so nothing is added globally.

**Create the virtual environment** in a `.venv` folder.

```bash
python -m venv .venv
```

**Activate the virtual environment.**

```bash
source .venv/bin/activate
```

Once activated, your shell prompt shows `(.venv)`, indicating that Python and
`pip` now refer to the environment you just created.

---

## Step 4 — Install Microbots with Contributor Tooling

Install the package in **editable mode** with the optional **`dev`** dependency
group. Editable mode (`-e`) links the installed package to your working copy, so
your code changes take effect without reinstalling. The `dev` extra adds
contributor-only tooling (`pre-commit` and `numpydoc`).

```bash
pip install -e ".[dev]"
```

> **Why the `dev` extra?** `pre-commit` is a developer tool, not a runtime
> dependency. Keeping it in the `dev` optional-dependency group means people who
> install Microbots to *use* it stay lean, while contributors receive everything
> they need with one command.

---

## Next Step

Your environment is ready. Continue to
**[Pre-commit Setup](pre-commit-setup.md)** to install the local checks that keep
your contributions consistent with the project's standards.
