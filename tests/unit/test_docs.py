"""Tests for repo_tasks.docs: asserts the exact command string each task builds via invoke's
MockContext, plus `clean`'s real filesystem behavior against tmp_path.

`link_check` is the one task here with real logic rather than a command string, so it gets direct
coverage of the parser (what counts as a link, what is skipped) and of the resolution rules."""

import shutil

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import docs


def _anchors_of(path):
    """The resolver `link_check` builds, without its per-run cache — tests want no shared state."""
    return docs._anchors(path.read_text())


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


def test_build_runs_zensical_strict(c, tmp_cwd, monkeypatch):
    (tmp_cwd / "mkdocs.yml").write_text("site_name: x\n")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/zensical")
    docs.build.body(c)
    # A gate step (precommit), so the folded shape from steps.py; `serve` below keeps streaming.
    c.run.assert_called_once_with("zensical build --strict", hide=True, warn=True)


def test_build_noops_without_an_mkdocs_config(c, tmp_cwd, capsys):
    """The guard that lets this run in every consumer's gate. Most have no docs site at all, and
    none of them declares zensical on repo-tasks' behalf."""
    docs.build.body(c)
    c.run.assert_not_called()
    assert "no docs site" in capsys.readouterr().out


def test_build_stops_when_the_docs_group_is_not_installed(c, tmp_cwd, monkeypatch, capsys):
    """A repo that *has* an mkdocs.yml and no zensical is broken, not docs-less — the whole point
    of keying the no-op on the config file rather than on the tool."""
    (tmp_cwd / "mkdocs.yml").write_text("site_name: x\n")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(Exit):
        docs.build.body(c)
    c.run.assert_not_called()
    out = capsys.readouterr().out
    assert "uv sync --group docs" in out
    # Not configs.require_tool's remediation: zensical is in the consumer's own docs group, so
    # naming the dev group or the repo-tasks-quality manifest would send them to sync the wrong one.
    assert "repo-tasks-quality" not in out
    assert "dependency-groups.dev" not in out


def test_serve_runs_zensical_serve(c):
    docs.serve.body(c)
    c.run.assert_called_once_with("zensical serve", echo=True)


def test_relative_links_finds_inline_targets():
    text = "see [the guide](contributing/guide.md) and [a plan](../plans/x.md)\n"
    assert docs._relative_links(text) == [(1, "contributing/guide.md"), (1, "../plans/x.md")]


def test_relative_links_skips_external_but_keeps_a_same_file_anchor():
    # A bare `#heading` is kept now that the fragment is checked — it is a link into this same
    # document, and same-file was most of the fragment surface measured across the family.
    text = "[site](https://example.com) [mail](mailto:a@b.c) [here](#a-heading)\n"
    assert docs._relative_links(text) == [(1, "#a-heading")]


def test_relative_links_skips_fenced_blocks():
    # A code sample showing markdown syntax is documentation, not a link this repo has to keep
    # working — CONTRIBUTING.md and the plan-docs convention are both full of them.
    text = "real [one](a.md)\n```markdown\n[example](does/not/exist.md)\n```\nafter [two](b.md)\n"
    assert docs._relative_links(text) == [(1, "a.md"), (5, "b.md")]


def test_relative_links_skips_inline_code_spans():
    # `def f[T](x)` is a valid `[text](target)` pointing at `x`. PEP 695 generics make that shape
    # ordinary prose, so the gate used to go red on correct input.
    text = "real [one](a.md) and `def f[T](x)` in prose\n"
    assert docs._relative_links(text) == [(1, "a.md")]


def test_relative_links_skips_a_multi_backtick_span():
    # A span opened with two backticks holds single ones, and only `` closes it.
    assert docs._relative_links("``a `b` [T](gone.md)`` and [real](a.md)\n") == [(1, "a.md")]


def test_relative_links_keeps_a_link_whose_text_holds_code():
    assert docs._relative_links("[the `evolve` guide](a.md)\n") == [(1, "a.md")]


def test_relative_links_ignores_a_link_title():
    assert docs._relative_links('[x](a.md "the title")\n') == [(1, "a.md")]


def test_bad_link_none_when_target_exists(tmp_cwd):
    (tmp_cwd / "target.md").write_text("hi")
    source = tmp_cwd / "source.md"
    assert docs._bad_link(source, "target.md") is None


def test_bad_link_reports_a_missing_target(tmp_cwd):
    source = tmp_cwd / "source.md"
    assert docs._bad_link(source, "gone.md") == "gone.md"


def test_bad_link_checks_only_the_file_without_an_anchor_resolver(tmp_cwd):
    # The path half stands alone: given no resolver, the fragment is not looked at. link_check
    # always supplies one — this is the seam, not the shipped behaviour.
    (tmp_cwd / "target.md").write_text("hi")
    source = tmp_cwd / "source.md"
    assert docs._bad_link(source, "target.md#any-heading-at-all") is None
    assert docs._bad_link(source, "gone.md#heading") == "gone.md"


def test_bad_link_reports_a_missing_file_before_looking_at_its_anchors(tmp_cwd):
    # Order matters for the message: "gone.md" is the useful report, not "no such anchor in a file
    # that does not exist".
    source = tmp_cwd / "source.md"
    assert docs._bad_link(source, "gone.md#heading", lambda _: frozenset()) == "gone.md"


