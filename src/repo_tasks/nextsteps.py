"""The "here is what to run now" block every task prints when it stops short of done.

One line of output shape, in one place, because five modules print it and three of them used to
print it themselves. It lived in `gitflow.py` as `_next_steps` — where the flow tasks that print it
most often are — and `configs.py`, `deps.py` and `venv.py` each imported that private name with a
`reportPrivateUsage` suppression, while `trunkflow.py` and `release.py` hand-rolled the same two
`print` calls rather than add a fourth. A block of output that five modules produce is not
gitflow's; it is this package's way of ending a task that cannot finish on its own.

Nothing here decides *what* the next step is — that is the calling task's judgement and belongs in
its own module beside the condition that produced it. This owns the shape and nothing else."""


def next_steps(*lines: str, preamble: str | None = None) -> None:
    """Print the next-steps block: a blank line, a heading, then one bullet per line.

    `preamble` prefixes the heading rather than printing above it — `trunkflow.cut` says
    "Nothing pushed. Next steps:" as one sentence, and that reads as a single thought where a
    separate line would read as two."""
    heading = f"{preamble} Next steps:" if preamble else "Next steps:"
    print(f"\n{heading}")
    for line in lines:
        print(f"  - {line}")
