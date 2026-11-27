---
status: idea
updated: 2026-11-25
---

# A .gitattributes ships as a canonical config

## Context

Filed from `agent-skills` on 2026-11-25, while preparing a Windows machine to join the plans store.
The user: "we should have a standard gitattributes somewhere, this is becoming a theme."

The theme so far:

- `power-user-linux-setup`'s `plans/2026-09-07-agents-md-and-skills-on-native-windows.md` found the
  quality gate failing on every markdown file of a Windows checkout. Git for Windows' installer sets
  `core.autocrlf=true` system-wide, tracked files check out CRLF, and dprint reformats them all. It
  called a `.gitattributes` pinning LF "worth having regardless of Windows".
- `agent-skills` added its own `.gitattributes` on 2026-11-25 for the same reason, ahead of this.
- `plan-conveyor`'s plans store gets one written by `plans.py install`, because a store edited from
  Linux and Windows machines conflicts across whole files once CRLF reaches a commit.

No personal repo had one before that. `power-user-linux-setup`'s machine-level
`core.autocrlf =
input` covers only machines it sets up, and only for checkouts made after it ran.

## Recommended direction

Add `.gitattributes` to `_CONFIG_FILES` in `src/repo_tasks/configs.py`, shipped from
`src/repo_tasks/configs/`, so every consumer gets the same file from one place. The content the user
asked for: LF everywhere, unless a file is Windows-only.

```gitattributes
* text=auto eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
```

- [DECISION 2026-11-25: LF for every text file, whatever `core.autocrlf` says; CRLF only for the
  Windows-only script types that need it. `text=auto` leaves binary detection to git.]
- `agent-skills`' copy is the same content, so materialising the canonical file there is a no-op.
- `scaffoldapy` generates new projects with repo-tasks' configs; check whether its template needs
  the file listed separately or inherits it through the same mechanism.
- [NEEDS CLARIFICATION: a consumer that already has CRLF committed needs a one-time
  `git add --renormalize .` commit when the file first lands. Does the materialising task detect
  that and say so, or is it left to the consumer's first gate run?]
