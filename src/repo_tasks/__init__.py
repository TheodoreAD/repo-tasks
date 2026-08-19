"""Every task module this package ships is importable directly (`from repo_tasks import quality`)
for a consumer that wants to hand-pick a subset, but `ns` is the recommended default: a
ready-made root Collection with every module already nested under its own name, so a consumer's
`tasks.py` only ever needs `from repo_tasks import ns` — no per-repo `add_collection` boilerplate,
and no consumer-side change needed when a new module (docker, python_pkg, helm, ...) ships here."""

from invoke import Collection

from . import quality, version

ns = Collection()
ns.add_collection(Collection.from_module(quality), name="quality")
ns.add_collection(Collection.from_module(version), name="version")
