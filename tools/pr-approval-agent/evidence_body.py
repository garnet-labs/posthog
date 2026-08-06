#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml==6.0.3",
# ]
# ///
# ruff: noqa: T201
"""Sync the parsed Garnet runtime evidence into the PR description.

Renders the same parse `review_pr.py` consumes into a marker-delimited
block in the PR body, so surfaces that read the description — Greptile
and other AI reviewers — ground in head-pinned recorded evidence instead
of the author's claims:

    <!-- garnet:evidence:begin -->
    ...rendered evidence for the current head...
    <!-- garnet:evidence:end -->

The block is upserted idempotently: replaced in place when the markers
exist, appended otherwise. When no usable evidence exists for the head
the block says so (fail-closed) rather than being removed.
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

from runtime_evidence import RuntimeEvidence, fetch_runtime_evidence, load_config

BEGIN_MARKER = "<!-- garnet:evidence:begin -->"
END_MARKER = "<!-- garnet:evidence:end -->"


def evidence_block(evidence: RuntimeEvidence, head_sha: str) -> str:
    """Render the PR-body evidence block for the current head."""
    lines = [BEGIN_MARKER, "## Runtime evidence (Garnet)", ""]
    if evidence.status == "missing":
        lines.append(
            f"No usable runtime evidence recorded for head `{head_sha[:7]}` yet. Do not assume execution was clean."
        )
    else:
        lines.append(
            f"Kernel-recorded execution tree for head `{evidence.commit_sha[:7]}` — "
            f"status: **{evidence.status}**. Each line is an execution chain "
            "(process lineage) and the destination its outbound connection reached:"
        )
        lines.append("")
        for d in evidence.destinations:
            note = f" ({d['note']})" if d["note"] else ""
            lineage = f"`{d['lineage']}` → " if d["lineage"] else "→ "
            prefix = "**NEW chain** " if d["new"] else ""
            lines.append(f"- {prefix}{lineage}`{d['dest']}`{note}")
        if evidence.new_destinations:
            lines.append("")
            lines.append(
                "Chains marked NEW were not recorded on the previously profiled "
                "commit; each one must be explained by this diff."
            )
        lines.append("")
        for link in evidence.permalinks[:3]:
            lines.append(f"Verify independently: [Garnet run profile]({link})")
    lines += [
        "",
        "<sub>Synced from the Garnet Runtime Review comment for the current head. "
        "Reviewers should ground runtime-behavior claims in this evidence "
        "(see <code>.stamphog/greptile-runtime-evidence.md</code>).</sub>",
        END_MARKER,
    ]
    return "\n".join(lines)


def upsert_block(body: str, block: str) -> str:
    """Replace the marker-delimited block in the body, or append it."""
    begin = body.find(BEGIN_MARKER)
    end = body.find(END_MARKER)
    if begin != -1 and end != -1 and end >= begin:
        return body[:begin] + block + body[end + len(END_MARKER) :]
    if body.strip():
        return body.rstrip() + "\n\n" + block + "\n"
    return block + "\n"


def _gh_json(args: list[str]) -> dict:
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--repo", required=True, help="owner/name")
    args = parser.parse_args()

    config = load_config(Path(__file__).resolve().parents[2] / ".stamphog")
    if config is None:
        print("runtime-evidence config absent; not syncing the PR body")
        return 0

    pr = _gh_json([f"repos/{args.repo}/pulls/{args.pr_number}"])
    head_sha = pr["head"]["sha"]
    evidence = fetch_runtime_evidence(args.repo, args.pr_number, head_sha, config)

    block = evidence_block(evidence, head_sha)
    new_body = upsert_block(pr.get("body") or "", block)
    if new_body == (pr.get("body") or ""):
        print(f"PR body already current for head {head_sha[:9]} ({evidence.status})")
        return 0
    _gh_json(
        [
            f"repos/{args.repo}/pulls/{args.pr_number}",
            "-X",
            "PATCH",
            "-f",
            f"body={new_body}",
        ]
    )
    print(f"PR body evidence block synced @ {head_sha[:9]}: {evidence.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
