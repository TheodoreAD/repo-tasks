"""Docs-site build tasks, wrapping zensical (mkdocs.yml-compatible, see zensical.org). Assumes
the consumer's `docs` uv dependency group is installed (`uv sync --group docs`) — `zensical`
itself isn't a dependency of this package.

`link_check` is the exception: it needs no zensical, no dependency at all, and runs in the gate."""

import re
import shutil
from pathlib import Path

from invoke import Context, Exit, task

from .projects import tracked_files

_SITE_DIR = Path("site")

# `[text](target)`, with markdown's optional `"title"` after the target. Deliberately narrow: no
# reference-style definitions, no HTML anchors, no bare autolinks — every one of those is a way to
# write a link this does not check, which is a smaller failure than flagging text that is not one.
_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")

_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

# Anything with a scheme is somebody else's uptime, not this repo's correctness.
_EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://")


def _relative_links(text: str) -> list[tuple[int, str]]:
    """Every relative link target in a markdown document, as (line number, target).

    Fenced blocks are skipped: a code sample showing markdown syntax is documentation, not a link
    this repo has to keep working."""
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _LINK_RE.finditer(line):
            target = match.group(1)
            if not target.startswith(_EXTERNAL) and not target.startswith("#"):
                found.append((number, target))
    return found


def _broken_link(source: Path, target: str) -> str | None:
    """The unresolvable path a link points at, or None when it resolves.

    The fragment is stripped and not checked further — `file.md#heading` verifies the file, never
    the heading, so a renamed heading still passes. Whole-document fragments (`#heading` alone) are
    filtered out before this."""
    path_part = target.split("#", 1)[0]
    if not path_part:
        return None
    # A leading slash means repo root, the way a docs site would serve it; everything else resolves
    # against the directory of the file doing the linking.
    resolved = Path.cwd() / path_part.lstrip("/") if path_part.startswith("/") else source.parent / path_part
    return None if resolved.exists() else path_part


@task
def link_check(c: Context):
    """Check that every relative link in the repo's markdown resolves to a file that exists.

    Relative links only — external URLs are somebody else's uptime, and checking them would make
    this a network call, which is what keeps it out of the gate. No-ops cleanly on a repo with no
    markdown at all.

    The failure it exists for is the plan-retirement procedure's: retiring a plan deletes a file
    that other documents link to, and the procedure's "grep for inbound references" step was
    honour-system until now. Both of this convention's own plans shipped a dangling link on their
    first commit."""
    broken: list[str] = []
    for name in tracked_files(c, "*.md"):
        source = Path(name)
        text = source.read_text()
        broken.extend(
            f"{name}:{number}: {missing}"
            for number, target in _relative_links(text)
            if (missing := _broken_link(source, target)) is not None
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


@task(pre=[clean])
def build(c: Context):
    """Build the docs site with zensical in strict mode (fails on any warning)."""
    c.run("zensical build --strict", echo=True)


@task
def serve(c: Context):
    """Serve the docs site locally with live reload (zensical serve)."""
    c.run("zensical serve", echo=True)
