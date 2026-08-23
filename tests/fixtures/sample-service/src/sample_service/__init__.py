"""A minimal stdlib-only HTTP service. It exists to give repo-tasks' docker, helm, and
version-grouping tasks a real artifact to run against — see README's "monorepos: workspace
members, version groups, and the sample service" section, not this package, for why it is here.

Deliberately no `__version__` constant: `version.py` writes the version into `pyproject.toml` and
nowhere else (contributing/versioning.md's single-writer rule), so a hardcoded copy here would
silently drift one bump later. `__main__` reads the installed metadata instead."""
