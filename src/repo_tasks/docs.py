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


@task(pre=[clean])
def build(c: Context):
    """Build the docs site with zensical in strict mode (fails on any warning)."""
    c.run("zensical build --strict", echo=True)


@task
def serve(c: Context):
    """Serve the docs site locally with live reload (zensical serve)."""
    c.run("zensical serve", echo=True)
