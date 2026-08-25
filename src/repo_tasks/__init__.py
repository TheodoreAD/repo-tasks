"""Every task module this package ships is importable directly (`from repo_tasks import quality`)
for a consumer that wants to hand-pick a subset, but `ns` is the recommended default: a
ready-made root Collection with every module already nested under its own name, so a consumer's
`tasks.py` only ever needs `from repo_tasks import ns` — no per-repo `add_collection` boilerplate,
and no consumer-side change needed when a new module (helm, ...) ships here."""

from invoke.collection import Collection

from . import (
    agents,
    configs,
    configure,
    dev_env,
    direnv,
    dist,
    docker,
    docs,
    gitflow,
    helm,
    quality,
    selfinstall,
    testing,
    version,
)
from . import deps as deps_module
from . import venv as venv_module

# Unnested, unlike every other module below — the one command anything outside this package
# should ever need to depend on by name (see configure.py). Mirrors power-user-linux-setup's own
# `namespace = Collection(setup.setup, ...)` pattern for its single top-level entrypoint. Passed
# to the constructor, not `ns.add_task()` — invoke's `@task` decorator has no type stub, so
# pyright falls back to the plain undecorated function signature for anything decorated with it;
# the constructor's `*args: Any` tolerates that, `add_task`'s `task: Task` parameter doesn't.
ns = Collection(configure.configure)
ns.add_collection(Collection.from_module(quality), name="quality")
ns.add_collection(Collection.from_module(testing), name="test")
ns.add_collection(Collection.from_module(version), name="version")
ns.add_collection(Collection.from_module(gitflow), name="gitflow")
ns.add_collection(Collection.from_module(dev_env), name="dev_env")
ns.add_collection(Collection.from_module(docs), name="docs")
ns.add_collection(Collection.from_module(venv_module), name="venv")
ns.add_collection(Collection.from_module(deps_module), name="deps")
ns.add_collection(Collection.from_module(direnv), name="direnv")
ns.add_collection(Collection.from_module(agents), name="agents")
ns.add_collection(Collection.from_module(dist), name="dist")
ns.add_collection(Collection.from_module(docker), name="docker")
ns.add_collection(Collection.from_module(helm), name="helm")
ns.add_collection(Collection.from_module(configs), name="configs")
ns.add_collection(Collection.from_module(selfinstall), name="repo_tasks")
