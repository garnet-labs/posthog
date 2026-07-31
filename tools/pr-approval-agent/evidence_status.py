#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml==6.0.3",
# ]
# ///
# ruff: noqa: T201
"""Mirror the Garnet runtime-evidence verdict as a commit status on the PR head.

Surfaces the same parse `review_pr.py` consumes as a `garnet/runtime-evidence`
status in the PR checks UI, bound to the head SHA:

    success  → evidence recorded for the head and every destination expected
    failure  → evidence recorded and at least one destination is off-policy
    pending  → no usable evidence for the head yet (waiting, stale, or a
               renderer format the parser refuses to trust)

The status is informational plus branch-protection-ready; the deny-bypass
decision itself stays inside review_pr.py.
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

from runtime_evidence import fetch_runtime_evidence, load_config

_CONTEXT = "garnet/runtime-evidence"


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
        print("runtime-evidence config absent; not posting a status")
        return 0

    pr = _gh_json([f"repos/{args.repo}/pulls/{args.pr_number}"])
    head_sha = pr["head"]["sha"]
    evidence = fetch_runtime_evidence(args.repo, args.pr_number, head_sha, config)

    if evidence.status == "pass":
        state = "success"
        description = f"pass — {len(evidence.destinations)} recorded destination(s), all expected"
    elif evidence.status == "unexpected":
        state = "failure"
        description = f"{len(evidence.unexpected)} unexpected destination(s): " + ", ".join(
            d["dest"] for d in evidence.unexpected[:3]
        )
    else:
        state = "pending"
        description = "no usable runtime evidence for this head yet (fail-closed)"

    target_url = evidence.permalinks[0] if evidence.permalinks else pr["html_url"]
    _gh_json(
        [
            f"repos/{args.repo}/statuses/{head_sha}",
            "-f",
            f"state={state}",
            "-f",
            f"context={_CONTEXT}",
            "-f",
            f"description={description[:140]}",
            "-f",
            f"target_url={target_url}",
        ]
    )
    print(f"{_CONTEXT} @ {head_sha[:9]}: {state} — {description}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
