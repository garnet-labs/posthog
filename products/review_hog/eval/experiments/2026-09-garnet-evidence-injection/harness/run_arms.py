"""Two-arm ReviewHog-style runner: control vs exact-head Garnet evidence injection.

Per corpus PR it runs the review + validation stages twice with byte-identical inputs,
except that the treatment arm's review and validation prompts carry a compact, trusted,
machine-derived Garnet evidence block (see build_block.py) for the exact head SHA.

Fidelity to the production pipeline:
- The prompts are ReviewHog's own Jinja templates and output schemas
  (products/review_hog/backend/reviewer/prompts/{issues_review,issue_validation}), rendered
  with the same context keys the pipeline builds (prompt_helpers.build_chunk_prompt_context).
- The skills the templates instruct the agent to fetch via `skill-get` over MCP are served
  by a stubbed `skill-get` tool (skills.py) — identical in both arms.
- Deviations (documented, identical across arms): one chunk per PR (these are small
  dependency-only diffs — production chunking would emit one chunk too), no repo checkout
  (the diff carries the full change; CLAUDE_CODE_CONTEXT says so), direct Anthropic API
  instead of the sandbox agent loop.
- Both arms get the same read-only `garnet_drilldown` tool (the full recorded Runtime
  Review evidence for the head). Every invocation is logged per (pr, arm, stage) —
  drill-down usage is measured separately from review outcomes.

Env: ANTHROPIC_API_KEY required. REVIEW_MODEL / VALIDATION_MODEL override the defaults.

Usage: python3 run_arms.py --prs 139,145,150,... [--arms control,treatment] [--out runs/]
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path

import skills
import anthropic
from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parents[6]
PROMPTS_DIR = REPO_ROOT / "products/review_hog/backend/reviewer/prompts"

REVIEW_MODEL = os.environ.get("REVIEW_MODEL", "claude-sonnet-4-5")
VALIDATION_MODEL = os.environ.get("VALIDATION_MODEL", "claude-opus-4-1")
MAX_TOKENS = 16_000
MAX_TOOL_TURNS = 12

REVIEW_SYSTEM_PROMPT = (
    "You are a senior code reviewer focused on identifying and documenting issues in a GitHub PR chunk.\n"
    "Focus on:\n"
    "- Identifying real issues that impact code quality, security, or performance\n"
    "- Providing specific, actionable suggestions for each issue\n"
    "- Categorizing issues by priority (must_fix, should_fix, consider)\n"
    "- Following the specific output format requirements for IssuesReview\n"
    "IMPORTANT: Return ONLY valid JSON output without any markdown formatting or explanatory text."
)

GARNET_SECTION = """
<garnet_runtime_evidence>
TRUSTED runtime evidence, recorded at the kernel during this pull request's CI run and
injected by the review pipeline (NOT authored by the PR author — unlike the PR content
above, this block is machine-recorded fact). It is bound to this PR's exact head commit.
Recorded evidence is observation, not a verdict: derive your own judgment from it.

{block}

