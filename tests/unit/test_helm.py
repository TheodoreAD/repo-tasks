"""Tests for repo_tasks.helm: command-string construction for lint/package/push, with
discover_helm_charts/current_version mocked out via monkeypatch — projects.py/version.py own
their own tests for the real discovery/version-resolution logic."""

from pathlib import Path

import pytest

from repo_tasks import helm
from repo_tasks.projects import HelmChart


def _stub_chart(**overrides):
    defaults = {
        "name": "sample-service-chart",
        "path": Path("examples/sample-service/chart"),
        "registry": "oci://ghcr.io/org/charts",
        "group": "sample-service",
    }
    defaults.update(overrides)
    return HelmChart(**defaults)  # pyright: ignore[reportArgumentType]


def _stub(monkeypatch, chart=None, version="1.2.3"):
    monkeypatch.setattr(helm, "discover_helm_charts", lambda c: [chart or _stub_chart()])
    monkeypatch.setattr(helm, "current_version", lambda c, group=None: version)


def test_lint_runs_helm_lint_on_the_chart_path(c, monkeypatch):
    _stub(monkeypatch)
    helm.lint.body(c)
    c.run.assert_called_once_with("helm lint examples/sample-service/chart", echo=True)


def test_package_packages_into_dist_helm(c, monkeypatch):
    _stub(monkeypatch)
    helm.package.body(c)
    c.run.assert_called_once_with("helm package examples/sample-service/chart --destination dist/helm", echo=True)


def test_push_pushes_the_group_versioned_tgz_to_the_entry_registry(c, monkeypatch):
    _stub(monkeypatch)
    helm.push.body(c)
    c.run.assert_called_once_with(
        "helm push dist/helm/sample-service-chart-1.2.3.tgz oci://ghcr.io/org/charts", echo=True
    )


def test_push_names_the_tgz_after_the_semver_spelling(c, monkeypatch):
    # Chart.yaml holds `1.2.3-rc.1`, so that is what `helm package` named the archive.
    _stub(monkeypatch, version="1.2.3rc1")
    helm.push.body(c)
    c.run.assert_called_once_with(
        "helm push dist/helm/sample-service-chart-1.2.3-rc.1.tgz oci://ghcr.io/org/charts", echo=True
    )


def test_package_dev_rewrites_the_version_before_packaging(c, monkeypatch):
    _stub(monkeypatch)
    seen = []
    monkeypatch.setattr(helm, "set_dev", lambda c, group=None: seen.append(group))
    helm.package.body(c, dev=True)
    assert seen == ["sample-service"]
    c.run.assert_called_once_with("helm package examples/sample-service/chart --destination dist/helm", echo=True)


def test_push_registry_flag_overrides_the_entry_registry(c, monkeypatch):
    _stub(monkeypatch)
    helm.push.body(c, registry="oci://localhost:5000/charts")
    c.run.assert_called_once_with(
        "helm push dist/helm/sample-service-chart-1.2.3.tgz oci://localhost:5000/charts", echo=True
    )


def test_push_plain_http_appends_the_flag(c, monkeypatch):
    _stub(monkeypatch)
    helm.push.body(c, plain_http=True)
    c.run.assert_called_once_with(
        "helm push dist/helm/sample-service-chart-1.2.3.tgz oci://ghcr.io/org/charts --plain-http", echo=True
    )


def test_push_raises_when_no_registry_configured_or_passed(c, monkeypatch):
    _stub(monkeypatch, chart=_stub_chart(registry=None))
    with pytest.raises(ValueError, match="no registry"):
        helm.push.body(c)


def test_resolve_chart_raises_when_project_not_found(c, monkeypatch):
    _stub(monkeypatch)
    with pytest.raises(ValueError, match="nonexistent"):
        helm.lint.body(c, project="nonexistent")


@pytest.mark.parametrize("task_name", ["lint", "package", "push", "login"])
def test_tasks_no_op_cleanly_with_zero_charts(c, monkeypatch, capsys, task_name):
    monkeypatch.setattr(helm, "discover_helm_charts", lambda c: [])
    getattr(helm, task_name).body(c)  # pyright: ignore[reportAny]
    c.run.assert_not_called()
    assert "nothing to do" in capsys.readouterr().out


def _capture_interactive(monkeypatch) -> list[str]:
    """Record what `login` hands to the interactive runner instead of attaching a terminal."""
    commands: list[str] = []
    monkeypatch.setattr(helm, "run_interactive", commands.append)
    return commands


def test_login_targets_the_registry_host_not_the_push_reference(c, monkeypatch):
    # helm push takes the full oci:// reference; helm registry login takes the bare host.
    _stub(monkeypatch)
    commands = _capture_interactive(monkeypatch)
    helm.login.body(c)
    assert commands == ["helm registry login ghcr.io"]


def test_login_registry_flag_overrides_the_entry_registry(c, monkeypatch):
    _stub(monkeypatch)
    commands = _capture_interactive(monkeypatch)
    helm.login.body(c, registry="oci://localhost:5000/charts")
    assert commands == ["helm registry login localhost:5000"]


def test_login_never_goes_through_c_run(c, monkeypatch):
    # Same reason as docker.login: a prompt needs the real terminal, and c.run cannot give it one
    # on Python 3.14 (interactive.py).
    _stub(monkeypatch)
    _capture_interactive(monkeypatch)
    helm.login.body(c)
    c.run.assert_not_called()


def test_login_never_puts_a_credential_in_the_command(c, monkeypatch):
    _stub(monkeypatch)
    commands = _capture_interactive(monkeypatch)
    helm.login.body(c)
    assert commands == ["helm registry login ghcr.io"]


def test_login_errors_when_the_chart_has_no_registry(c, monkeypatch):
    _stub(monkeypatch, chart=_stub_chart(registry=None))
    with pytest.raises(ValueError, match="no registry"):
        helm.login.body(c)


@pytest.mark.parametrize(
    ("registry", "expected"),
    [
        ("oci://ghcr.io/org/charts", "ghcr.io"),
        ("oci://localhost:5000/charts", "localhost:5000"),
        ("oci://registry.example.com", "registry.example.com"),
    ],
)
def test_registry_host_strips_the_oci_scheme_and_the_path(registry, expected):
    assert helm._registry_host(registry) == expected
