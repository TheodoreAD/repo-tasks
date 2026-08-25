"""Wraps bump-my-version to bump every project sharing a version group in one commit+tag. Writes
a temporary per-group `.bumpversion.toml` at call time instead of a static one — confirmed
hands-on that bump-my-version's config-free CLI mode can't express a different search/replace
template per file, and a group's file set (which projects/charts belong to it) isn't fixed ahead
of time, only resolved from projects.py/repo-tasks.toml at call time.

One logical version, three spellings: the parts (`Version`) are the source of truth, and each
artifact kind serializes them its own way — PEP 440 in `pyproject.toml`/`uv.lock` (`1.1.0rc1`),
SemVer 2 in `Chart.yaml` and as the docker tag (`1.1.0-rc.1`). Nothing translates one string into
another; `docker.py`/`helm.py` ask for `semver()` and `dist.py` reads the PEP 440 form as-is. See
contributing/versioning.md."""

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dunamai import Version as GitVersion
from invoke import Context, task

from .projects import HelmChart, PythonProject, discover_helm_charts, discover_python_projects

_PEP440 = re.compile(
    r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:rc(?P<rc>\d+))?"
    r"(?:\.dev(?P<dev>\d+))?"
    r"(?:\+g(?P<commit>[0-9a-f]+))?$"
)
# What bump-my-version is ever asked to parse: a committed version, which is never a dev build.
_BUMP_PARSE = r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:(?P<pre_l>rc)(?P<pre_n>\d+))?"
_PEP440_SERIALIZE = '["{major}.{minor}.{patch}{pre_l}{pre_n}", "{major}.{minor}.{patch}"]'
_SEMVER_SERIALIZE = '["{major}.{minor}.{patch}-{pre_l}.{pre_n}", "{major}.{minor}.{patch}"]'

# `part` names accepted by `bump`/`next_version`, and the bump-my-version component each drives.
# major/minor/patch land on rc1 (the scheme's first pre-release value) unless the caller asks for
# a final version outright, which goes through --new-version instead — see _bump.
_PARTS = {"major": "major", "minor": "minor", "patch": "patch", "rc": "pre_n", "final": "pre_l"}


