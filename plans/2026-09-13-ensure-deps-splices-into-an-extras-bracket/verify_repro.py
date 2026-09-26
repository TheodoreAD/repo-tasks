"""Replay the 2026-09-13 `ingesta` corruption against the fixed code, on that consumer's own file.

Reads `ingesta`'s real pyproject.toml, rewinds its dev group to the pre-repair state the plan records
(the two manifest entries absent, `"ingesta[store]"` still first), runs `ensure_deps` on a copy in a
scratch directory, and asserts the outcome. Nothing in that repo is written, and the source file is
re-read at the end to prove it.

Run it with this repo's own interpreter (`python3 plans/<this plan>/verify_repro.py` with the venv
active), which resolves `repo_tasks` through the editable install — so what it exercises is the
working tree, deliberately: the point is to check a candidate fix before it ships, not the installed
tool. That is also the limit this plan's `[UNVERIFIED:]` names.
"""

import contextlib
import shutil
import tempfile
import tomllib
from pathlib import Path

from invoke import MockContext, Result

from repo_tasks import configs

REWOUND = ('  "pytest-socket",\n', '  "pytest-timeout",\n')
SOURCE = Path.home() / "projects/github.com-personal/ingesta/pyproject.toml"

original = SOURCE.read_text(encoding="utf-8")
rewound = original
for line in REWOUND:
    assert line in rewound, f"expected {line!r} in the consumer's dev group"
    rewound = rewound.replace(line, "", 1)

work = Path(tempfile.mkdtemp())
(work / "pyproject.toml").write_text(rewound, encoding="utf-8")
with contextlib.chdir(work):
    configs.ensure_deps.body(MockContext(run=Result(exited=1)))
result = (work / "pyproject.toml").read_text(encoding="utf-8")
shutil.rmtree(work)

print("=" * 70)
dev = tomllib.loads(result)["dependency-groups"]["dev"]  # the 2026-09-13 run left this unparseable
print(f"parses as TOML: yes, dev group has {len(dev)} entries")
print(f"entry 0 is still the extras entry: {dev[0]!r}")

before = set(tomllib.loads(rewound)["dependency-groups"]["dev"])
added = sorted(entry for entry in dev if entry not in before)
print(f"added: {added}")

assert dev[0] == "ingesta[store]", "the extras entry was disturbed"
assert added == ["pytest-socket", "pytest-timeout"], f"expected only the two missing: {added}"
assert result.count('"ingesta[store]"') == 1
assert result.count('"ingesta[bot]"') == 1

restored = result
for line in REWOUND:
    restored = restored.replace(line, "", 1)
assert restored == rewound, "something other than the two insertions changed"
print("the only change is the two insertions; every other byte is identical")

assert original == SOURCE.read_text(encoding="utf-8"), "the consumer's file must not have changed"
print("ingesta's own pyproject.toml: untouched")
print("=" * 70)
print("PASS")
