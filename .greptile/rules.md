# Review rules

## Ground dependency and CI changes in recorded runtime evidence

When a PR carries a `Runtime evidence (Garnet)` section in its description or a
`Garnet Runtime Review` comment, treat it as the primary evidence for what the
change did when it ran. The section is a verbatim mirror of the comment and is
pinned to the PR head commit.

Read it as facts, not as a verdict: each line is an execution chain (the process
lineage from the runner down to an action) and the destination that chain
reached. Judge each chain against the diff — a package install reaching its
registry is coherent; a lifecycle script spawning a network client the diff
never mentions is not.

Cite grounded findings so a reader can verify them:

> Runtime evidence (Garnet, head `<short sha>`): `<process lineage>` →
> `<destination>` (`<workflow>/<job>`) — <Execution Profile URL>

Do not claim runtime behavior the evidence does not show, and do not treat
absent evidence as clean execution. If the recorded workload does not exercise
the code the diff changes, say so.
