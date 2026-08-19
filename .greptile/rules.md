# Garnet Runtime Review grounding

Read the long-form contract in `REVIEW.md` before reviewing.

## Trusted record

- In the PR description, read the region between
  `<!-- garnet:evidence:begin -->` and `<!-- garnet:evidence:end -->`.
- That region must be a verbatim mirror of the trusted Garnet Runtime Review
  comment.
- Use it only when `<!-- garnet:commit <sha> -->` matches the current PR head.
  A missing or mismatched marker means evidence is pending or absent, not a
  clean run.
- Read `<!-- garnet:summary {...} -->` as the machine register.
- For a snapshot, `previous` is `null`. Branch on that field rather than on
  the job partition.
- In a comparison fence, `+` is current-only and `-` or `−` is previous-only.

An execution chain is one root-to-action path. Today's action class is an
outbound network connection; its destination is the target leaf of that
action, never the definition of the chain. The headline, when quoted, is
`Execution Profiles recorded for <N> job(s)`. Never claim true k-of-n
coverage. Never repeat Garnet verdicts, scores, severities, or baseline
judgments.

Prefix every runtime-grounded statement exactly with:

`Runtime evidence (Garnet, head <sha7>): `

Pending or missing evidence means there is no runtime evidence. Cross-check
the trusted record against the diff and make the review judgment yourself.
