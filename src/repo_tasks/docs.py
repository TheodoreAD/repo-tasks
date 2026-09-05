"""Docs-site build tasks, wrapping zensical (mkdocs.yml-compatible, see zensical.org). Assumes
the consumer's `docs` uv dependency group is installed (`uv sync --group docs`) — `zensical`
itself isn't a dependency of this package.

`link_check` needs no zensical and no dependency at all. `build` is in the gate too, but on the
weaker terms its own docstring sets out: it no-ops without an mkdocs.yml, so a consumer with no
docs site pays nothing and needs no group."""

import re
import shutil
import unicodedata
from collections.abc import Callable
from difflib import get_close_matches
from pathlib import Path

from invoke import Context, Exit, task

from .projects import tracked_files
from .steps import run_step

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

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")

# python-markdown's attr_list: `## Heading {#custom-id}`.
_ATTR_LIST_ID_RE = re.compile(r"\s*\{#([^}\s]+)\}\s*$")

_HTML_ANCHOR_RE = re.compile(r"<a\s[^>]*?(?:id|name)\s*=\s*[\"']([^\"']+)[\"']")

# `[text](target)` reduced to its text, for a heading that links somewhere.
_LINK_TEXT_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

_EMPHASIS_RE = re.compile(r"\*+")


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
            # A bare `#heading` is kept: it is a link into this same document, and the anchor half
            # of the check is exactly what it needs. It used to be dropped here, back when the
            # fragment was never looked at.
            if not target.startswith(_EXTERNAL):
                found.append((number, target))
    return found


def _heading_text(raw: str) -> str:
    """A heading's plain text, as a slugger would see it.

    [PITFALL: `_` is left alone on purpose. Treating it as emphasis turns
    `## Whole-file configs — config_files` into `configfiles`, an anchor no renderer emits — these
    docs use underscores as identifiers, not as markup. That was one of the two false positives the
    first run of this check produced, both of them the checker's bug rather than the repo's.]"""
    text = _LINK_TEXT_RE.sub(r"\1", raw)
    text = text.replace("`", "")
    return _EMPHASIS_RE.sub("", text).strip()


def _toc_slug(text: str) -> str:
    """python-markdown's `markdown.extensions.toc` slugify — what the published site serves."""
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def _gh_slug(text: str) -> str:
    """github.com's slugger — what a reader of `plans/`, `contributing/` or a README follows.

    [PITFALL: GitHub does **not** collapse runs of spaces. `## Bash & the CLI allowlist (intro)`
    loses the ampersand and keeps both surrounding spaces, so the anchor carries a double hyphen:
    `bash--the-cli-allowlist-intro`. A `\\s+ -> -` shared with the toc slugger reports that correct
    link as broken, which was the second of the two first-run false positives.]"""
    value = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return value.replace(" ", "-")


def _anchors(text: str) -> frozenset[str]:
    """Every fragment a link into this document could legitimately name.

    Deliberately a union across both renderers rather than one answer. The same markdown is read
    two ways in this family — a docs site renders it through python-markdown's toc extension, and
    `plans/`, `contributing/`, `AGENTS.md` and every README are read on github.com — and the two
    sluggers agree on the common case while differing on punctuation and space runs. Requiring
    either alone would report correct links in the other renderer as broken.

    Fenced blocks are skipped for the same reason `_relative_links` skips them: a `##` inside a code
    sample is not a heading. Duplicate headings are suffixed the way each renderer does it, which is
    also not the same — python-markdown appends `_1`, github.com appends `-1`."""
    found: set[str] = set()
    # One counter per slugger, never one shared. Both sluggers usually agree on a heading, so a
    # shared dict counts every heading twice and numbers the second `## Notes` as `notes_2`/
    # `notes-3` — anchors no renderer emits, on the very shape duplicate suffixing exists for.
    counts: tuple[dict[str, int], dict[str, int]] = ({}, {})
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.update(_HTML_ANCHOR_RE.findall(line))
        heading = _HEADING_RE.match(line)
        if heading is None:
            continue
        raw = heading.group(1)
        if (explicit := _ATTR_LIST_ID_RE.search(raw)) is not None:
            found.add(explicit.group(1))
            raw = _ATTR_LIST_ID_RE.sub("", raw)
        plain = _heading_text(raw)
        for slug, separator, seen_here in ((_toc_slug(plain), "_", counts[0]), (_gh_slug(plain), "-", counts[1])):
            if not slug:
                continue
            seen = seen_here.get(slug, 0)
            seen_here[slug] = seen + 1
            found.add(slug if seen == 0 else f"{slug}{separator}{seen}")
    return frozenset(found)


