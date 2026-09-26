"""Dependency lock-file operations. The only module in this package allowed to write uv.lock —
`venv.py`'s `--locked` sync fails loudly on drift instead of ever silently regenerating it."""

import builtins
import re
import tomllib
from pathlib import Path
from typing import cast

from invoke import Context, Exit, task

from .configs import quality_dep_names
from .nextsteps import next_steps
from .requirements import NETWORK, requires

# The one `uv lock` failure a plain re-run never fixes: a workspace member that *moved*. uv.lock
# records the member's `source = { editable = "<old path>" }` and uv reads that stale entry before
# noticing the manifest changed, so both `uv lock` and `uv lock --check` fail with this message
# (exit 2), naming a path that no longer exists. `--upgrade-package <member>` re-resolves it.
# Measured against uv 0.11.19: renaming a member (path unchanged) or removing it outright both
# re-resolve fine — only a move does this.
_MOVED_MEMBER_RE = re.compile(r"Failed to generate package metadata for `(?P<name>[^=` ]+)[^`]*@ editable\+")


@requires(NETWORK)
@task(
    help={
        "upgrade": "Fully re-resolve every dependency",
        "package": "Upgrade one package deliberately (--upgrade-package)",
    }
)
def lock(c: Context, upgrade: bool = False, package: str | None = None):
    """Write/update uv.lock. The only task in this package that ever runs `uv lock`."""
    cmd = "uv lock"
    if upgrade:
        cmd += " --upgrade"
    if package:
        cmd += f" --upgrade-package {package}"
    result = c.run(cmd, echo=True, warn=True)
    if result.ok:
        return
    match = _MOVED_MEMBER_RE.search(result.stderr)
    if match:
        print(
            f"\n[deps.lock] workspace member {match.group('name')!r} looks moved — uv.lock still records its old "
            "path, and a plain `uv lock` never re-resolves that."
        )
        next_steps(f"inv deps.lock --package {match.group('name')}")
    raise Exit(code=result.exited)


@task
def check(c: Context):
    """Check uv.lock is up-to-date with pyproject.toml, read-only, no .venv needed. A gate step,
    echoed like every effectful command, so report mode reports it (see runner.py)."""
    c.run("uv lock --check", echo=True)


@requires(NETWORK)
@task
def audit(c: Context):
    """Check the locked dependency set for known advisories (uv audit --locked).

    Needs network: it queries the OSV database, so the answer changes when OSV changes rather than
    when this repo does. That is why this is a standalone task and never a step in `quality.check`
    — a gate step whose result moves on its own fails commits that changed nothing, and would put a
    network call in every consumer's `precommit`.

    `--locked` audits exactly what uv.lock commits to, which is what a consumer actually installs;
    it also keeps this module's single-writer rule intact, since a re-resolving audit would report
    on a dependency set nobody has.
    """
    # `uv audit` is experimental as of uv 0.11 and prints a warning saying so. Left visible on
    # purpose: silencing it means `--preview-features audit-command`, and an unknown feature name is
    # a hard error ("invalid value ... Unknown feature flag"), so that flag breaks outright the day
    # uv graduates the command and retires it. The warning is informative and cannot rot.
    c.run("uv audit --locked", echo=True)


_LOCK_PATH = Path("uv.lock")

# One package line of `uv tree --depth 1 --outdated`: `├── ruff v0.16.3 (group: dev) (latest: v0.16.9)`.
# The latest clause is absent when the lock is current, and always absent for a git source, which uv
# does not look up.
_TREE_LINE_RE = re.compile(
    r"[├└]── (?P<name>\S+) v(?P<version>\S+)(?: \([^)]*\))*?(?: \(latest: v(?P<latest>[^)]+)\))?$"
)

_CURRENCY_TREE_CMD = "uv tree --outdated --depth 1 --locked --only-group dev --quiet"


def _git_sources() -> dict[str, tuple[str, str]]:
    """Every git-sourced package in uv.lock, bare name -> (repository URL, locked commit).

    uv records `source = { git = "<url>#<sha>" }`, sometimes with a `?rev=` query before the `#`;
    the URL is kept without it, since the question asked of it is only where the default branch is."""
    data = tomllib.loads(_LOCK_PATH.read_text(encoding="utf-8"))
    found: dict[str, tuple[str, str]] = {}
    # `builtins.list`, because this module's own `list` task shadows the builtin for both the
    # interpreter and the type checker.
    for package in cast(builtins.list[dict[str, object]], data.get("package", [])):
        source = cast(dict[str, str], package.get("source", {}))
        if "git" in source:
            url, _, sha = source["git"].partition("#")
            found[str(package["name"]).lower()] = (url.split("?", 1)[0], sha)
    return found