@dataclass(frozen=True)
class Version:
    """The parts every artifact kind's version string is rendered from. `rc` is None for a final
    version; `dev`/`commit` are set only on a dev build (`set_dev`), never on a committed one."""

    major: int
    minor: int
    patch: int
    rc: int | None = None
    dev: int | None = None
    commit: str | None = None

    @classmethod
    def parse(cls, text: str) -> "Version":
        """Parse the PEP 440 form this package writes: `X.Y.Z`, `X.Y.ZrcN`, and the dev-build
        shapes `X.Y.Z[rcN].devN[+gHASH]`. Anything else — alpha/beta, post, epoch, an unrelated
        local segment — is rejected by name: no file in a repo on these tasks should hold one."""
        match = _PEP440.match(text)
        if match is None:
            raise ValueError(
                f"unsupported version {text!r} — expected X.Y.Z, X.Y.ZrcN, or a dev build X.Y.Z[rcN].devN[+gHASH]"
            )
        rc, dev = match["rc"], match["dev"]
        return cls(
            major=int(match["major"]),
            minor=int(match["minor"]),
            patch=int(match["patch"]),
            rc=int(rc) if rc is not None else None,
            dev=int(dev) if dev is not None else None,
            commit=match["commit"],
        )

    @property
    def base(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def is_final(self) -> bool:
        return self.rc is None and self.dev is None

    def pep440(self) -> str:
        """`pyproject.toml`/`uv.lock`: `1.1.0`, `1.1.0rc2`, `1.0.1.dev3+g1a2b3c`. The commit rides
        in a local version, which PyPI rejects and a private index accepts — exactly the split a
        dev build wants."""
        text = self.base
        if self.rc is not None:
            text += f"rc{self.rc}"
        if self.dev is not None:
            text += f".dev{self.dev}"
        if self.commit is not None:
            text += f"+g{self.commit}"
        return text

    def semver(self) -> str:
        """`Chart.yaml` and docker tags: `1.1.0`, `1.1.0-rc.2`, `1.0.1-dev.3.g1a2b3c`. The commit
        goes inside the pre-release identifiers, never as `+` build metadata: a docker tag forbids
        `+`, and one spelling for both keeps the chart's `appVersion` equal to the image tag."""
        identifiers: list[str] = []
        if self.rc is not None:
            identifiers += ["rc", str(self.rc)]
        if self.dev is not None:
            identifiers += ["dev", str(self.dev)]
        if self.commit is not None:
            identifiers.append(f"g{self.commit}")
        return self.base + (f"-{'.'.join(identifiers)}" if identifiers else "")


def semver(text: str) -> str:
    """The SemVer 2 spelling of a PEP 440 version string this package wrote."""
    return Version.parse(text).semver()


def _resolve_project(c: Context, group: str | None):
    """The python project whose `[project].version` is the group's version. Absence is an error
    here, not a no-op like `dist.py`/`docker.py`/`helm.py`: nothing else can supply a version, so a
    bump has nothing to write and a `current_version` query has nothing to answer — say so, rather
    than an IndexError out of `[0]`."""
    python_projects = discover_python_projects(c)
    if group is not None:
        python_projects = [p for p in python_projects if p.name == group]
        if not python_projects:
            raise ValueError(f"no project found for group {group!r}")
    if not python_projects:
        raise ValueError("no python project found (no pyproject.toml [project] table and no workspace members)")
    return python_projects[0]


def current_version(c: Context, group: str | None = None):
    """The current version of one group's project (PEP 440 form), resolved via projects.py."""
    return _resolve_project(c, group).version


def next_version(current: str, part: str, rc: bool = True):
    """The version `bump` would produce for `part`, computed without writing or committing
    anything. Hand-rolled rather than shelling out to `bump-my-version show --increment`, and safe
    only because tests/integration pins every transition here against that very command on the
    same generated config — a scheme divergence fails a test, not a release. gitflow.py uses this
    to name a release/hotfix branch *before* the bump commit exists.

    `major`/`minor`/`patch` land on `rc1` of the bumped base, exactly as bump-my-version's part
    arithmetic does once a pre-release component exists; `rc=False` asks for the final version
    outright (a hotfix), which `_bump` then passes as `--new-version`. `rc` increments the
    candidate number, `final` drops it."""
    v = Version.parse(current)
    if v.dev is not None:
        raise ValueError(f"cannot bump from a dev build ({current!r}) — restore the committed version first")
    if part in ("major", "minor", "patch"):
        if part == "major":
            bumped = Version(v.major + 1, 0, 0)
        elif part == "minor":
            bumped = Version(v.major, v.minor + 1, 0)
        else:
            bumped = Version(v.major, v.minor, v.patch + 1)
        return Version(bumped.major, bumped.minor, bumped.patch, rc=1 if rc else None).pep440()
    if part == "rc":
        if v.rc is None:
            raise ValueError(f"{current!r} is a final version — start a new release/hotfix rather than bumping rc")
        return Version(v.major, v.minor, v.patch, rc=v.rc + 1).pep440()
    if part == "final":
        if v.rc is None:
            raise ValueError(f"{current!r} is already final")
        return Version(v.major, v.minor, v.patch).pep440()
    raise ValueError(f"unknown version part {part!r} (expected one of {', '.join(_PARTS)})")


def _toml_basic(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _toml_literal(value: str) -> str:
    return f"'{value}'"


@dataclass(frozen=True)
class _FileEntry:
    """One `[[tool.bumpversion.files]]` entry, kept as data so `set_dev` can apply the same
    search/replace pair directly — a dev version has no bump-my-version spelling (its `parse`
    would reject the `.devN+g...` tail), so the one file set is rendered two ways."""

    filename: Path
    search: str
    replace: str
    semver: bool  # this file spells the version as SemVer (Chart.yaml); PEP 440 otherwise

    def toml(self) -> str:
        entry = f'\n[[tool.bumpversion.files]]\nfilename = "{self.filename}"\n'
        # The uv.lock search is multi-line: a basic (double-quoted) TOML string keeps the `\n`
        # a real newline, where a literal (single-quoted) one would hand bump-my-version a
        # backslash and an `n`. Everything else contains double quotes and is literal-quoted.
        for key, value in (("search", self.search), ("replace", self.replace)):
            entry += f"{key} = {_toml_basic(value) if chr(10) in value else _toml_literal(value)}\n"
        if self.semver:
            entry += f"serialize = {_SEMVER_SERIALIZE}\n"
        return entry

    def rendered(self, current: Version, new: Version) -> tuple[str, str]:
        spell = Version.semver if self.semver else Version.pep440
        return (
            self.search.replace("{current_version}", spell(current)),
            self.replace.replace("{new_version}", spell(new)),
        )


def _file_entries(project: PythonProject, charts: list[HelmChart], lock_path: Path | None = None) -> list[_FileEntry]:
    entries = [
        _FileEntry(project.path / "pyproject.toml", 'version = "{current_version}"', 'version = "{new_version}"', False)
    ]
    # Anchored on the preceding `name = ...` line: uv.lock spells this project's own version
    # exactly like every dependency's (`version = "X"` inside a [[package]] block), so a bare
    # search would also hit any dependency pinned at the same number. The name line is unique
    # per package, and uv always writes it immediately before `version`.
    if lock_path is not None:
        entries.append(
            _FileEntry(
                lock_path,
                f'name = "{project.name}"\nversion = "{{current_version}}"',
                f'name = "{project.name}"\nversion = "{{new_version}}"',
                False,
            )
        )
    # The search patterns assume `helm create`'s own scaffold quoting: `version:` unquoted,
    # `appVersion:` quoted. The quoted appVersion form also keeps the bare `version: X` search
    # from matching inside the appVersion line (`version: X` is a substring of an unquoted
    # `appVersion: X`). bump-my-version fails loudly when a search string is absent, so a chart
    # straying from that quoting breaks the bump instead of half-applying it.
    for chart in charts:
        chart_yaml = chart.path / "Chart.yaml"
        entries.append(_FileEntry(chart_yaml, "version: {current_version}", "version: {new_version}", True))
        entries.append(_FileEntry(chart_yaml, 'appVersion: "{current_version}"', 'appVersion: "{new_version}"', True))
    return entries


def _bumpversion_config(
    project: PythonProject, charts: list[HelmChart], tag: bool, lock_path: Path | None = None
) -> str:
    tag_config = 'tag = true\ntag_name = "v{new_version}"' if tag else "tag = false"
    # uv.lock embeds the project's own version, and `uv sync --locked` rejects a lock whose copy
    # disagrees with pyproject.toml (astral-sh/uv#15643) — so a bump that left it alone would
    # commit a stale lock that fails the next `venv.sync` on a tree that looks clean. Rewriting
    # the field here keeps it in the same commit bump-my-version already owns; `uv lock --check`
    # as a pre-commit hook proves the rewrite left the lock consistent before anything is
    # committed, so a pattern that ever misfires fails the bump instead of shipping. Measured:
    # a text-rewritten version passes both `uv lock --check` and `uv sync --locked`.
    hook_config = 'pre_commit_hooks = ["uv lock --check"]\n' if lock_path is not None else ""
    # `pre_l`/`pre_n` give the scheme its rc cycle: every major/minor/patch bump resets them to
    # their first values (`rc`, `1`), `pre_n` counts candidates, and `pre_l` moving to its
    # optional value `final` drops both from the serialized string. Chart.yaml entries override
    # `serialize` to the SemVer spelling of the same parts.
    config = f"""\
[tool.bumpversion]
current_version = "{project.version}"
commit = true
{tag_config}
parse = '''{_BUMP_PARSE}'''
serialize = {_PEP440_SERIALIZE}
{hook_config}
[tool.bumpversion.parts.pre_l]
values = ["rc", "final"]
optional_value = "final"

[tool.bumpversion.parts.pre_n]
first_value = "1"
"""
    for entry in _file_entries(project, charts, lock_path):
        config += entry.toml()
    return config


def _lock_path() -> Path | None:
    # The workspace root's lock, never `project.path / "uv.lock"`: a workspace member has no lock
    # of its own, its version lives in the root one alongside every other member's.
    return Path("uv.lock") if Path("uv.lock").exists() else None


def _bump(c: Context, part: str, group: str | None = None, tag: bool = True, rc: bool = True):
    if part not in _PARTS:
        raise ValueError(f"unknown version part {part!r} (expected one of {', '.join(_PARTS)})")
    project = _resolve_project(c, group)
    charts = [chart for chart in discover_helm_charts(c) if chart.group == project.name]
    config = _bumpversion_config(project, charts, tag, lock_path=_lock_path())
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        _ = f.write(config)
        config_path = Path(f.name)

    cmd = f"bump-my-version bump {_PARTS[part]} --config-file {config_path}"
    if part in ("major", "minor", "patch") and not rc:
        # bump-my-version's own arithmetic can only land on rc1 here (pre_n resets to its first
        # value); the final version is stated outright instead, in one commit.
        cmd += f" --new-version {next_version(project.version, part, rc=False)}"
    try:
        c.run(cmd, echo=True)
    finally:
        config_path.unlink()

    return discover_python_projects(c)[0].version


@task(
    help={
        "part": "major/minor/patch (land on rc1), rc (next candidate), or final (drop the rc)",
        "group": "Version group to bump (default: the repo's own root project)",
        "tag": "Tag the bump commit vX.Y.Z[rcN] (default: yes)",
        "rc": "For major/minor/patch: bump to rc1 (default) or straight to the final version (--no-rc)",
    }
)
def bump(c: Context, part: str, group: str | None = None, tag: bool = True, rc: bool = True):
    """Bump one version group: writes the new version into every file that group's projects live
    in and commits. Tags `vX.Y.Z[rcN]` unless `tag=False` — gitflow.py's release_start/hotfix_start
    pass tag=False since the final tag belongs on main at finish time, not on develop at bump
    time. Returns the new version string."""
    return _bump(c, part, group=group, tag=tag, rc=rc)


def _dev_version(commit_length: int = 7) -> Version:
    """The version of the working tree's HEAD as a dev build, dunamai's scheme: the next patch of
    the nearest final tag (or the next candidate of a nearest rc tag), then the commit distance
    and short hash. Exactly at a tag it is the tag's own version — a dev build of a release commit
    is that release."""
    git = GitVersion.from_git(commit_length=commit_length)
    if git.distance == 0:
        return Version.parse(git.base if git.stage is None else f"{git.base}rc{git.revision}")
    bumped = git.bump()
    rc = bumped.revision if bumped.stage == "rc" else None
    return Version.parse(f"{bumped.base}{f'rc{rc}' if rc is not None else ''}.dev{git.distance}+g{git.commit}")


@task(help={"group": "Version group to rewrite (default: the repo's own root project)"})
def set_dev(c: Context, group: str | None = None):
    """Write a dev-build version into the working tree — `pyproject.toml`, `uv.lock`, and every
    chart in the group — without committing: `1.0.1.dev3+g1a2b3c` from a tree three commits past
    `v1.0.0`, `1.0.1-dev.3.g1a2b3c` in the charts. For `dist.build --dev`/`docker.build --dev`/
    `helm.package --dev`, which call it first. Refuses on a dirty tree, so it can never write over
    uncommitted work and the undo is always the `git restore` it prints; a CI checkout is clean by
    construction. Returns the new PEP 440 string."""
    dirty = subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, text=True).stdout
    if dirty.strip():
        raise ValueError(
            "working tree is dirty — set_dev only rewrites a clean checkout, so its undo is a plain git restore"
        )
    project = _resolve_project(c, group)
    charts = [chart for chart in discover_helm_charts(c) if chart.group == project.name]
    current = Version.parse(project.version)
    new = _dev_version()
    entries = _file_entries(project, charts, lock_path=_lock_path())
    for entry in entries:
        search, replace = entry.rendered(current, new)
        text = entry.filename.read_text()
        if search not in text:
            raise ValueError(f"did not find {search!r} in {entry.filename} — nothing rewritten")
        _ = entry.filename.write_text(text.replace(search, replace, 1))
        print(f"[version.set_dev] {entry.filename}: {search.splitlines()[-1]} -> {replace.splitlines()[-1]}")
    print(f"[version.set_dev] undo with: git restore {' '.join(str(e.filename) for e in entries)}")
    return new.pep440()
