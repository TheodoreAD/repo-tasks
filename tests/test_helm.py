"""Tests for repo_tasks.helm: command-string construction for lint/package/push, with
discover_helm_charts/current_version mocked out via monkeypatch — projects.py/version.py own
their own tests for the real discovery/version-resolution logic."""

from pathlib import Path

import pytest
from invoke import MockContext

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


def test_lint_runs_helm_lint_on_the_chart_path(monkeypatch):
    _stub(monkeypatch)
    c = MockContext(run=True)
    helm.lint.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "helm lint examples/sample-service/chart", echo=True
    )


def test_package_packages_into_dist_helm(monkeypatch):
    _stub(monkeypatch)
    c = MockContext(run=True)
    helm.package.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "helm package examples/sample-service/chart --destination dist/helm", echo=True
    )


def test_push_pushes_the_group_versioned_tgz_to_the_entry_registry(monkeypatch):
    _stub(monkeypatch)
    c = MockContext(run=True)
    helm.push.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "helm push dist/helm/sample-service-chart-1.2.3.tgz oci://ghcr.io/org/charts", echo=True
    )


def test_push_registry_flag_overrides_the_entry_registry(monkeypatch):
    _stub(monkeypatch)
    c = MockContext(run=True)
    helm.push.body(c, registry="oci://localhost:5000/charts")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "helm push dist/helm/sample-service-chart-1.2.3.tgz oci://localhost:5000/charts", echo=True
    )


def test_push_raises_when_no_registry_configured_or_passed(monkeypatch):
    _stub(monkeypatch, chart=_stub_chart(registry=None))
    c = MockContext(run=True)
    with pytest.raises(ValueError, match="no registry"):
        helm.push.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]


def test_resolve_chart_raises_when_project_not_found(monkeypatch):
    _stub(monkeypatch)
    c = MockContext(run=True)
    with pytest.raises(ValueError, match="nonexistent"):
        helm.lint.body(c, project="nonexistent")  # pyright: ignore[reportAny, reportFunctionMemberAccess]


@pytest.mark.parametrize("task_name", ["lint", "package", "push"])
def test_tasks_no_op_cleanly_with_zero_charts(monkeypatch, capsys, task_name):
    monkeypatch.setattr(helm, "discover_helm_charts", lambda c: [])
    c = MockContext(run=True)
    getattr(helm, task_name).body(c)  # pyright: ignore[reportAny]
    c.run.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue]
    assert "nothing to do" in capsys.readouterr().out
