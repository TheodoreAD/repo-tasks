# repo-tasks

Shared, reproducible quality-tooling [invoke](https://www.pyinvoke.org/) tasks — `lint`/`format`/
`type_check`/`shell_check`/`test`, and the composite `fix`/`check`/`precommit` graph — for personal
Python repos, extracted from
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
from invoke import Collection
from repo_tasks import quality

ns = Collection.from_module(quality)
```

That's the entire file — no local override. `inv precommit` is then the single command,
identical across every consumer repo (`Collection.from_module` assigned directly as `ns` puts the
module's tasks at the root, not behind a `quality.` prefix — that prefix only shows up in a repo that
instead does `namespace.add_collection(Collection.from_module(quality))`, e.g.
`power-user-linux-setup`'s own `tasks/__init__.py`). Every leaf task (`lint_check`, `type_check`,
`test`, ...) is also individually invocable (`inv test`, etc.) — each has its own docstring, so
`inv -l` alone is enough to know what's available.

Every consumer repo needs its own `pyrightconfig.json` — `check` runs `type_check` unconditionally
(no allowances), so type-check config must exist everywhere `check` runs.

## Developing

```shell
uv sync
inv precommit
```

This repo dogfoods its own tasks against itself (`tasks.py` wires up the same `quality` module a
consumer would import).
