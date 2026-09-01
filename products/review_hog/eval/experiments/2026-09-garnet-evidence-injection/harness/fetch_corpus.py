"""Build the frozen corpus for the Garnet evidence-injection A/B experiment.

For each replay PR on the fork (default #139-#188), records everything both arms need,
frozen to the exact head SHA so the two arms are byte-identical inputs:

- PR metadata (title, body, head/base SHA)
- the changed files with patches (the reviewer's diff input)
- the Garnet Runtime Review sticky comment, only when its ``garnet:commit`` marker
  equals the live head SHA (exact-head binding; stale or missing records are kept in
  the corpus row as ``garnet_exact_head: false`` and excluded from the treatment arm's
  evidence source, never silently substituted)
- the parsed ``garnet:summary`` machine block

Usage: python3 fetch_corpus.py [--repo garnet-labs/posthog] [--first 139] [--last 188] [--out corpus.json]
"""

import re
import sys
import json
import argparse
import subprocess

MARKER_COMMIT = re.compile(r"<!-- garnet:commit ([0-9a-f]{40}) -->")
MARKER_SUMMARY = re.compile(r"<!-- garnet:summary (\{.*?\}) -->", re.DOTALL)
STICKY = "<!-- garnet-runtime-review -->"


def gh_api(path: str, paginate: bool = False) -> object:
    cmd = ["gh", "api", path]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def fetch_pr(repo: str, number: int) -> dict | None:
    try:
        pr = gh_api(f"repos/{repo}/pulls/{number}")
    except subprocess.CalledProcessError:
        print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
            f"#{number}: not found, skipping", file=sys.stderr
        )
        return None
    files = gh_api(f"repos/{repo}/pulls/{number}/files", paginate=True)
    files = [f for page in files for f in page] if files and isinstance(files[0], list) else files
    comment_pages = gh_api(f"repos/{repo}/issues/{number}/comments", paginate=True)
    comments = (
        [c for page in comment_pages for c in page]
        if comment_pages and isinstance(comment_pages[0], list)
        else comment_pages
    )

    head_sha = pr["head"]["sha"]
    garnet = next((c for c in comments if STICKY in (c.get("body") or "")), None)
    garnet_body = garnet["body"] if garnet else None
    marker = MARKER_COMMIT.search(garnet_body) if garnet_body else None
    summary_m = MARKER_SUMMARY.search(garnet_body) if garnet_body else None
    exact_head = bool(marker and marker.group(1) == head_sha)
    summary = json.loads(summary_m.group(1)) if summary_m else None

    return {
        "pr_number": number,
        "url": pr["html_url"],
        "title": pr["title"],
        "body": pr.get("body") or "",
        "head_sha": head_sha,
        "base_sha": pr["base"]["sha"],
        "state": pr["state"],
        "files": [
            {
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "patch": f.get("patch", ""),
            }
            for f in files
        ],
        "garnet_comment_present": garnet_body is not None,
        "garnet_exact_head": exact_head,
        "garnet_marker_commit": marker.group(1) if marker else None,
        "garnet_summary": summary,
        "garnet_comment_body": garnet_body,
        # Non-garnet PR comments both arms see identically (quoted verbatim, untrusted).
        "other_comments": [
            {"user": c["user"]["login"], "body": c["body"]} for c in comments if STICKY not in (c.get("body") or "")
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="garnet-labs/posthog")
    ap.add_argument("--first", type=int, default=139)
    ap.add_argument("--last", type=int, default=188)
    ap.add_argument("--out", default="corpus.json")
    args = ap.parse_args()

    rows = []
    for n in range(args.first, args.last + 1):
        row = fetch_pr(args.repo, n)
        if row is None:
            continue
        rows.append(row)
        tag = (
            "exact-head"
            if row["garnet_exact_head"]
            else ("stale/missing" if row["garnet_comment_present"] else "no-comment")
        )
        print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
            f"#{n}: {row['head_sha'][:7]} garnet={tag} files={len(row['files'])}"
        )

    with open(args.out, "w") as f:
        json.dump({"repo": args.repo, "prs": rows}, f, indent=1)
    exact = sum(1 for r in rows if r["garnet_exact_head"])
    print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
        f"\n{len(rows)} PRs recorded, {exact} with exact-head Garnet evidence -> {args.out}"
    )


if __name__ == "__main__":
    main()
