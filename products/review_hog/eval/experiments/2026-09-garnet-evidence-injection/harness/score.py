"""Aggregate the two-arm run results into the experiment's metric table.

Reads runs/pr<N>-<arm>.json and emits per-arm and per-PR:
- findings raised / validated / dismissed
- severity mix (must_fix / should_fix / consider) after validator adjustment
- tier/escalation proxy: highest validated severity per PR (the pipeline's publish
  tier is driven by validated severities)
- runtime-evidence-grounded findings (finding or verdict text references the
  recorded runtime evidence)
- drill-down invocations, counted separately per stage (never part of the verdict)
- recall vs the adjudicated real-findings set in adjudicated.json when present
  (format: {"<pr>": [{"key": "...", "match": "<substring matched against finding titles+issues>"}]})

Usage: python3 score.py [--runs runs/] [--adjudicated adjudicated.json] [--out results.md]
"""

import json
import argparse
from collections import defaultdict
from pathlib import Path

SEVERITY_ORDER = {"must_fix": 3, "should_fix": 2, "consider": 1}
EVIDENCE_TERMS = ("garnet", "runtime evidence", "recorded network", "execution chain", "receipt_id", "recorded run")


def load_runs(runs_dir: Path) -> dict:
    runs: dict = defaultdict(dict)
    for f in sorted(runs_dir.glob("pr*-*.json")):
        r = json.loads(f.read_text())
        runs[r["pr_number"]][r["arm"]] = r
    return runs


def _final_severity(issue: dict, verdict: dict) -> str | None:
    if not verdict.get("is_valid"):
        return None
    return verdict.get("adjusted_priority") or issue.get("priority")


def summarize_arm(r: dict) -> dict:
    issues = {i.get("id"): i for i in r["issues"]}
    validated, severities, evidence_grounded = 0, [], 0
    for v in r["verdicts"]:
        issue = issues.get(v["issue_id"], {})
        sev = _final_severity(issue, v["verdict"])
        if sev:
            validated += 1
            severities.append(sev)
        text = json.dumps(issue).lower() + json.dumps(v["verdict"]).lower()
        if any(t in text for t in EVIDENCE_TERMS):
            evidence_grounded += 1
    top = max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0)) if severities else None
    drills = {k: len(v) for k, v in r["drilldown_invocations"].items()}
    return {
        "raised": len(r["issues"]),
        "validated": validated,
        "dismissed": len(r["verdicts"]) - validated,
        "severities": severities,
        "top_severity": top,
        "evidence_grounded": evidence_grounded,
        "drilldown": drills,
    }


def recall(r: dict, adjudicated: list[dict]) -> tuple[int, int]:
    if not adjudicated:
        return 0, 0
    text = json.dumps(r["issues"]).lower()
    hit = sum(1 for a in adjudicated if a["match"].lower() in text)
    return hit, len(adjudicated)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--adjudicated", default="adjudicated.json")
    ap.add_argument("--out", default="results.md")
    args = ap.parse_args()

    runs = load_runs(Path(args.runs))
    adj_path = Path(args.adjudicated)
    adjudicated = json.loads(adj_path.read_text()) if adj_path.exists() else {}

    lines = [
        "# Garnet evidence-injection A/B — results",
        "",
        "| PR | arm | raised | validated | dismissed | top severity | evidence-grounded | recall | drill-down (review/validation) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    totals: dict = defaultdict(lambda: defaultdict(int))
    for pr in sorted(runs):
        for arm in ("control", "treatment"):
            r = runs[pr].get(arm)
            if not r:
                continue
            s = summarize_arm(r)
            hit, n = recall(r, adjudicated.get(str(pr), []))
            d = s["drilldown"]
            lines.append(
                f"| #{pr} | {arm} | {s['raised']} | {s['validated']} | {s['dismissed']} | "
                f"{s['top_severity'] or '—'} | {s['evidence_grounded']} | "
                f"{f'{hit}/{n}' if n else '—'} | {d.get('review', 0)}/{d.get('validation', 0)} |"
            )
            t = totals[arm]
            t["prs"] += 1
            t["raised"] += s["raised"]
            t["validated"] += s["validated"]
            t["evidence_grounded"] += s["evidence_grounded"]
            t["escalated"] += 1 if s["top_severity"] == "must_fix" else 0
            t["drill_review"] += d.get("review", 0)
            t["drill_validation"] += d.get("validation", 0)
            t["recall_hit"] += hit
            t["recall_n"] += n

    lines += ["", "## Per-arm aggregate", "", "| metric | control | treatment |", "|---|---|---|"]
    for metric in ("prs", "raised", "validated", "evidence_grounded", "escalated", "drill_review", "drill_validation"):
        lines.append(f"| {metric} | {totals['control'][metric]} | {totals['treatment'][metric]} |")
    for arm in ("control", "treatment"):
        t = totals[arm]
        t["recall_pct"] = f"{t['recall_hit']}/{t['recall_n']}" if t["recall_n"] else "no adjudicated set"
    lines.append(f"| recall | {totals['control']['recall_pct']} | {totals['treatment']['recall_pct']} |")
    lines += [
        "",
        "Human attention is not measured: these were no-publish eval runs, so no human ever saw the output.",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
        f"wrote {args.out}"
    )


if __name__ == "__main__":
    main()
