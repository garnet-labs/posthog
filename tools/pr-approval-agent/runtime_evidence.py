"""Consume Garnet Runtime Review evidence posted on the PR.

Garnet runs an eBPF sensor (Jibril) inside CI jobs and posts a sticky
"Garnet Runtime Review" comment on the PR: every recorded outbound
connection made while the PR's code actually executed, keyed to the head
commit via an embedded `<!-- garnet:commit <sha> -->` marker. That gives
stamphog something no static reviewer has: kernel-recorded ground truth
about what a change *did* when it ran, not what its diff *looks like* it
would do.

This module mirrors migration_risk.py's shape: a deterministic CI signal,
bound to the head commit, interpreted conservatively, feeding a scoped
deny-list bypass plus a TRUSTED prompt block for the LLM reviewer.

Semantics (all fail toward "no bypass"):
    missing    → no Garnet comment for the current head; deny-list applies
                 normally and the reviewer is told no runtime evidence exists.
    pass       → evidence exists for the head commit and every recorded
                 destination matches the expected-egress policy. Scoped
                 bypass: a deps_toolchain-only deny may proceed to LLM
                 review (never auto-approve) with the evidence in-prompt.
    unexpected → evidence exists and at least one destination is NOT
                 expected. No bypass; the reviewer is instructed that this
                 is a showstopper unless the destination is clearly
                 explained by the PR's stated intent.

Trust model: only comments authored by the configured Garnet bot logins are
read, the commit marker must equal the PR head SHA (a stale comment from an
earlier push is ignored), and the expected-destination patterns live in
`.stamphog/runtime-evidence.yml` (trusted, human-reviewed via the
stamphog_policy deny which covers `.stamphog/**`).
"""

import re
import html
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

COMMENT_MARKER = "<!-- garnet-runtime-review -->"

_COMMIT_MARKER_RE = re.compile(r"<!--\s*garnet:commit\s+([0-9a-f]{40})\s*-->")
_DESTINATION_RE = re.compile(r"→\s*([^\s<][^<\n]*?)\s*(?:\(([^)]*)\))?\s*$")
_TAG_RE = re.compile(r"<(strong|em)>|</(strong|em)>")
_PERMALINK_RE = re.compile(r'href="(https://app\.garnet\.ai/public/runs/[^"]+)"')
_EXPLAINER_RE = re.compile(r"<details><summary>(?:<sub>)?💡 How to read this.*?</details>", re.DOTALL)

_CONFIG_FILENAME = "runtime-evidence.yml"


class RuntimeEvidenceError(Exception):
    """Malformed runtime-evidence config — fail closed, like PolicyError."""


@dataclass(frozen=True)
class RuntimeEvidenceConfig:
    trusted_bots: frozenset[str]
    expected_destinations: tuple[re.Pattern, ...]
    bypass_categories: frozenset[str]


@dataclass
class RuntimeEvidence:
    """Parsed evidence for the PR's current head commit."""

    status: str  # "missing" | "pass" | "unexpected"
    commit_sha: str = ""
    destinations: list[dict] = field(default_factory=list)  # {dest, note, lineage, expected}
    permalinks: list[str] = field(default_factory=list)

    @property
    def unexpected(self) -> list[dict]:
        return [d for d in self.destinations if not d["expected"]]


