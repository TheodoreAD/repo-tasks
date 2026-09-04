"""Docs-site build tasks, wrapping zensical (mkdocs.yml-compatible, see zensical.org). Assumes
the consumer's `docs` uv dependency group is installed (`uv sync --group docs`) — `zensical`
itself isn't a dependency of this package.

`link_check` needs no zensical and no dependency at all. `build` is in the gate too, but on the
weaker terms its own docstring sets out: it no-ops without an mkdocs.yml, so a consumer with no
docs site pays nothing and needs no group."""

import re
import shutil
from pathlib import Path

from invoke import Context, Exit, task

from .projects import tracked_files

_SITE_DIR = Path("site")

# What "this repo has a docs site" means. zensical reads mkdocs.yml, so its presence is the same
# question the build itself would ask, one step earlier and without needing zensical installed.
_MKDOCS_CONFIG = Path("mkdocs.yml")

# `[text](target)`, with markdown's optional `"title"` after the target. Deliberately narrow: no
# reference-style definitions, no HTML anchors, no bare autolinks — every one of those is a way to
# write a link this does not check, which is a smaller failure than flagging text that is not one.
_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")

_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

# An inline code span: a run of backticks, content holding no run that long, the same run again.
# `def evolve[T: BaseModel](...)` is a valid inline link to `...` as far as `_LINK_RE` is concerned,
# and PEP 695 generics make that shape ordinary prose rather than an exotic one. Same reasoning as
# the fence skip: a code sample that happens to read as markdown is documentation, not a link.
_CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)*\1")

# Anything with a scheme is somebody else's uptime, not this repo's correctness.
_EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://")


def _relative_links(text: str) -> list[tuple[int, str]]:
    """Every relative link target in a markdown document, as (line number, target).

    Fenced blocks and inline code spans are both skipped: a code sample showing markdown syntax is
    documentation, not a link this repo has to keep working. [PITFALL: the span half was missing at
    first, and `def f[T](x)` in prose about PEP 695 generics is a valid `[text](target)` — the gate
    went red on correct input, and the only way to green was rewording prose around the bug.
    Measured across every markdown file in the repo family: stripping spans loses no real link.]"""
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Blanked rather than removed, so a reported line still lines up with the source.
        prose = _CODE_SPAN_RE.sub(lambda span: " " * len(span.group(0)), line)
        for match in _LINK_RE.finditer(prose):
            target = match.group(1)
            if not target.startswith(_EXTERNAL) and not target.startswith("#"):
                found.append((number, target))
    return found


def _bad_link(source: Path, target: str) -> str | None:
    """Why a link is wrong, or None when it is fine.

    The fragment is stripped and not checked further — `file.md#heading` verifies the file, never
    the heading, so a renamed heading still passes. Whole-document fragments (`#heading` alone) are
    filtered out before this."""
    path_part = target.split("#", 1)[0]
    if not path_part:
        return None
    # A leading slash means repo root, the way a docs site would serve it; everything else resolves
    # against the directory of the file doing the linking.
    root = Path.cwd().resolve()
    resolved = root / path_part.lstrip("/") if path_part.startswith("/") else (source.parent / path_part).resolve()
    if not resolved.is_relative_to(root):
        # A `../../other-repo/file.md` resolves on a machine that happens to have both repos
        # checked out as siblings and nowhere else — it is dead on GitHub and unresolvable in CI,
        # so it is wrong even while it "works" locally. Reported as its own kind of wrong rather
        # than as missing, because the fix is different: link the URL, not the path.
        return f"{path_part} (escapes the repository — link the URL instead)"
    return None if resolved.exists() else path_part


@task
def link_check(c: Context):
    """Check that every relative link in the repo's markdown resolves to a file in this repo.

    Relative links only — external URLs are somebody else's uptime, and checking them would make
    this a network call, which is what keeps it out of the gate. No-ops cleanly on a repo with no
    markdown at all.

    Two ways a link fails: it names a file that does not exist, or it climbs out of the repository
    (`../../other-repo/file.md`). The second only resolves for someone with both repos checked out
    as siblings — it is dead on GitHub and unresolvable in CI — so it counts as broken even though
    a local run can open it. [PITFALL: it did not, at first, and that is exactly the
    green-locally-red-in-CI divergence the gate exists to prevent. One such link kept CI red for a
    day while `inv quality.check` passed on the machine that wrote it.]

    The failure it exists for is the plan-retirement procedure's: retiring a plan deletes a file
    that other documents link to, and the procedure's "grep for inbound references" step was
    honour-system until now. Both of this convention's own plans shipped a dangling link on their
    first commit."""
    broken: list[str] = []
    for name in tracked_files(c, "*.md"):
        source = Path(name)
        text = source.read_text()
        broken.extend(
            f"{name}:{number}: {problem}"
            for number, target in _relative_links(text)
            if (problem := _bad_link(source, target)) is not None
        )
    if not broken:
        return
    for entry in broken:
        print(f"[docs.link-check] {entry}")
    raise Exit(f"[docs.link-check] {len(broken)} broken relative link(s)", code=1)


@task
def clean(c: Context):
    """Remove the built docs site (site/)."""
    if not _SITE_DIR.exists():
        print("[docs.clean] site/ not present — nothing to clean")
        return
    shutil.rmtree(_SITE_DIR)
    print("[docs.clean] site/ removed")


def _require_zensical() -> None:
    """Preflight zensical, naming the group that supplies it.

    Deliberately not `configs.require_tool`, which is right for every other gate binary and wrong
    for this one: its message names the `repo-tasks-quality` manifest and `dependency-groups.dev`,
    and zensical is in neither. It is the consumer's own `docs` group, so a consumer following that
    remediation would sync the wrong group and see no change."""
    if shutil.which("zensical") is not None:
        return
    print(
        "[docs.build] zensical not found on PATH — this repo has an mkdocs.yml, so the docs site "
        "is meant to build, but zensical is not installed in this project's environment. It comes "
        "from the consumer's own `docs` dependency group, not from repo-tasks."
    )
    print("[docs.build] next: uv sync --group docs")
    raise Exit(code=1)


@task(pre=[clean])
def build(c: Context):
    """Build the docs site with zensical in strict mode (fails on any warning).

    In `quality.check`, because `--strict` is the only check in this family that sees a dangling
    anchor: `link_check` strips the fragment by design, so a renamed heading passes it. That gap
    shipped a red Pages deploy twice in one consumer while `CI` stayed green on both commits.

    No-ops cleanly on a repo with no `mkdocs.yml`, which is what makes it safe to run
    unconditionally in every consumer's gate — most of them have no docs site, and none of them
    declares zensical on repo-tasks' behalf. [PITFALL: the no-op is keyed on the config file rather
    than on whether zensical is installed. Keying on the tool would make "the docs group is not
    synced" indistinguishable from "this repo has no docs", which is the silent-pass shape this
    whole step exists to remove.]"""
    if not _MKDOCS_CONFIG.exists():
        print(f"[docs.build] no {_MKDOCS_CONFIG} — this repo has no docs site, nothing to build")
        return
    _require_zensical()
    c.run("zensical build --strict", echo=True)


@task
def serve(c: Context):
    """Serve the docs site locally with live reload (zensical serve)."""
    c.run("zensical serve", echo=True)
