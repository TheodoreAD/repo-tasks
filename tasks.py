"""Dogfoods this repo's own quality tasks against itself — the exact same wiring
every consumer repo uses (see README.md)."""

from invoke import Collection

from repo_tasks import quality

ns = Collection.from_module(quality)
