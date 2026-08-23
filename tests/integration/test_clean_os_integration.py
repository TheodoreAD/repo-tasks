"""Smoke test for the clean_os_container fixture itself -- proves the image builds, runs non-root,
starts with a clean $HOME, and has the repo source copied in. The real mutating tests live in
test_clean_os_user_effects.py, in their own module deliberately: module scope gives each module its
own fresh container, so this module's clean-$HOME assertions can never observe that one's
mutations.

All three tests here share one module-scoped container; fine since none of them mutates $HOME."""


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
