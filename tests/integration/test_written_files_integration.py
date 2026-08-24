"""Files this package writes into a consumer must come out clean under this package's own
formatters — otherwise `inv configure` writes a file, the next `inv quality.fix` rewrites it, and
the next `configure` reverts it, a permanent oscillation in every consumer's `git status`.

Integration tier rather than unit because the proof is the real formatter's verdict: shfmt over
the rendered bootstrap script, dprint over the pyproject.toml `ensure_deps` edits. Both run under
the *shipped* configs (`.editorconfig` for shfmt's `space_redirects`, `dprint.json` for the TOML
plugin), copied into the scratch tree, since that is the environment the consumer runs them in.
No Docker, no network beyond dprint's already-cached plugins.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from invoke import MockContext, Result

from repo_tasks import configs, selfinstall

_PYPROJECT_HEAD = '[project]\nname = "x"\nversion = "0.1.0"\n\n[dependency-groups]\n'
_CONFIGS_DIR = Path(configs._source_dir(None))  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
def scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copy(_CONFIGS_DIR / ".editorconfig", tmp_path / ".editorconfig")
    shutil.copy(_CONFIGS_DIR / "dprint.json", tmp_path / "dprint.json")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_stamp_script_is_shfmt_clean(scratch: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    ls_remote = f"git ls-remote --tags --refs --sort=-v:refname {selfinstall._REPO_URL} 'v*'"  # pyright: ignore[reportPrivateUsage]
    selfinstall.stamp.body(MockContext(run={ls_remote: Result(stdout="refs/tags/v1.2.3\n", exited=0)}))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    result = subprocess.run(["shfmt", "-d", "bootstrap-repo-tasks.sh"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("empty_array", ["dev = []", "dev = [\n]"])
def test_ensure_deps_output_is_dprint_clean(scratch: Path, empty_array: str):
    (scratch / "pyproject.toml").write_text(f"{_PYPROJECT_HEAD}{empty_array}\n")
    configs.ensure_deps.body(MockContext(run=Result(exited=1)))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    result = subprocess.run(["dprint", "check", "pyproject.toml"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