def test_anchors_slugs_a_heading_both_ways():
    anchors = docs._anchors("## The New Heading\n")
    assert "the-new-heading" in anchors


def test_anchors_keeps_underscores_in_an_identifier():
    # False positive #1 from the first real run: treating `_` as emphasis turns this into
    # `configfiles`, an anchor no renderer emits.
    assert "whole-file-configs-config_files" in docs._anchors("## Whole-file configs — config_files\n")


def test_anchors_keeps_githubs_double_hyphen_from_a_dropped_ampersand():
    # False positive #2: GitHub drops the `&` and keeps both surrounding spaces, so the anchor
    # carries a double hyphen. Collapsing space runs reports this correct link as broken.
    anchors = docs._anchors("## Bash & the CLI allowlist (cluster intro)\n")
    assert "bash--the-cli-allowlist-cluster-intro" in anchors
    # python-markdown's toc *does* collapse them, and both readings have to pass.
    assert "bash-the-cli-allowlist-cluster-intro" in anchors


def test_anchors_suffixes_duplicates_the_way_each_renderer_does():
    anchors = docs._anchors("## Notes\n\ntext\n\n## Notes\n")
    assert "notes" in anchors
    assert "notes_1" in anchors  # python-markdown
    assert "notes-1" in anchors  # github.com


def test_anchors_takes_an_explicit_attr_list_id():
    assert "custom-id" in docs._anchors("## Heading {#custom-id}\n")


def test_anchors_takes_an_html_anchor():
    assert "by-hand" in docs._anchors('<a id="by-hand"></a>\n\ntext\n')


def test_anchors_flattens_code_and_links_in_a_heading():
    assert "the-evolve-guide" in docs._anchors("## The `evolve` guide\n")
    assert "see-the-plan" in docs._anchors("## See [the plan](a.md)\n")


def test_anchors_skips_a_heading_inside_a_fenced_block():
    # A `##` in a code sample is not a heading, the same reason _relative_links skips fences.
    assert docs._anchors("```markdown\n## Not A Heading\n```\n") == frozenset()


def test_bad_link_catches_a_renamed_heading_across_files(tmp_cwd):
    """The plan's fixture, and the failure this exists for: a.md cites b.md's old anchor."""
    (tmp_cwd / "b.md").write_text("## The new heading\n")
    (tmp_cwd / "a.md").write_text("[x](b.md#the-old-heading)\n")
    problem = docs._bad_link(tmp_cwd / "a.md", "b.md#the-old-heading", _anchors_of)
    assert problem is not None
    assert "no such anchor in b.md" in problem


def test_bad_link_names_the_closest_surviving_anchor(tmp_cwd):
    # A renamed heading is usually a near miss, and naming it turns the report into the fix.
    (tmp_cwd / "b.md").write_text("## The new heading\n")
    problem = docs._bad_link(tmp_cwd / "a.md", "b.md#the-new-headings", _anchors_of)
    assert problem is not None
    assert "closest is #the-new-heading" in problem


def test_bad_link_accepts_a_same_file_anchor(tmp_cwd):
    # 59 of the 79 fragment links measured across the family were same-file, so this is most of
    # the surface rather than an edge case.
    source = tmp_cwd / "page-a.md"
    source.write_text("## Page A\n\nsee [above](#page-a)\n")
    assert docs._bad_link(source, "#page-a", _anchors_of) is None


def test_bad_link_catches_a_broken_same_file_anchor(tmp_cwd):
    source = tmp_cwd / "page-a.md"
    source.write_text("## Page A\n\nsee [above](#page-b)\n")
    assert docs._bad_link(source, "#page-b", _anchors_of) is not None


def test_bad_link_ignores_a_fragment_on_a_non_markdown_target(tmp_cwd):
    # Nothing here knows how to enumerate anchors in a .py or an image, and a fragment on one is
    # not this task's business.
    (tmp_cwd / "script.py").write_text("x = 1\n")
    assert docs._bad_link(tmp_cwd / "a.md", "script.py#L1", _anchors_of) is None


def test_link_check_stops_on_a_dangling_anchor(tmp_cwd, capsys):
    """End to end through the task, not just the helper — this is the gate step that has to fail."""
    (tmp_cwd / "b.md").write_text("## The new heading\n")
    (tmp_cwd / "a.md").write_text("[x](b.md#the-old-heading)\n")
    c = MockContext(run=Result(stdout="a.md\nb.md\n", exited=0))
    with pytest.raises(Exit):
        docs.link_check.body(c)
    assert "no such anchor in b.md" in capsys.readouterr().out


def test_bad_link_rejects_a_target_outside_the_repository(tmp_cwd):
    # The one that kept CI red for a day: `../../sibling-repo/file.md` opens fine on a machine with
    # both repos checked out side by side, and is dead everywhere else — so it has to fail on that
    # machine too, or the gate is green exactly where it needs to be red.
    sibling = tmp_cwd.parent / "sibling"
    sibling.mkdir(exist_ok=True)
    (sibling / "notes.md").write_text("hi")
    source = tmp_cwd / "docs" / "source.md"
    problem = docs._bad_link(source, "../../sibling/notes.md")
    assert problem is not None
    assert "escapes the repository" in problem


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
