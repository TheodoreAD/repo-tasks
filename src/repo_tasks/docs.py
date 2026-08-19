"""Docs-site build tasks, wrapping zensical (mkdocs.yml-compatible, see zensical.org). Assumes
the consumer's `docs` uv dependency group is installed (`uv sync --group docs`) — `zensical`
itself isn't a dependency of this package."""

import shutil
from pathlib import Path

from invoke import task

_SITE_DIR = Path("site")


@task
def clean(c):
    """Remove the built docs site (site/)."""
    if not _SITE_DIR.exists():
        print("[docs.clean] site/ not present — nothing to clean")
        return
    shutil.rmtree(_SITE_DIR)
    print("[docs.clean] site/ removed")


@task(pre=[clean])
def build(c):
    """Build the docs site with zensical in strict mode (fails on any warning)."""
    c.run("zensical build --strict", echo=True)


@task
def serve(c):
    """Serve the docs site locally with live reload (zensical serve)."""
    c.run("zensical serve", echo=True)
