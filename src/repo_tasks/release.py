"""Publishing an existing tag as a GitHub Release.

Deliberately model-agnostic: a release is a repo-level event, not a property of whichever branching
model produced the tag. `gitflow.release-finalize` tags `main` after a PR merges and `trunkflow.cut`
tags `main` directly — either can be published from here, and a third model added later needs
nothing new. That is why this is its own module rather than a task inside one of the flows, and why
it is not in `dist`, whose scope is Python distributions (a Release may reference a wheel, an image,
a chart, or no artifact at all).

Publishing is always a separate, deliberate act. `version.bump` and `trunkflow.cut` produce a tag
and stop, because not every version merits a Release and one that does may not want it yet — so a
tag can sit unpublished indefinitely and be released later by naming it.
"""

from invoke import Context, task

from .requirements import GH, NETWORK, requires


def _latest_tag(c: Context) -> str:
    """The most recent tag reachable from HEAD, which is the one a release almost always means."""
    result = c.run("git describe --tags --abbrev=0", hide=True, warn=True)
    tag = result.stdout.strip()
    if not result.ok or not tag:
        raise ValueError(
            "no tags in this repository, so there is nothing to release — "
            "`inv trunkflow.cut` or the gitflow release flow creates one"
        )
    return tag


def _require_tag_on_remote(c: Context, tag: str):
    """A Release must name a tag the remote already has.

    `gh release create` will happily *create* the tag when it is missing, resolving it against
    whatever `--target` says (defaulting to the default branch's tip). That turns a typo into a new
    tag on a commit nobody chose, and a Release pointing at it — so the tag is required to exist
    upstream first, where this can only ever refer to something already published.
    """
    if not c.run(f"git rev-parse --verify --quiet refs/tags/{tag}", hide=True, warn=True).ok:
        raise ValueError(f"tag {tag} does not exist locally — check the name, or create it first")
    if not c.run(f"git ls-remote --exit-code --tags origin refs/tags/{tag}", hide=True, warn=True).ok:
        raise ValueError(f"tag {tag} exists locally but not on origin — `git push origin {tag}` first")


def _require_no_release(c: Context, tag: str):
    """Refuse to publish over an existing Release rather than editing one nobody asked to change."""
    if c.run(f"gh release view {tag}", hide=True, warn=True).ok:
        raise ValueError(
            f"a GitHub Release for {tag} already exists — `gh release edit {tag}` to change it, "
            f"or release a different tag"
        )


@requires(GH, NETWORK)
@task(
    help={
        "tag": "Tag to publish (default: the most recent tag reachable from HEAD)",
        "notes": "Release notes body. Omitted, GitHub generates them from the commits since the last release",
        "draft": "Create the Release as a draft instead of publishing it",
    }
)
def create(c: Context, tag: str | None = None, notes: str | None = None, draft: bool = False):
    """Publish an existing tag as a GitHub Release.

    Needs `gh` and the network. This is what makes `ci.check-actions` able to report a stale pin in
    a consumer: that check resolves currency through the releases API, so a repo with tags and no
    Releases is one whose pinned consumers go stale silently.
    """
    tag = tag or _latest_tag(c)
    _require_tag_on_remote(c, tag)
    _require_no_release(c, tag)

    # `--generate-notes` rather than a hand-written default: it lists the merged PRs and commits
    # since the previous Release, which is the summary a reader wants and nobody wants to retype.
    body = f'--notes "{notes}"' if notes is not None else "--generate-notes"
    flags = f"{body}{' --draft' if draft else ''}"
    c.run(f"gh release create {tag} --title {tag} {flags}", echo=True)
