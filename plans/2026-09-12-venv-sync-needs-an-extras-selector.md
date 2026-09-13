---
status: idea
updated: 2026-09-12
---

# `venv.sync` cannot select extras, and a runtime image needs to

## Context

Found 2026-09-12 in `ingesta`, writing the `Dockerfile` its container plan calls for. That plan says
to adopt this repository's recipe — `tests/fixtures/sample-service/Dockerfile` — rather than
hand-write one, and it anticipated this exact gap:

> the deps layer needs the `store` and the new `api` extras and not `cli` or `bot`, and whether
> `inv venv.sync` takes an extras selector is unverified here. If it does not, that is a small
> `repo-tasks` change rather than a reason to hand-roll `uv` commands in the Dockerfile.

Checked: it does not. `venv.sync` takes `project`, `no_editable`, `no_dev`, `no_install_project` and
`python`, and builds `uv sync --locked` from them. There is no `--extra`, no `--all-extras` and no
`--group`.

## Why it blocks rather than inconveniences

`ingesta` keeps its deployable layers in **extras**, deliberately: the wheel is an engine artifact a
browser installs with `micropip`, so SQLAlchemy, aiogram and FastAPI are `store`, `bot` and `api`
rather than dependencies. A runtime image wants exactly two of the four.

Every way of getting there without this change is worse:

- **`inv venv.sync --no-dev`** installs the project's dependencies, which for that repository is one
  package. The image would have no database driver and no web framework.
- **`inv venv.sync`** with dev installs the extras, because its dev group names them — and brings
  pytest, hypothesis, playwright, act and hadolint into a production image with them.
- **`uv pip install 'dist/ingesta-*.whl[store,api]'`** resolves from the index rather than the lock,
  which is the property the deps layer exists to hold.
- **Hand-writing `uv sync --locked --extra store --extra api`** in the Dockerfile is what that plan
  says not to do, and the sample's own comment gives the reason: every build step goes through the
  tasks, which is how the tasks stay proven against a real image.

## Recommended direction

Add `extra: list[str] | None` and, probably, `group: list[str] | None` to `venv.sync`, appending
`--extra <name>` / `--group <name>` per entry. `uv` takes both repeatably and the defaults are
unchanged when neither is given, so no existing caller moves.

Worth deciding at the same time, since they are the same question: whether `--all-extras` is worth
carrying. The argument for is that a one-extra repository never wants to name it; the argument
against is that an image built with every extra is the fat-image default this change exists to
avoid, and a repository that wants all of them can say so.

**What makes this small is that the sample would exercise it.** `sample-service` has no extras
today, so proving the flag reaches `uv` means either giving the fixture one or asserting the
composed command — and the first is the one that matches how the rest of that fixture is used.

## What this is not

Not a request to change how `ingesta` is laid out. Extras are the right shape there for a reason
that plan records at length: the wheel is the artifact three runtimes install, and a browser must
not download a web framework to compute a dose.
