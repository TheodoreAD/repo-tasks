"""Every task module this package ships is importable directly (`from repo_tasks import quality`)
for a consumer that wants to hand-pick a subset, but `ns` is the recommended default: a
ready-made root Collection with every module already nested under its own name, so a consumer's
`tasks.py` only ever needs `from repo_tasks import ns` — no per-repo `add_collection` boilerplate,
and no consumer-side change needed when a new module (docker, python_pkg, helm, ...) ships here."""

from invoke import Collection

from . import agents, dev_env, direnv, dist, docs, gitflow, quality, version
from . import deps as deps_module
from . import venv as venv_module

ns = Collection()
ns.add_collection(Collection.from_module(quality), name="quality")
ns.add_collection(Collection.from_module(version), name="version")
ns.add_collection(Collection.from_module(gitflow), name="gitflow")
ns.add_collection(Collection.from_module(dev_env), name="dev_env")
ns.add_collection(Collection.from_module(docs), name="docs")
ns.add_collection(Collection.from_module(venv_module), name="venv")
ns.add_collection(Collection.from_module(deps_module), name="deps")
ns.add_collection(Collection.from_module(direnv), name="direnv")
ns.add_collection(Collection.from_module(agents), name="agents")
ns.add_collection(Collection.from_module(dist), name="dist")
