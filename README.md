# repo-tasks

Shared, reproducible [invoke](https://www.pyinvoke.org/) tasks for personal Python repos —
`quality` (`lint`/`format`/`type_check`/`shell_check`/`test`, and the composite `fix`/`check`/
`precommit` graph), `dev_env` (`venv`/`claude_hook`/`setup` — the one-time dev-loop bootstrap after
cloning), and `docs` (`clean`/`build`/`serve`, wrapping [zensical](https://zensical.org/)) —
extracted from
[power-user-linux-setup](https://github.com/TheodoreAD/power-user-linux-setup)'s own `tasks/`
directory so a fix or improvement lands once and reaches every consumer deliberately (a pinned
dependency bump), instead of being hand-copied and silently drifting per repo.

## Design

No per-repo allowances: every consumer uses the identical `fix`/`check`/`precommit` composite,
unmodified. `precommit` (`fix` then `check`) is the one command an agent always runs — no need to
know or invoke the individual tools. Every task, leaf and composite alike, carries a succinct
one-line docstring — what `inv -l` shows as help text. Every command echoes (`echo=True`) what it
ran, except a step that would involve a secret (none here do). `shell_check`/`shell_format_*`
no-op cleanly on a repo with zero `*.sh` files, so they're safe to run unconditionally — no
per-repo opt-out needed.

Each tool gets its own dedicated config file (`ruff.toml`, `pyrightconfig.json`, `pytest.ini`) —
not consolidated into `pyproject.toml` — so a template-driven config update across many repos can
diff/replace one file cleanly instead of risking a monolithic block.

## Installing

```shell
uv add --dev git+https://github.com/TheodoreAD/repo-tasks
```

Git-as-artifact-store, no PyPI. `uv.lock` freezes an exact commit — a later fix reaches a consumer
only via a deliberate `uv lock --upgrade-package repo-tasks` (or a pinned `@<tag>` bump) plus a
committed lockfile change, not automatically.

## Using

```python
# consumer repo's tasks.py, at the repo root
from repo_tasks import ns
```

That's the entire file — no local override, no `add_collection` boilerplate. `ns` is a ready-made
root `Collection` with every task module this package ships already nested under its own name, so
`inv quality.precommit` is the one command, identical across every consumer repo, and stays that way
automatically as new modules (`docker`, `python_pkg`, `helm`, ...) land here — nothing to change on
the consumer side when they do. Every leaf task (`lint_check`, `type_check`, `test`, ...) is also
individually invocable (`inv quality.test`, etc.) — each has its own docstring, so `inv -l` alone is
enough to know what's available.

Each module is also importable on its own (`from repo_tasks import quality`) for a consumer that
wants to hand-pick a subset rather than take the full `ns` — see `src/repo_tasks/__init__.py` for
the exact wiring `ns` does, to replicate a narrower version of it.

Every consumer repo needs its own `pyrightconfig.json` — `check` runs `type_check` unconditionally
(no allowances), so type-check config must exist everywhere `check` runs.

`inv dev-env.setup` is the one command to run once after cloning: `uv sync` + `direnv allow`, plus
wiring Claude Code's Bash tool to auto-activate the venv too (`claude-hook`, no-ops if the repo has
no `.envrc`). `inv docs.build`/`docs.serve` assume `zensical` is installed — add it as a project
`docs` dependency group, it isn't a dependency of this package.

## Developing

```shell
uv sync
inv quality.precommit
```

This repo dogfoods its own tasks against itself (`tasks.py` is `from repo_tasks import ns` — the
same one-liner a consumer uses).
