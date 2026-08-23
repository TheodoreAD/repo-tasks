---
status: idea
updated: 2026-08-23
depends_on: [scaffoldapy]
---

## Context

Two places where this package writes or edits a file in a shape that this package's own quality
tooling then disagrees with. Both found 2026-08-23 while bringing `scaffoldapy` onto the family's
conventions — neither is `scaffoldapy`-specific, both reach every consumer.

### 1. `selfinstall.stamp` writes bash that `shfmt` immediately rewrites

`_STAMP_TEMPLATE` contains:

```shell
command -v uv >/dev/null 2>&1 || {
```

`shfmt` — the same `shfmt`, from this package's own `quality.shell_format_apply` — rewrites that to
`> /dev/null`. So `inv configure` writes `bootstrap-repo-tasks.sh`, the next `inv quality.precommit`
rewrites one line of it, and the next `inv configure` reverts it. A permanent one-line oscillation
in `git status`, in every consumer repo that has ever run both commands.

Confirmed live in `scaffoldapy` 2026-08-23: `configure` wrote the file, `precommit` produced a diff
on it immediately, twice in a row.

[PITFALL: `quality.check`'s `pre=` list is `lint_check, format_check, type_check, shell_check, test`
— `shell_format_check` is defined right next to `shell_check` but is not in it. So shell formatting
drift is only ever surfaced by running `fix`, i.e. by mutating the file, and never by the check-only
gate that CI runs. That asymmetry is why this has gone unnoticed: python has both `format_check` and
a formatter, shell has only the formatter.]

### 2. `configs.ensure_deps` needs the dev array pre-shaped across two lines

`_DEV_ARRAY_RE` matches `dev\s*=\s*\[(?P<items>.*?)\]` and splices one two-space-indented `"<dep>",`
line per missing dependency in at `match.end("items")`. That assumes the bracket pair is already
spread over two lines. Given `dev = []` it produces:

```toml
dev = [  "basedpyright>=1.39.10",
  "pytest",
  ...
]
```

which `dprint` rejects — so a freshly generated repo fails its very first `inv quality.check`.

Confirmed live: `scaffoldapy`'s template renders an empty `dependencies` array as `[]` (dprint's own
preferred shape, fixed there in `bd3919a`). Making the empty `dependency-groups.dev` match failed 6
of 7 end-to-end combinations. That template now carries a comment explaining why its empty dev group
can't take the shape dprint prefers — a workaround for this defect, living in another repo.

[PITFALL: `ensure_deps` runs as the _first_ of `scaffoldapy`'s `_tasks`, before any venv exists, so
"just run `dprint fmt` afterwards" is not available as a fix — there is no dprint on the machine yet
at that point. Whatever it writes has to be formatter-clean by construction.]

## Open questions

- **How to keep `stamp`'s output shfmt-clean.** Writing `> /dev/null` in the template is a
  one-character fix, but nothing stops the next edit to that template from reintroducing the
  problem.

  [NEEDS CLARIFICATION: is a test that runs `shfmt -d` over the rendered template enough, or should
  `stamp` shell out to `shfmt` on what it just wrote? The latter couples `selfinstall` to a quality
  tool being installed, which it currently doesn't need at all.]

- **Whether `check` should gain `shell_format_check`.** It would make python and shell symmetric and
  stop defect 1 from recurring silently.

  [NEEDS CLARIFICATION: does adding it break any consumer today? `power-user-linux-setup` has by far
  the most `*.sh` files in the family and has never had its shell formatting enforced by a
  check-only gate — worth running `shfmt -d` across every consumer before wiring this in, since the
  no-per-repo-allowances rule means it lands everywhere at once.]

- **How `ensure_deps` should edit TOML.** The regex splice is what makes the input shape
  load-bearing. A real TOML round-trip (`tomlkit`) would remove the constraint entirely.

  [NEEDS CLARIFICATION: does `tomlkit` clear the "task modules import stdlib + invoke only" bar in
  `power-user-linux-setup/contributing/repo-family-architecture.md`? It is small and single-purpose,
  like the `python-dotenv` exception — but it is currently only present transitively, via
  `bump-my-version`, and depending on a transitive dep is not acceptable either way. The cheaper
  alternative is to keep the regex and handle the empty-array case explicitly, writing
  `[\n  "…",\n]` when `items` is blank.]

## Recommended direction

Cheapest correct pass, in order:

1. Make `_STAMP_TEMPLATE` shfmt-clean, with a test asserting the rendered script survives `shfmt -d`
   unchanged.
2. Make `ensure_deps` produce a well-formed multi-line array whether the input was `dev = []` or
   `dev = [\n]`, with a test covering both input shapes and asserting the result is dprint-clean.
3. Then decide on `shell_format_check` in `check` — it's the durable guard for defect 1, but it's
   also the only item here that can fail other repos' CI on landing, so it wants the audit above
   first rather than being bundled in.

Once step 2 lands, `scaffoldapy`'s template comment about the empty dev group can be removed and its
`dev` group can take the same `[]` shape as `dependencies` — worth doing in the same pass so the
workaround doesn't outlive the bug.
