"""A minimal stdlib-only HTTP service. It exists to give repo-tasks' docker, helm, and
version-grouping tasks a real artifact to run against — see the repo's README and
plans/2026-08-19-dogfood-sample-service.md, not this package, for why it is here.

Deliberately no `__version__` constant: `version.py` writes the version into `pyproject.toml` and
nowhere else (contributing/versioning.md's single-writer rule), so a hardcoded copy here would
silently drift one bump later. `__main__` reads the installed metadata instead."""