def _bad_link(source: Path, target: str, anchors_of: Callable[[Path], frozenset[str]] | None = None) -> str | None:
    """Why a link is wrong, or None when it is fine.

    Two halves. The path half asks whether the file exists and stays inside the repository. The
    fragment half — only when `anchors_of` is supplied — asks whether the heading it names still
    exists, which is the half a rename actually breaks. `file.md#heading` used to verify the file
    and never the heading, and a renamed heading passed the gate twice while breaking a published
    site both times.

    Both a cross-file `file.md#heading` and a whole-document `#heading` are checked; 59 of the 79
    fragment links measured across this family were same-file, so dropping those would miss most of
    the surface."""
    path_part, _, fragment = target.partition("#")
    if not path_part and not fragment:
        return None
    if path_part:
        # A leading slash means repo root, the way a docs site would serve it; everything else
        # resolves against the directory of the file doing the linking.
        root = Path.cwd().resolve()
        resolved = root / path_part.lstrip("/") if path_part.startswith("/") else (source.parent / path_part).resolve()
        if not resolved.is_relative_to(root):
            # A `../../other-repo/file.md` resolves on a machine that happens to have both repos
            # checked out as siblings and nowhere else — it is dead on GitHub and unresolvable in
            # CI, so it is wrong even while it "works" locally. Reported as its own kind of wrong
            # rather than as missing, because the fix is different: link the URL, not the path.
            return f"{path_part} (escapes the repository — link the URL instead)"
        if not resolved.exists():
            return path_part
    else:
        resolved = source.resolve()
    if not fragment or anchors_of is None or resolved.suffix != ".md":
        return None
    anchors = anchors_of(resolved)
    if fragment in anchors:
        return None
    # The nearest surviving anchor, because a renamed heading is usually a near miss and the whole
    # failure mode is that nobody re-greps inbound references. Naming it turns the report into the
    # fix. Without a close match the message still names the file, so a slugger bug stays
    # diagnosable from the failure rather than from reading the source.
    near = get_close_matches(fragment, sorted(anchors), n=1)
    hint = f" — closest is #{near[0]}" if near else ""
    return f"{target} (no such anchor in {resolved.name}{hint})"


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
    first commit.

    Anchors are checked too, against the union of what python-markdown and github.com would emit —
    the same procedure's "grep for section-shaped citations" step, and the class a rename breaks.
    A renamed heading passed this gate twice while breaking a published site both times."""
    broken: list[str] = []
    # Per run, not per link: a heavily cross-referenced document is read once however many links
    # point into it, and the tree cannot change underneath a single gate step.
    anchor_cache: dict[Path, frozenset[str]] = {}

    def anchors_of(path: Path) -> frozenset[str]:
        if path not in anchor_cache:
            anchor_cache[path] = _anchors(path.read_text())
        return anchor_cache[path]

    for name in tracked_files(c, "*.md"):
        source = Path(name)
        text = source.read_text()
        broken.extend(
            f"{name}:{number}: {problem}"
            for number, target in _relative_links(text)
            if (problem := _bad_link(source, target, anchors_of)) is not None
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
    run_step(c, "zensical build --strict")


@task
def serve(c: Context):
    """Serve the docs site locally with live reload (zensical serve)."""
    c.run("zensical serve", echo=True)