def load_config(stamphog_dir: Path) -> RuntimeEvidenceConfig | None:
    """Load `.stamphog/runtime-evidence.yml`; None when absent (feature off)."""
    path = stamphog_dir / _CONFIG_FILENAME
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeEvidenceError(f"could not read/parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeEvidenceError("runtime-evidence config root: must be a mapping")
    unknown = set(raw) - {"version", "trusted_bots", "expected_destinations", "bypass_categories"}
    if unknown:
        raise RuntimeEvidenceError(f"runtime-evidence config: unknown keys {sorted(unknown)}")
    if raw.get("version") != 1:
        raise RuntimeEvidenceError(f"runtime-evidence config: unsupported version {raw.get('version')!r}")
    bots = raw.get("trusted_bots") or []
    patterns = raw.get("expected_destinations") or []
    bypass = raw.get("bypass_categories") or []
    if not bots or not all(isinstance(b, str) for b in bots):
        raise RuntimeEvidenceError("runtime-evidence config: trusted_bots must be a non-empty string list")
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error as exc:
            raise RuntimeEvidenceError(f"runtime-evidence config: bad pattern {p!r}: {exc}") from exc
    if not all(isinstance(c, str) for c in bypass):
        raise RuntimeEvidenceError("runtime-evidence config: bypass_categories must be strings")
    return RuntimeEvidenceConfig(
        trusted_bots=frozenset(bots),
        expected_destinations=tuple(compiled),
        bypass_categories=frozenset(bypass),
    )


def fetch_runtime_evidence(repo: str, pr_number: int, head_sha: str, config: RuntimeEvidenceConfig) -> RuntimeEvidence:
    """Find the Garnet sticky comment on the PR and parse it for the head commit."""
    comments = _issue_comments(repo, pr_number)
    for comment in comments:
        login = (comment.get("user") or {}).get("login", "")
        body = comment.get("body") or ""
        if login not in config.trusted_bots or COMMENT_MARKER not in body:
            continue
        return parse_comment(body, head_sha, config)
    return RuntimeEvidence(status="missing")


def parse_comment(body: str, head_sha: str, config: RuntimeEvidenceConfig) -> RuntimeEvidence:
    """Parse the Garnet comment body; evidence counts only for the current head."""
    marker = _COMMIT_MARKER_RE.search(body)
    if marker is None or marker.group(1) != head_sha:
        return RuntimeEvidence(status="missing")

    destinations = _extract_destinations(body)
    permalinks = _PERMALINK_RE.findall(body)
    for d in destinations:
        d["expected"] = any(p.search(d["dest"]) for p in config.expected_destinations)
    status = "pass" if all(d["expected"] for d in destinations) else "unexpected"
    if not destinations:
        # A recorded run with zero destinations is still evidence (nothing egressed).
        status = "pass"
    return RuntimeEvidence(
        status=status,
        commit_sha=marker.group(1),
        destinations=destinations,
        permalinks=[html.unescape(p) for p in permalinks],
    )


def _refang(dest: str) -> str:
    """Undo the comment's hostname defanging (`github[.]com` → `github.com`)."""
    return dest.replace("[.]", ".")


def _extract_destinations(body: str) -> list[dict]:
    """Extract `→ destination` leaves plus the process lineage above each.

    Two evidence containers exist:
    - <pre> trees (snapshot jobs and substrate folds): process nodes wrapped
      in <em>/<strong>, destination leaves as `→ name` (optionally with a
      parenthesised note such as `(dns resolver)`).
    - ```diff fences (changed jobs in comparison comments): the same tree
      with a leading diff column — `+` (new), space (unchanged), `-` (no
      longer recorded; not current evidence).

    Lineage is reconstructed from tree indentation depth. Hostnames are
    defanged in the comment and refanged here so policy patterns match.

    Explainer exclusion: the current contract wraps its sample tree in the
    “How to read this” details fold, which is removed wholesale before
    parsing; older contracts root real trees at `<name> · job` (sample
    trees lack that root).
    """
    body = _EXPLAINER_RE.sub("", body)
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    pres = re.findall(r"<pre>(.*?)</pre>", body, flags=re.DOTALL)
    legacy_contract = any("· job" in pre for pre in pres)
    for pre in pres:
        if legacy_contract and "· job" not in pre:
            continue
        _walk_tree(pre.splitlines(), results, seen)
    for fence in re.findall(r"```diff\n(.*?)```", body, flags=re.DOTALL):
        lines = []
        for raw in fence.splitlines():
            if raw.startswith("@@") or raw.startswith("-"):
                continue
            lines.append(raw[1:] if raw[:1] in "+ " else raw)
        _walk_tree(lines, results, seen)
    return results


def _walk_tree(lines: list[str], results: list[dict], seen: set[tuple[str, str]]) -> None:
    stack: list[tuple[int, str]] = []  # (depth, process name)
    for line in lines:
        depth = _tree_depth(line)
        text = _TAG_RE.sub("", line)
        text = re.sub(r"^[\s│├└─]+", "", text).strip()
        if not text:
            continue
        dest_match = _DESTINATION_RE.search(text)
        if text.startswith("→") and dest_match:
            dest = _refang(html.unescape(dest_match.group(1)).strip())
            note = (dest_match.group(2) or "").strip()
            lineage = " > ".join(name for d, name in stack if d < depth)
            key = (dest, lineage)
            if key not in seen:
                seen.add(key)
                results.append({"dest": dest, "note": note, "lineage": lineage, "expected": False})
        else:
            name = html.unescape(re.sub(r"\s*·\s*job$", "", text)).strip()
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, name))


def _tree_depth(line: str) -> int:
    """Indentation depth of a rendered tree line (3 columns per level)."""
    stripped = _TAG_RE.sub("", line)
    prefix_len = len(stripped) - len(stripped.lstrip(" │├└─"))
    return prefix_len // 3


