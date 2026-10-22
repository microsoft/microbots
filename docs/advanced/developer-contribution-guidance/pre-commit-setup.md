# Pre-commit Setup

This article is part of the
**[Developer Contribution Guidance](index.md)** series. It assumes you have
already completed the [Environment Setup](index.md) article, including installing
Microbots with the `dev` extra.

Microbots uses [`pre-commit`](https://pre-commit.com/) to run automated quality
checks before each commit. The primary check validates that docstrings follow the
project's NumPy style. Running these checks locally means issues are caught on
your machine instead of in continuous integration (CI).

---

## Step 1 — Activate the Git Hooks

Installing the `pre-commit` *package* (done via the `dev` extra) is not enough.
You must also wire it into git so the checks run automatically.

**Activate the git hooks.** Run this once per clone.

```bash
pre-commit install
```

This command writes a hook into `.git/hooks/pre-commit`. From now on, every
`git commit` runs the configured checks against the files you have **staged**.

> **This is a per-clone step.** The `.git/hooks/` directory is not tracked by git,
> so every contributor must run `pre-commit install` once after cloning. If you
> clone the repository again, run it again.

---

## Step 2 — Run the Checks on the Files You Changed

You do not have to wait for a commit to run the checks, and you only need to
validate the files **you** changed — not the entire codebase. The repository
contains pre-existing docstring issues in files unrelated to your contribution.
Resolving those is outside the scope of your change, so limit your validation to
the files you have modified.

Pick the command that matches what you want to do:

| You want to…                                   | Run this command                                                                                                |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Validate a single file you edited              | `pre-commit run numpydoc-validation --files src/microbots/bot/LogAnalysisBot.py`                                |
| Validate several specific files                | `pre-commit run numpydoc-validation --files src/microbots/bot/LogAnalysisBot.py src/microbots/utils/network.py` |
| Validate everything you have staged for commit | `pre-commit run numpydoc-validation`                                                                            |

Notes on the commands above:

- **`--files <paths>`** scopes the check to exactly the files you list, separated
  by spaces. Use this while you iterate on specific modules.
- **Without `--all-files`**, `pre-commit` runs against your **staged** files only,
  so it validates exactly what you are about to commit.

> **Windows note:** If you encounter a `UnicodeDecodeError` while running the hook
> locally, set the UTF-8 mode first, then run the command again:
>
> ```bash
> export PYTHONUTF8=1
> ```
>
> This addresses a Windows-only default encoding (`cp1252`). Linux and CI runners
> default to UTF-8 and are unaffected.

---

## Step 3 — Understand the Output

When a docstring is missing or malformed, the hook prints a table that points at
the exact object and the rule it violated:

```text
+-----------------------------------------+--------------------------------+-------+--------------------------------------+
| file                                    | item                           | check | description                          |
+-----------------------------------------+--------------------------------+-------+--------------------------------------+
| src/microbots/bot/LogAnalysisBot.py:55  | LogAnalysisBot.__init__        | PR01  | Parameters {'token_provider'} not    |
|                                         |                                |       | documented                           |
+-----------------------------------------+--------------------------------+-------+--------------------------------------+
```

The `check` column reports a code. The most common codes are:

| Code   | Meaning                                           |
| ------ | ------------------------------------------------- |
| `GL08` | The object has no docstring at all                |
| `PR01` | A parameter is not documented                     |
| `RT01` | No `Returns` section found                        |
| `SS01` | No one-line summary at the start of the docstring |

To learn how to write docstrings that satisfy these checks, continue to
**[Docstring & Writing Guidelines](docstring-and-writing-guidelines.md)**.

---

## How the Same Check Runs in CI

The identical validation runs on every pull request as the **NumPy docstring
guide** check. It is currently **informational and non-blocking**: it reports the
project's docstring coverage and surfaces issues without preventing a merge.

> Docstring coverage: 13% (31/245) · non-blocking

As coverage improves, this check is intended to become a required gate. Even while
it is non-blocking, fix any docstring issues your change introduces so coverage
trends upward.

> **Tip:** Because CI re-runs the check regardless of your local setup, fixing
> the docstrings in your changed files before you push saves a review
> round-trip. Running `pre-commit run numpydoc-validation --files <your files>`
> before pushing is the most reliable way to stay consistent with CI.

---

## Recommended Contributor Workflow

1. Create a feature branch off `main`.
2. Make your changes, including NumPy-style docstrings for any new or modified
   public classes, functions, and methods.
3. Run `pre-commit run numpydoc-validation --files <the files you changed>` and
   resolve the issues reported for **your** files only.
4. Commit your work — the hooks run automatically against your staged files.
5. Push your branch and open a pull request. Confirm that the **NumPy docstring
   guide** check reflects your changes.

---

## Next Step

Continue to **[Docstring & Writing Guidelines](docstring-and-writing-guidelines.md)**
to learn how to write docstrings and documentation that meet the project's
standards.
