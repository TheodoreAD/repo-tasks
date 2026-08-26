"""Tests for repo_tasks.docs: asserts the exact command string each task builds via invoke's
MockContext, plus `clean`'s real filesystem behavior against tmp_path.

`link_check` is the one task here with real logic rather than a command string, so it gets direct
coverage of the parser (what counts as a link, what is skipped) and of the resolution rules."""

import pytest
from invoke import Exit, MockContext, Result

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


def test_relative_links_finds_inline_targets():
    text = "see [the guide](contributing/guide.md) and [a plan](../plans/x.md)\n"
    assert docs._relative_links(text) == [(1, "contributing/guide.md"), (1, "../plans/x.md")]


def test_relative_links_skips_external_and_pure_anchors():
    text = "[site](https://example.com) [mail](mailto:a@b.c) [here](#a-heading)\n"
    assert docs._relative_links(text) == []


def test_relative_links_skips_fenced_blocks():
    # A code sample showing markdown syntax is documentation, not a link this repo has to keep
    # working — CONTRIBUTING.md and the plan-docs convention are both full of them.
    text = "real [one](a.md)\n```markdown\n[example](does/not/exist.md)\n```\nafter [two](b.md)\n"
    assert docs._relative_links(text) == [(1, "a.md"), (5, "b.md")]


def test_relative_links_ignores_a_link_title():
    assert docs._relative_links('[x](a.md "the title")\n') == [(1, "a.md")]


def test_broken_link_none_when_target_exists(tmp_path):
    (tmp_path / "target.md").write_text("hi")
    source = tmp_path / "source.md"
    assert docs._broken_link(source, "target.md") is None


def test_broken_link_reports_a_missing_target(tmp_path):
    source = tmp_path / "source.md"
    assert docs._broken_link(source, "gone.md") == "gone.md"


def test_broken_link_checks_the_file_not_the_fragment(tmp_path):
    # file.md#heading verifies the file only: a renamed heading still passes, deliberately.
    (tmp_path / "target.md").write_text("hi")
    source = tmp_path / "source.md"
    assert docs._broken_link(source, "target.md#any-heading-at-all") is None
    assert docs._broken_link(source, "gone.md#heading") == "gone.md"


def test_link_check_passes_when_every_link_resolves(tmp_cwd, capsys):
    (tmp_cwd / "target.md").write_text("hi")
    (tmp_cwd / "index.md").write_text("[ok](target.md)\n")
    c = MockContext(run=Result(stdout="index.md\n", exited=0))
    docs.link_check.body(c)
    assert capsys.readouterr().out == ""


def test_link_check_stops_on_a_broken_link(tmp_cwd, capsys):
    (tmp_cwd / "index.md").write_text("intro\n\n[gone](nope.md)\n")
    c = MockContext(run=Result(stdout="index.md\n", exited=0))
    with pytest.raises(Exit) as exc_info:
        docs.link_check.body(c)
    assert exc_info.value.code == 1
    assert "index.md:3: nope.md" in capsys.readouterr().out


def test_link_check_noops_without_markdown(tmp_cwd):
    # Same safe-to-run-unconditionally contract as shell_check and workflow_check.
    c = MockContext(run=Result(stdout="", exited=0))
    docs.link_check.body(c)