def bypassable_deny(deny: list[str], evidence: RuntimeEvidence, config: RuntimeEvidenceConfig) -> list[str]:
    """Return deny categories cleared by passing runtime evidence.

    Conservative on purpose: only configured categories (deps_toolchain by
    default) are ever bypassable, only when the evidence status is `pass`
    for the current head, and only when *every* deny category on the PR is
    bypassable — a PR that also trips auth or crypto_secrets keeps its full
    deny even with clean runtime evidence. Like the migration-risk bypass,
    this never auto-approves: the PR still gets full LLM review with the
    evidence in the prompt.
    """
    if evidence.status != "pass":
        return []
    if not deny or not set(deny) <= config.bypass_categories:
        return []
    return list(deny)


def prompt_block(evidence: RuntimeEvidence) -> str:
    """Render the TRUSTED prompt block describing the runtime evidence."""
    if evidence.status == "missing":
        return (
            "Runtime evidence (Garnet): none recorded for the current head commit. "
            "Judge the PR without runtime evidence; do not assume execution was clean."
        )
    lines = [
        f"Runtime evidence (Garnet, TRUSTED — kernel-recorded egress while this PR's code ran in CI, head {evidence.commit_sha[:7]}):"
    ]
    for d in evidence.destinations:
        flag = "expected" if d["expected"] else "UNEXPECTED"
        note = f" ({d['note']})" if d["note"] else ""
        lineage = f" via {d['lineage']}" if d["lineage"] else ""
        lines.append(f"  - [{flag}] {d['dest']}{note}{lineage}")
    if not evidence.destinations:
        lines.append("  - no outbound destinations recorded")
    if evidence.status == "unexpected":
        lines.append(
            "  Verdict guidance: at least one destination is outside the expected-egress policy. "
            "Unless the PR's stated intent clearly explains that exact destination, this is a "
            "showstopper — REFUSE and name the destination and its process lineage."
        )
    else:
        lines.append(
            "  Verdict guidance: all recorded egress matches the expected-egress policy. For "
            "dependency/toolchain risky territory, this counts as independent assurance over "
            "runtime behavior (it does not vouch for logic correctness)."
        )
    for link in evidence.permalinks[:3]:
        lines.append(f"  Evidence permalink: {link}")
    return "\n".join(lines)


def citation_block(evidence: RuntimeEvidence) -> str | None:
    """Verifiable Markdown citation for the posted verdict comment.

    Whenever runtime evidence existed for the reviewed head, the verdict
    comment carries the exact commit binding, every destination outside the
    expected-egress policy (with its process lineage), and the Garnet public
    run permalinks — so anyone can independently verify the kernel-recorded
    egress the verdict relied on, without re-running anything.
    """
    if evidence.status == "missing":
        return None
    lines = [
        "<details>",
        f"<summary>Runtime evidence (Garnet) — kernel-recorded CI egress for head <code>{evidence.commit_sha[:7]}</code></summary>",
        "",
        f"Status: **{evidence.status}** ({len(evidence.destinations)} recorded destination(s)).",
    ]
    unexpected = evidence.unexpected
    if unexpected:
        lines.append("")
        lines.append("Destinations outside the expected-egress policy (`.stamphog/runtime-evidence.yml`):")
        for d in unexpected:
            note = f" ({d['note']})" if d["note"] else ""
            lineage = f" — process lineage: `{d['lineage']}`" if d["lineage"] else ""
            lines.append(f"- `{d['dest']}`{note}{lineage}")
    elif not evidence.destinations:
        lines.append("No outbound destinations were recorded while this PR's code ran.")
    else:
        lines.append("Every recorded destination matches the expected-egress policy.")
    lines.append("")
    lines.append("Verify independently:")
    for link in evidence.permalinks[:3]:
        lines.append(f"- [Garnet run profile]({link})")
    lines.append(
        "- The `Garnet Runtime Review` comment on this PR "
        f"(its embedded commit marker must equal `{evidence.commit_sha[:7]}`)."
    )
    lines += ["", "</details>"]
    return "\n".join(lines)


def evidence_dict(evidence: RuntimeEvidence | None) -> dict | None:
    """Full evidence for the machine-readable review bundle."""
    if evidence is None:
        return None
    return {
        "status": evidence.status,
        "commit_sha": evidence.commit_sha,
        "destinations": evidence.destinations,
        "permalinks": evidence.permalinks,
    }


def _issue_comments(repo: str, pr_number: int) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{pr_number}/comments", "--paginate"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)
