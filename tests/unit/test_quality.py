"""Tests for repo_tasks.quality: asserts the exact command string each task
builds via invoke's MockContext, plus dedicated coverage for _sh_files — the
one piece of real logic, and what makes the mandatory `check`/`fix` composite
safe to run unconditionally on a repo with no shell scripts.

The command-string tests run against the real `shutil.which`, so they also assert that this repo's
own environment has every gate binary — which is the preflight's whole premise. The preflight's own
behaviour is covered in test_configs.py, where it lives; the tests here pin the wiring."""

import shutil
from collections.abc import Callable

import pytest
from invoke import Context, Exit, MockContext, Result, Task

from repo_tasks import deps, docs, quality, testing

# Every gate step under test here takes only the Context, so one alias covers the parametrized
# cases below — `Task` is generic over its body's signature in invoke-stubs. A plain assignment,
# not a `type` statement: this package supports 3.11, where that syntax does not exist.
GateStep = Task[Callable[[Context], None]]

_WORKFLOW_LISTING = (
    "git ls-files --cached --others --exclude-standard -- '.github/workflows/*.yml' '.github/workflows/*.yaml'"
)

_DOCKERFILE_LISTING = "git ls-files --cached --others --exclude-standard -- 'Dockerfile' '*/Dockerfile' '*.Dockerfile'"


def test_lint_check(c):
    quality.lint_check.body(c)
    c.run.assert_called_once_with("ruff check .", echo=True)


def test_lint_apply(c):
    quality.lint_apply.body(c)
    c.run.assert_called_once_with("ruff check --fix .", echo=True)


def test_format_check(c):
    quality.format_check.body(c)
    assert c.run.call_args_list == [
        (("ruff format --check .",), {"echo": True}),
        (("dprint check --config-discovery=ignore-descendants",), {"echo": True}),
    ]


def test_format_apply(c):
    quality.format_apply.body(c)
    assert c.run.call_args_list == [
        (("ruff format .",), {"echo": True}),
        (("dprint fmt --config-discovery=ignore-descendants",), {"echo": True}),
    ]


def test_type_check(c):
    quality.type_check.body(c)
    c.run.assert_called_once_with("basedpyright", echo=True)


def test_type_check_forwards_an_explicit_python_version(c):
    # The matrix escape hatch: pyrightconfig.json's derived `pythonVersion` is what an editor and CI
    # normally agree on, and this overrides it for one run. Verified against basedpyright 1.39.10
    # that the flag beats the config file rather than only filling in for an absent value.
    quality.type_check.body(c, python_version="3.13")
    c.run.assert_called_once_with("basedpyright --pythonversion 3.13", echo=True)


def test_sh_files_empty():
    c = MockContext(run=Result(stdout="", exited=0))
    assert quality._sh_files(c) == []  # testing the one piece of real logic directly


def test_sh_files_nonempty():
    c = MockContext(run=Result(stdout="./a.sh ./b.sh\n", exited=0))
    assert quality._sh_files(c) == ["./a.sh", "./b.sh"]


def test_sh_files_command_failure_treated_as_empty():
    c = MockContext(run=Result(exited=1))
    assert quality._sh_files(c) == []


def test_shell_check_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_check.body(c)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True
    )


def test_shell_check_runs_shellcheck_when_files_found():
    c = MockContext(
        run={
            "git ls-files --cached --others --exclude-standard -- '*.sh'": Result(stdout="./a.sh\n", exited=0),
            "shellcheck ./a.sh": Result(exited=0),
        }
    )
    quality.shell_check.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shellcheck ./a.sh",),
        {"echo": True},
    )


