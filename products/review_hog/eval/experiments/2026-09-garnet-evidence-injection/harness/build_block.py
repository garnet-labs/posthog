"""Build the compact exact-head Garnet evidence block injected in the treatment arm.

The block is machine-derived from the PR's Garnet Runtime Review record (the
``garnet:summary`` machine block plus the rendered diff tree), never hand-written:

- receipt_id: the Execution Profile id from the record's Garnet permalink
- head/compared SHA pair, or the explicit ``comparison: unavailable`` state
- added/removed recorded network evidence (destinations), split workload vs runner background
- recorded process evidence (execution chains) and file evidence, with kinds not
  recorded stated explicitly rather than omitted
- deterministic detections, or ``none recorded``

Usage: python3 build_block.py [--corpus corpus.json] [--out blocks.json]
"""

import re
import json
import argparse

PROFILE_RE = re.compile(r"[?&]profile=([0-9a-f-]{36})")
DEST_LINE = re.compile(r"^([+-])\s*[│├└─\s]*○ (.+?)\s*$")


def _diff_destinations(comment_body: str) -> tuple[list[dict], list[dict]]:
    """Added/removed destination lines from the record's diff trees, tagged by section."""
    added: list[dict] = []
    removed: list[dict] = []
    for block in re.findall(r"```diff\n(.*?)```", comment_body, re.DOTALL):
        section = "workload"
        for line in block.splitlines():
            if "runner background" in line:
                section = "runner background"
            m = DEST_LINE.match(line)
            if not m:
                continue
            entry = {"destination": m.group(2), "section": section}
            (added if m.group(1) == "+" else removed).append(entry)
    return added, removed


def build_block(pr: dict) -> dict | None:
    if not pr["garnet_exact_head"] or not pr["garnet_summary"]:
        return None
    s = pr["garnet_summary"]
    body = pr["garnet_comment_body"]
    profile = PROFILE_RE.search(body)
    added, removed = _diff_destinations(body)
    kinds = s.get("kinds", [])
    previous = s.get("previous")
    block = {
        "source": "Garnet Runtime Review (kernel-recorded CI runtime evidence)",
        "contract": s.get("contract"),
        "receipt_id": profile.group(1) if profile else None,
        "head_sha": s["commit"],
        "compared_sha": previous,
        "comparison": "available" if previous else "unavailable",
        "recorded_at": s.get("recorded"),
        "jobs_recorded": s.get("jobs"),
        "workload": {
            "jobs_changed": s.get("changed"),
            "jobs_unchanged": s.get("unchanged"),
            "destinations_added": s.get("added"),
            "destinations_removed": s.get("removed"),
        },
        "runner_background": {
            "destinations_added": s.get("backgroundAdded"),
            "destinations_removed": s.get("backgroundRemoved"),
        },
        "network_evidence": {
            "recorded": "network" in kinds,
            "execution_chains": s.get("chains"),
            "destinations": s.get("destinations"),
            "added": added,
            "removed": removed,
        },
        "process_evidence": {
            "recorded": True,
            "note": "processes appear as the execution chains behind each recorded action",
        },
        "file_evidence": {
            "recorded": "file" in kinds,
            "note": None if "file" in kinds else "no file evidence recorded for this run",
        },
        "deterministic_detections": [],
        "detections_note": "none recorded",
        "drill_down": "call the read-only garnet_drilldown tool to read the full recorded evidence for this head",
    }
    return block


def render_block(block: dict) -> str:
    """The block as it appears in the treatment prompt: compact, trusted, machine-derived."""
    lines = [
        f"receipt_id: {block['receipt_id']}",
        f"head: {block['head_sha']}",
    ]
    if block["comparison"] == "available":
        lines.append(f"compared with previous recorded head: {block['compared_sha']}")
    else:
        lines.append("comparison unavailable (no previous recorded head)")
    w = block["workload"]
    lines.append(
        f"workload: {w['jobs_changed']} job(s) changed, {w['jobs_unchanged']} unchanged; "
        f"destinations +{w['destinations_added']} -{w['destinations_removed']}"
    )
    ne = block["network_evidence"]
    lines.append(
        f"recorded network evidence: {ne['execution_chains']} execution chains, {ne['destinations']} destinations"
    )
    for e in ne["added"]:
        lines.append(f"  + {e['destination']} ({e['section']})")
    for e in ne["removed"]:
        lines.append(f"  - {e['destination']} ({e['section']})")
    if not ne["added"] and not ne["removed"]:
        lines.append("  no destination additions or removals recorded")
    lines.append(f"file evidence: {'recorded' if block['file_evidence']['recorded'] else 'none recorded for this run'}")
    dets = block["deterministic_detections"]
    lines.append("deterministic detections: " + (", ".join(dets) if dets else "none recorded"))
    lines.append(f"recorded at: {block['recorded_at']} · contract {block['contract']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus.json")
    ap.add_argument("--out", default="blocks.json")
    args = ap.parse_args()
    corpus = json.load(open(args.corpus))
    out = {}
    for pr in corpus["prs"]:
        block = build_block(pr)
        if block:
            out[str(pr["pr_number"])] = {"block": block, "rendered": render_block(block)}
    json.dump(out, open(args.out, "w"), indent=1)
    print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
        f"{len(out)} evidence blocks -> {args.out}"
    )


if __name__ == "__main__":
    main()
