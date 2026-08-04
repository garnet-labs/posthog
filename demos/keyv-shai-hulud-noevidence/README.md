# Runtime-review demo — no-runtime-evidence baseline

This mirror directory exists to demonstrate what an AI code reviewer sees
**without** Garnet Execution Profile evidence attached. The workflow
`ci-demo-keyv-shai-hulud.yml` watches `demos/keyv-shai-hulud/**` only —
this path is intentionally excluded from that watch, so PRs bumping the
version here do NOT get a Garnet execution-diff comment.

Package contents mirror `demos/keyv-shai-hulud/` exactly. Compare the AI
reviewer's take on a PR against this path (no runtime evidence) with a
PR against the canonical path (Garnet posts an execution-diff comment).