def test_workflow_check_noop_when_no_workflow_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.workflow_check.body(c)
    c.run.assert_called_once_with(_WORKFLOW_LISTING, hide=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_workflow_check_runs_both_linters_when_files_found():
    c = MockContext(
        run={
            _WORKFLOW_LISTING: Result(stdout=".github/workflows/ci.yml\n", exited=0),
            "actionlint .github/workflows/ci.yml": Result(exited=0),
            "zizmor --offline .github/workflows/ci.yml": Result(exited=0),
        }
    )
    quality.workflow_check.body(c)
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("actionlint .github/workflows/ci.yml",), {"echo": True}),
        (("zizmor --offline .github/workflows/ci.yml",), {"echo": True}),
    ]


def test_workflow_check_pins_zizmor_offline():
    # Not decoration: zizmor turns its online audits on whenever a GH_TOKEN/GITHUB_TOKEN is in the
    # environment, which is the normal state inside CI. Without the flag the gate's rule set would
    # differ between a laptop and a runner, and `check` is supposed to be deterministic and offline.
    c = MockContext(
        run={
            _WORKFLOW_LISTING: Result(stdout=".github/workflows/ci.yml\n", exited=0),
            "actionlint .github/workflows/ci.yml": Result(exited=0),
            "zizmor --offline .github/workflows/ci.yml": Result(exited=0),
        }
    )
    quality.workflow_check.body(c)
    zizmor_calls = [call for call in c.run.call_args_list if call[0][0].startswith("zizmor")]  # pyright: ignore[reportAttributeAccessIssue]
    assert zizmor_calls
    assert all("--offline" in call[0][0] for call in zizmor_calls)


def test_check_gates_on_workflow_check():
    assert "workflow_check" in [t.name for t in quality.check.pre]


def test_dockerfile_check_noop_when_no_dockerfiles():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.dockerfile_check.body(c)
    c.run.assert_called_once_with(_DOCKERFILE_LISTING, hide=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_dockerfile_check_runs_hadolint_when_files_found():
    c = MockContext(
        run={
            _DOCKERFILE_LISTING: Result(stdout="Dockerfile\nsvc/clean-os.Dockerfile\n", exited=0),
            "hadolint Dockerfile svc/clean-os.Dockerfile": Result(exited=0),
        }
    )
    quality.dockerfile_check.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("hadolint Dockerfile svc/clean-os.Dockerfile",),
        {"echo": True},
    )


def test_dockerfiles_finds_both_spellings_at_any_depth():
    # The one piece of real logic here is the pathspec set, and git's `*` crosses directory
    # separators — which is what lets `*.Dockerfile` reach a fixture nested three levels down.
    c = MockContext(run=Result(stdout="Dockerfile\na/b/c.Dockerfile\na/Dockerfile\n", exited=0))
    assert quality._dockerfiles(c) == ["Dockerfile", "a/b/c.Dockerfile", "a/Dockerfile"]


def test_check_gates_on_dockerfile_check():
    # hadolint is the static half; `docker build --check` needs a daemon and stays out of the gate.
    assert quality.dockerfile_check in quality.check.pre


def test_verify_types_reports_each_package_under_src(c, tmp_cwd):
    package = tmp_cwd / "src" / "mypkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    quality.verify_types.body(c)
    # warn=True: --verifytypes exits non-zero at anything short of 100% completeness, and this is a
    # report rather than a gate, so its exit code is deliberately not propagated.
    c.run.assert_called_once_with("basedpyright --verifytypes mypkg", echo=True, warn=True)


def test_verify_types_noops_without_a_src_layout(c, tmp_cwd, capsys):
    quality.verify_types.body(c)
    assert "nothing to do" in capsys.readouterr().out
    c.run.assert_not_called()


def test_verify_types_is_not_a_gate_step():
    # A report, not a check: gating on a completeness score means permanent red or a committed
    # baseline, and contributing/type-checking.md rejected baselines for this repo.
    assert quality.verify_types not in quality.check.pre


def test_check_gates_on_link_check():
    # Retiring a plan deletes a file other documents link to; the procedure's "grep for inbound
    # references" step was honour-system until this ran in the gate.
    assert docs.link_check in quality.check.pre


