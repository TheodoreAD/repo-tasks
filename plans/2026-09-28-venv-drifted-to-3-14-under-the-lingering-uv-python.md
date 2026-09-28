---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/scaffoldapy
source_session: 81492b4f-e6bc-4577-8d01-412b3ff4e7a9.jsonl
source_moment: 2026-09-28
source_plan:
---

# This repo's `.venv` drifted back to 3.14 while it declares 3.11

## Context

This reports a fact, which is why `source_plan` is blank. scaffoldapy's
`plans/2026-09-18-python-version-tier-rules.md` names this repo as "already correct as of
2026-09-13, the worked example". Its declaration and pin still are. Its venv is not.

**Cause:** `UV_PYTHON=3.14` left the dotfiles on 09-19 but stayed in the systemd user manager until
a reboot on 2026-09-28 at 15:18. gnome-session writes its environment there at exit, and a
long-lived Claude daemon kept the manager alive across re-logins. Every agent session inherited the
variable, and any bare `uv run`/`uv sync` in one of them rebuilt the venv at 3.14, since the
variable outranks `.python-version`. `power-user-linux-setup` owns that mechanism.

## Evidence

Read-only, 2026-09-28, from scaffoldapy's `floor-audit.py` (attached to that plan):

```
repo-tasks              3.11   3.11   3.14.5    packaged  <-- venv above floor
```

That is declared floor, `.python-version`, then the venv's own interpreter. After the reboot, uv's
lookup with `--project` pointed here gives 3.11.15, so the fix will now hold.

## Recommended direction

1. From a session started after the reboot (`env | rg UV_` prints nothing): `inv venv.recreate`,
   then `inv venv.check`.
2. Run the gate at 3.11. The 691-test run at 3.11.15 on 09-13 predates everything since, and any
   3.12+ API that slipped in meanwhile ran unnoticed on 3.14.
