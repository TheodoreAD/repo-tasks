"""Tests for repo_tasks.docs: asserts the exact command string each task builds via invoke's
MockContext, plus `clean`'s real filesystem behavior against tmp_path."""

from repo_tasks import docs


def test_clean_noop_when_site_dir_missing(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(docs, "_SITE_DIR", tmp_cwd / "site")
    docs.clean.body(c)
    assert "nothing to clean" in capsys.readouterr().out


def test_clean_removes_site_dir(c, tmp_path, monkeypatch):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("hi")
    monkeypatch.setattr(docs, "_SITE_DIR", site_dir)
    docs.clean.body(c)
    assert not site_dir.exists()


def test_build_runs_zensical_strict(c):
    docs.build.body(c)
    c.run.assert_called_once_with("zensical build --strict", echo=True)


def test_serve_runs_zensical_serve(c):
    docs.serve.body(c)
    c.run.assert_called_once_with("zensical serve", echo=True)