def test_precommit_builds_the_docs():
    # zensical build --strict catches what a renderer objects to and nothing else here sees.
    assert docs.build in quality.precommit.pre


def test_check_does_not_build_the_docs():
    # check is the read-only half by construction — safe concurrently, on a read-only checkout, and
    # twice with the same answer. docs.build writes a site into the working tree, so it cannot be
    # here whatever .gitignore thinks of the output.
    assert docs.build not in quality.check.pre


def test_check_gates_on_untested_modules():
    # The question a coverage percentage cannot answer: which module has no tests at all.
    assert testing.untested_modules in quality.check.pre


def test_check_gates_on_lock_drift():
    # Without this, a pyproject.toml edit with no re-lock passes precommit and fails in CI, where
    # bootstrap.sh's `uv sync --locked` catches it. Deterministic and offline, unlike deps.audit.
    assert deps.check in quality.check.pre


def test_check_does_not_gate_on_audit():
    # The gate stays runnable offline: deps.audit queries OSV, so its result moves without the code.
    assert deps.audit not in quality.check.pre


def test_check_gates_on_shell_format_check():
    # The check-only half of shell formatting, so drift is caught by CI rather than only ever
    # surfaced by `fix` rewriting the file.
    assert "shell_format_check" in [t.name for t in quality.check.pre]


def test_shell_format_check_runs_shfmt_diff_when_files_found():
    c = MockContext(
        run={
            "git ls-files --cached --others --exclude-standard -- '*.sh'": Result(stdout="./a.sh\n", exited=0),
            "shfmt -d ./a.sh": Result(exited=0),
        }
    )
    quality.shell_format_check.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shfmt -d ./a.sh",),
        {"echo": True},
    )


def test_shell_format_check_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_format_check.body(c)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True
    )


def test_shell_format_apply_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_format_apply.body(c)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True
    )


def test_shell_format_apply_runs_shfmt_when_files_found():
    c = MockContext(
        run={
            "git ls-files --cached --others --exclude-standard -- '*.sh'": Result(stdout="./a.sh\n", exited=0),
            "shfmt -w ./a.sh": Result(exited=0),
        }
    )
    quality.shell_format_apply.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shfmt -w ./a.sh",),
        {"echo": True},
    )


@pytest.mark.parametrize(
    "step",
    [quality.lint_check, quality.lint_apply, quality.format_check, quality.format_apply, quality.type_check],
)
def test_unconditional_steps_preflight_their_binary(c, monkeypatch, step: GateStep):
    # Exit, not the shell's exit 127 from a command that was never runnable — with the missing
    # entry and the command that adds it in the message (see test_configs.py for the text).
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    with pytest.raises(Exit):
        step.body(c)
    c.run.assert_not_called()


_SH_LISTING = "git ls-files --cached --others --exclude-standard -- '*.sh'"


@pytest.mark.parametrize(
    ("step", "listing", "found"),
    [
        (quality.shell_check, _SH_LISTING, "./a.sh\n"),
        (quality.shell_format_check, _SH_LISTING, "./a.sh\n"),
        (quality.shell_format_apply, _SH_LISTING, "./a.sh\n"),
        (quality.workflow_check, _WORKFLOW_LISTING, ".github/workflows/ci.yml\n"),
        (quality.dockerfile_check, _DOCKERFILE_LISTING, "Dockerfile\n"),
    ],
)
def test_file_gated_steps_preflight_only_once_they_have_files(monkeypatch, step: GateStep, listing: str, found: str):
    monkeypatch.setattr(shutil, "which", lambda tool: None)

    # No files: still a clean no-op. The preflight must not cost these steps the
    # safe-to-run-in-any-consumer contract their docstrings promise.
    step.body(MockContext(run=Result(stdout="", exited=0)))

    with pytest.raises(Exit):
        step.body(MockContext(run={listing: Result(stdout=found, exited=0)}))
