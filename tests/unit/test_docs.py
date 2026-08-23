"""Tests for repo_tasks.docs: asserts the exact command string each task builds via invoke's
MockContext, plus `clean`'s real filesystem behavior against tmp_path."""

from invoke import MockContext

from repo_tasks import docs


def test_clean_noop_when_site_dir_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(docs, "_SITE_DIR", tmp_path / "site")
    c = MockContext()
    docs.clean.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "nothing to clean" in capsys.readouterr().out


def test_clean_removes_site_dir(tmp_path, monkeypatch):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("hi")
    monkeypatch.setattr(docs, "_SITE_DIR", site_dir)
    c = MockContext()
    docs.clean.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert not site_dir.exists()


def test_build_runs_zensical_strict():
    c = MockContext(run=True)
    docs.build.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("zensical build --strict", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_serve_runs_zensical_serve():
    c = MockContext(run=True)
    docs.serve.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("zensical serve", echo=True)  # pyright: ignore[reportAttributeAccessIssue]