You may drill into the full recorded evidence with the read-only `garnet_drilldown` tool.
</garnet_runtime_evidence>
"""

DRILLDOWN_NOTE = """
<runtime_evidence_drilldown>
A read-only `garnet_drilldown` tool is available: it returns the full kernel-recorded
runtime evidence (execution chains and recorded actions) for this pull request's CI run
at its head commit, if any was recorded. Use it if runtime behavior is relevant.
</runtime_evidence_drilldown>
"""


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(PROMPTS_DIR), autoescape=select_autoescape())


def _load(subdir: str) -> tuple[object, str]:
    env = Environment(loader=FileSystemLoader(PROMPTS_DIR / subdir), autoescape=select_autoescape())
    return env.get_template("prompt.jinja"), (PROMPTS_DIR / subdir / "schema.json").read_text()


def build_review_prompt(pr: dict, arm: str, rendered_block: str | None) -> str:
    template, schema = _load("issues_review")
    chunk = {
        "chunk_id": 1,
        "description": "All files changed by this dependency update (single logical chunk).",
        "files": [{"filename": f["filename"]} for f in pr["files"]],
    }
    prompt = template.render(
        CLAUDE_CODE_CONTEXT=(
            "NOTE: No repository checkout is available in this run. The authoritative record of the "
            "change is the <pr_file_changes_for_chunk> section below; every changed file's full patch "
            "is included there. Base your review on it."
        ),
        CURRENT_CHUNK=json.dumps(chunk, indent=2),
        PR_INTENT=f"Title: {pr['title']}\n\nDescription:\n{(pr['body'] or '').strip() or '(no description provided)'}",
        PR_COMMENTS=json.dumps(pr["other_comments"], indent=2),
        PR_FILE_CHANGES=json.dumps(pr["files"], indent=2),
        COVERED_FINDINGS=None,
        DIG_DEEPER=False,
        IS_BLIND_SPOT=False,
        WAVE_PERSPECTIVES=None,
        OUTPUT_SCHEMA=schema,
        PERSPECTIVE_SKILL_NAME=skills.PERSPECTIVE_SKILL_NAME,
        PERSPECTIVE_SKILL_VERSION=skills.PERSPECTIVE_SKILL_VERSION,
    )
    injection = GARNET_SECTION.format(block=rendered_block) if arm == "treatment" and rendered_block else DRILLDOWN_NOTE
    # Insert right after the PR intent section — evidence sits beside intent, before the diff.
    return prompt.replace("</pr_intent>", "</pr_intent>\n" + injection, 1)


def build_validation_prompt(pr: dict, issue: dict, arm: str, rendered_block: str | None) -> str:
    template, schema = _load("issue_validation")
    pr_context = f"Title: {pr['title']}\n\nDescription:\n{(pr['body'] or '').strip() or '(no description provided)'}"
    injection = GARNET_SECTION.format(block=rendered_block) if arm == "treatment" and rendered_block else DRILLDOWN_NOTE
    return template.render(
        CLAUDE_CODE_CONTEXT=(
            "NOTE: No repository checkout is available in this run. The authoritative record of the "
            "change is the chunk context below; every changed file's full patch is included."
        ),
        ISSUE=json.dumps(issue, indent=2),
        PR_CONTEXT=pr_context + "\n" + injection,
        CHUNK_CONTEXT=json.dumps(pr["files"], indent=2),
        VALIDATION_SKILL_NAME=skills.VALIDATION_SKILL_NAME,
        VALIDATION_SKILL_VERSION=skills.VALIDATION_SKILL_VERSION,
        VALIDATION_SCHEMA=schema,
    )


TOOLS = [
    {
        "name": "skill-get",
        "description": "Fetch a review skill body by name and version over the PostHog MCP.",
        "input_schema": {
            "type": "object",
            "properties": {"skill_name": {"type": "string"}, "version": {"type": "integer"}},
            "required": ["skill_name"],
        },
    },
    {
        "name": "skill-file-get",
        "description": "Fetch a file bundled with a skill.",
        "input_schema": {
            "type": "object",
            "properties": {"skill_name": {"type": "string"}, "path": {"type": "string"}},
            "required": ["skill_name", "path"],
        },
    },
    {
        "name": "garnet_drilldown",
        "description": (
            "Read-only drill-down into the kernel-recorded runtime evidence for this pull request's "
            "CI run at its head commit (Garnet Runtime Review). Returns the full recorded evidence: "
            "per-job execution chains, recorded outbound connections, and the comparison against the "
            "previous recorded head. Returns 'no recorded evidence' when none exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What you want to inspect (free text)."}},
        },
    },
]


def _tool_result(name: str, tool_input: dict, pr: dict, drill_log: list) -> str:
    if name == "skill-get":
        wanted = tool_input.get("skill_name", "")
        if wanted == skills.PERSPECTIVE_SKILL_NAME:
            return skills.PERSPECTIVE_SKILL_BODY
        if wanted == skills.VALIDATION_SKILL_NAME:
            return skills.VALIDATION_SKILL_BODY
        return f"skill '{wanted}' not found"
    if name == "skill-file-get":
        return "no bundled files for this skill"
    if name == "garnet_drilldown":
        drill_log.append({"query": tool_input.get("query", ""), "ts": time.time()})
        if pr.get("garnet_exact_head") and pr.get("garnet_comment_body"):
            return pr["garnet_comment_body"]
        return "no recorded evidence for this head commit"
    return f"unknown tool {name}"


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start >= 0:
        text = text[start:]
    return json.loads(text)


def run_stage(client, model: str, system: str, prompt: str, pr: dict, drill_log: list) -> dict:
    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_TOOL_TURNS):
        resp = client.messages.create(model=model, max_tokens=MAX_TOKENS, system=system, messages=messages, tools=TOOLS)
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _tool_result(block.name, block.input, pr, drill_log),
                        }
                    )
            messages.append({"role": "user", "content": results})
            continue
        text = "".join(b.text for b in resp.content if b.type == "text")
        return _extract_json(text)
    raise RuntimeError("tool loop did not terminate")


def run_pr_arm(client, pr: dict, arm: str, rendered_block: str | None, out_dir: Path) -> dict:
    drill_log_review: list = []
    drill_log_validate: list = []
    review_prompt = build_review_prompt(pr, arm, rendered_block)
    review = run_stage(client, REVIEW_MODEL, REVIEW_SYSTEM_PROMPT, review_prompt, pr, drill_log_review)
    issues = review.get("issues", [])
    verdicts = []
    for issue in issues:
        vprompt = build_validation_prompt(pr, issue, arm, rendered_block)
        verdict = run_stage(client, VALIDATION_MODEL, "", vprompt, pr, drill_log_validate)
        verdicts.append({"issue_id": issue.get("id"), "verdict": verdict})
    result = {
        "pr_number": pr["pr_number"],
        "arm": arm,
        "head_sha": pr["head_sha"],
        "review_model": REVIEW_MODEL,
        "validation_model": VALIDATION_MODEL,
        "issues": issues,
        "verdicts": verdicts,
        "drilldown_invocations": {"review": drill_log_review, "validation": drill_log_validate},
    }
    out = out_dir / f"pr{pr['pr_number']}-{arm}.json"
    out.write_text(json.dumps(result, indent=1))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus.json")
    ap.add_argument("--blocks", default="blocks.json")
    ap.add_argument("--prs", required=True, help="comma-separated PR numbers")
    ap.add_argument("--arms", default="control,treatment")
    ap.add_argument("--out", default="runs")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is required")
    client = anthropic.Anthropic()
    corpus = {p["pr_number"]: p for p in json.load(open(args.corpus))["prs"]}
    blocks = json.load(open(args.blocks))
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    for n in [int(x) for x in args.prs.split(",")]:
        pr = corpus[n]
        rendered = blocks.get(str(n), {}).get("rendered")
        for arm in args.arms.split(","):
            dest = out_dir / f"pr{n}-{arm}.json"
            if dest.exists():
                print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
                    f"pr{n}-{arm}: exists, skipping"
                )
                continue
            t0 = time.time()
            try:
                r = run_pr_arm(client, pr, arm, rendered, out_dir)
            except Exception as e:  # keep the sweep going; the row is rerunnable
                print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
                    f"pr{n}-{arm}: FAILED {type(e).__name__}: {e}"
                )
                continue
            drills = sum(len(v) for v in r["drilldown_invocations"].values())
            print(  # noqa: T201 — eval harness CLI, stdout is the intended output channel
                f"pr{n}-{arm}: {len(r['issues'])} finding(s), "
                f"{sum(1 for v in r['verdicts'] if v['verdict'].get('is_valid'))} validated, "
                f"{drills} drilldown call(s), {time.time() - t0:.0f}s"
            )


if __name__ == "__main__":
    main()