def _remote_head(c: Context, url: str) -> str | None:
    result = c.run(f"git ls-remote {url} HEAD", hide=True, warn=True)
    if not result.ok or not result.stdout.strip():
        return None
    return result.stdout.split()[0]


def _locked_tree(c: Context) -> dict[str, tuple[str, str | None]]:
    """The dev group's direct packages, bare name -> (locked version, latest or None when current)."""
    result = c.run(_CURRENCY_TREE_CMD, hide=True, warn=True)
    if not result.ok:
        raise Exit(f"[deps.check-currency] `{_CURRENCY_TREE_CMD}` failed:\n{result.stderr.strip()}", code=result.exited)
    tree: dict[str, tuple[str, str | None]] = {}
    for line in result.stdout.splitlines():
        if match := _TREE_LINE_RE.search(line):
            tree[match["name"].lower()] = (match["version"], match["latest"])
    return tree


def _git_verdict(c: Context, url: str, locked: str) -> tuple[str, bool]:
    """A git entry's verdict line, and whether it is behind — against its default-branch head,
    the only "latest" a git source has."""
    head = _remote_head(c, url)
    if head is None:
        return f"git, locked at {locked[:12]} — could not read {url}'s head", False
    if head == locked:
        return f"git, locked at {locked[:12]} — current with its default branch", False
    return f"BEHIND — git, locked at {locked[:12]}, default branch is at {head[:12]}", True


@requires(NETWORK)
@task(name="check-currency")
def check_currency(c: Context):
    """Report which `repo-tasks-quality` entries this project's lock holds behind their latest
    release. Reads only, needs the network, exits zero.

    The drift `configs.diff` cannot see. That command asks whether each manifest entry is
    **declared**; an entry declared without a version is then frozen at whatever the consumer's lock
    resolved on the day, and nothing reported it — measured 2026-09-08, `power-user-linux-setup` held
    `invoke-stubs` two releases back while `configs.diff` called it up to date. Settled 2026-09-26 as
    a detector for every entry rather than pinning any of them: `configs.ensure-deps` stays
    additive-only, and the judgement of when to move stays with whoever reads this.

    PyPI entries go through `uv tree --outdated`, so a consumer's own index configuration is
    honoured rather than pypi.org assumed. A git entry is invisible to that — uv does not look one up
    — so its locked commit is compared with the remote's default-branch head, which is the only
    "latest" such an entry has. Never in `quality.check`: the answer moves when an index does, the
    same reason `deps.audit` stands alone."""
    if not _LOCK_PATH.exists():
        print("[deps.check-currency] no uv.lock — nothing to check")
        return
    names = quality_dep_names()
    tree = _locked_tree(c)
    git = _git_sources()

    behind: builtins.list[str] = []
    for name in names:
        if name not in tree:
            print(f"[deps.check-currency] {name}  not in this project's dev group — `inv configs.diff` reports that")
            continue
        version, latest = tree[name]
        if name in git:
            verdict, is_behind = _git_verdict(c, *git[name])
        else:
            verdict, is_behind = ("current", False) if latest is None else (f"BEHIND — latest {latest}", True)
        if is_behind:
            behind.append(name)
        print(f"[deps.check-currency] {name} {version}  {verdict}")

    noun = "entry" if len(names) == 1 else "entries"
    print(f"[deps.check-currency] {len(behind)} of {len(names)} manifest {noun} behind")
    if behind:
        next_steps(*(f"inv deps.lock --package {name}" for name in behind))


@task(help={"outdated": "Show the latest available version of each installed package"})
def list(c: Context, outdated: bool = False):  # noqa: A001 — this is the CLI task name (`inv deps.list`), matches uv's own `list` verb
    """List what's actually installed in .venv (uv pip list)."""
    cmd = "uv pip list"
    if outdated:
        cmd += " --outdated"
    c.run(cmd, echo=True)


@task(help={"outdated": "Show the latest available version of each package in the tree"})
def tree(c: Context, outdated: bool = False):
    """Show the full resolved dependency tree from uv.lock (uv tree)."""
    cmd = "uv tree"
    if outdated:
        cmd += " --outdated"
    c.run(cmd, echo=True)


@task(help={"output": "Output path for the exported requirements file", "no_dev": "Skip the dev dependency group"})
def export(c: Context, output: str = "requirements.txt", no_dev: bool = False):
    """Export uv.lock to a pinned requirements.txt (--locked, non-editable) for non-uv-aware
    consumers — SBOM/vulnerability scanners, plain-pip CI steps."""
    cmd = "uv export --format requirements.txt --locked --no-editable"
    if no_dev:
        cmd += " --no-dev"
    cmd += f" -o {output}"
    c.run(cmd, echo=True)
