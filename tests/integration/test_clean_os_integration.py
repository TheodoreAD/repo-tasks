"""Smoke test for the clean_os_container fixture itself (plans/2026-08-23-clean-os-integration-
testing.md) -- proves the image builds, runs non-root, starts with a clean $HOME, and has the repo
source copied in, before any real selfinstall.py/agents.py/direnv.py test is written against it.

All three tests share one module-scoped container; fine here since none of them mutates $HOME.
Revisit fixture scope once a real mutating test lands (see conftest.py's clean_os_container
docstring)."""


def test_runs_as_non_root(clean_os_container):
    result = clean_os_container.exec(["id", "-u"])
    assert result.exit_code == 0
    assert result.output.decode().strip() != "0"


def test_home_starts_clean(clean_os_container):
    result = clean_os_container.exec(["test", "-d", "/home/tester/.claude"])
    assert result.exit_code != 0, "a fresh container must not already have ~/.claude"


def test_repo_source_copied_in(clean_os_container):
    result = clean_os_container.exec(["test", "-f", "/home/tester/repo-tasks/pyproject.toml"])
    assert result.exit_code == 0
