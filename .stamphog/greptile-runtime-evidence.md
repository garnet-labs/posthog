# Runtime evidence (Garnet) — grounding for AI review

This repository runs its CI dependency install under the Garnet sensor.
Garnet records the execution tree at the kernel while the PR's code runs:
every execution chain (one path from the runner's root to an action — today,
an outbound connection) and the destination that connection reached.

Where the evidence lives on a PR:

- The sticky `Garnet Runtime Review` comment: the full execution tree,
  head-pinned via an embedded `<!-- garnet:commit <sha> -->` marker, with a
  comparison against the previously profiled commit when one exists.
- The PR description block between `<!-- garnet:evidence:begin -->` and
  `<!-- garnet:evidence:end -->`: the same evidence, parsed and synced
  automatically for the current head.
- The `garnet/runtime-evidence` commit status on the head.

How to use it when reviewing:

- Treat the evidence as recorded ground truth about what the change did when
  it ran — not a claim by the author.
- Evidence counts only when its commit marker equals the current head. A
  block or comment pinned to an older commit is stale; say so instead of
  citing it.
- Ground runtime-behavior claims in the recorded chains: cite the head
  commit, the specific chain (lineage → destination), and the Garnet public
  run profile link.
- A chain marked NEW versus the previously profiled commit must be explained
  by this diff. Name the chain and ask the author to account for it if the
  diff does not.
- There is no static egress allowlist. Judge each destination by the
  execution chain that produced it, in the context of the diff.
- Clean evidence covers the runtime-behavior slice only. It never vouches
  for logic correctness or overall PR safety.
