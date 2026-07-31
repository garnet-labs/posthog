"""Tests for runtime_evidence.py — Garnet comment parsing and bypass scoping."""

import re

import pytest

from runtime_evidence import (
    RuntimeEvidence,
    RuntimeEvidenceConfig,
    RuntimeEvidenceError,
    bypassable_deny,
    citation_block,
    evidence_dict,
    load_config,
    parse_comment,
    prompt_block,
)

HEAD = "6e5d0d4cf00a92a9e1fe697efe0e41b3ae61533e"

# Trimmed from a real control-plane githubapp golden (contract v6.4).
COMMENT = f"""<!-- garnet-runtime-review -->
<!-- garnet-run-profile -->
<!-- garnet:commit {HEAD} -->
**See what ran** — every outbound connection and its process lineage.

<details><summary><code>ci</code> / <a href="https://github.com/o/r/actions/runs/1"><code>install</code> ↗</a></summary>

<pre>
<em>install · job</em>
└─ <em>systemd</em>
   └─ <em>hosted-compute-agent</em>
      ├─ <em>Runner.Listener</em>
      │  └─ <em>Runner.Worker</em>
      │     └─ <strong>bash</strong>
      │        └─ <strong>node</strong>
      │           ├─ → registry.npmjs.org
      │           └─ → localhost (dns resolver)
      └─ <em>sudo</em>
         └─ <strong>provjobd920019609</strong>
            └─ → localhost (dns resolver)
</pre>

<p align="right"><sub><a href="https://app.garnet.ai/public/runs/1?profile=abc&amp;utm_source=github&amp;utm_medium=pr_comment">View Run Profile in Garnet ↗</a></sub></p>

</details>
"""


def _config(patterns: list[str] | None = None) -> RuntimeEvidenceConfig:
    return RuntimeEvidenceConfig(
        trusted_bots=frozenset({"garnet-runtime-review[bot]"}),
        expected_destinations=tuple(re.compile(p) for p in (patterns or [])),
        bypass_categories=frozenset({"deps_toolchain"}),
    )


ALLOW_ALL = [r"^registry\.npmjs\.org$", r"^localhost$"]


def test_parse_extracts_destinations_and_lineage():
    ev = parse_comment(COMMENT, HEAD, _config(ALLOW_ALL))
    dests = {d["dest"] for d in ev.destinations}
    assert dests == {"registry.npmjs.org", "localhost"}
    npm = next(d for d in ev.destinations if d["dest"] == "registry.npmjs.org")
    assert npm["lineage"].endswith("bash > node")
    resolver = next(d for d in ev.destinations if d["dest"] == "localhost" and "node" in d["lineage"])
    assert resolver["note"] == "dns resolver"
    assert ev.permalinks == ["https://app.garnet.ai/public/runs/1?profile=abc&utm_source=github&utm_medium=pr_comment"]


def test_all_expected_is_pass():
    ev = parse_comment(COMMENT, HEAD, _config(ALLOW_ALL))
    assert ev.status == "pass"
    assert ev.unexpected == []


def test_unexpected_destination_flagged():
    ev = parse_comment(COMMENT, HEAD, _config([r"^localhost$"]))
    assert ev.status == "unexpected"
    assert [d["dest"] for d in ev.unexpected] == ["registry.npmjs.org"]


def test_stale_commit_marker_is_missing():
    ev = parse_comment(COMMENT, "f" * 40, _config(ALLOW_ALL))
    assert ev.status == "missing"


def test_no_commit_marker_is_missing():
    body = COMMENT.replace(f"<!-- garnet:commit {HEAD} -->", "")
    assert parse_comment(body, HEAD, _config(ALLOW_ALL)).status == "missing"


def test_zero_destinations_is_missing():
    # Waiting-state comment, or a renderer format this parser can't read:
    # unusable evidence must never clear a deny.
    body = f"<!-- garnet-runtime-review -->\n<!-- garnet:commit {HEAD} -->\nno record"
    ev = parse_comment(body, HEAD, _config([]))
    assert ev.status == "missing"
    assert ev.destinations == []
    assert bypassable_deny(["deps_toolchain"], ev, _config([])) == []


# Trimmed from the contract v6.6 goldens: no "· job" tree roots, defanged
# destination names, "How to read this" explainer fold with a sample tree.
COMMENT_V66 = f"""<!-- garnet-runtime-review -->
<!-- garnet-run-profile -->
<!-- garnet:commit {HEAD} -->
**Execution Profiles recorded for 1 job, triggered by [`{HEAD[:7]}`](https://github.com/o/r/commit/{HEAD})**

> *5&nbsp;execution chains · 2&nbsp;destinations · recorded at the kernel by Garnet*

<details><summary><code>ci</code> / <a href="https://github.com/o/r/actions/runs/2"><code>install</code>&nbsp;↗</a></summary>

<pre>
<em>Runner.Worker</em>
└─ <strong>bash</strong>
   └─ <strong>node</strong>
      ├─ → registry.npmjs[.]org
      └─ → localhost (dns resolver)
</pre>

<p align="right"><sub><a href="https://app.garnet.ai/public/runs/2?profile=def&amp;utm_source=github&amp;utm_medium=pr_comment">View this job's Execution Profile in Garnet →</a></sub></p>

</details>

---

<details open><summary><sub>💡 How to read this</sub></summary>

<pre>
<em>Runner.Worker</em>                ← runner (italic)
└─ <strong>npm install</strong>               ← your workflow step (bold)
   └─ → sample-domain[.]example  ← outbound connection, defanged
</pre>

</details>
"""


def test_v66_comment_parses_with_defang_normalized():
    ev = parse_comment(COMMENT_V66, HEAD, _config(ALLOW_ALL))
    dests = {d["dest"] for d in ev.destinations}
    assert dests == {"registry.npmjs.org", "localhost"}
    assert ev.status == "pass"
    npm = next(d for d in ev.destinations if d["dest"] == "registry.npmjs.org")
    assert npm["lineage"].endswith("bash > node")


def test_v66_explainer_sample_tree_ignored():
    ev = parse_comment(COMMENT_V66, HEAD, _config(ALLOW_ALL))
    assert "sample-domain.example" not in {d["dest"] for d in ev.destinations}


def test_bypass_only_configured_categories():
    ev = parse_comment(COMMENT, HEAD, _config(ALLOW_ALL))
    cfg = _config(ALLOW_ALL)
    assert bypassable_deny(["deps_toolchain"], ev, cfg) == ["deps_toolchain"]
    # A PR that also trips auth keeps its full deny.
    assert bypassable_deny(["auth", "deps_toolchain"], ev, cfg) == []
    assert bypassable_deny([], ev, cfg) == []


def test_no_bypass_on_unexpected_or_missing():
    cfg = _config([r"^localhost$"])
    unexpected = parse_comment(COMMENT, HEAD, cfg)
    assert bypassable_deny(["deps_toolchain"], unexpected, cfg) == []
    missing = RuntimeEvidence(status="missing")
    assert bypassable_deny(["deps_toolchain"], missing, cfg) == []


def test_prompt_block_names_unexpected():
    ev = parse_comment(COMMENT, HEAD, _config([r"^localhost$"]))
    block = prompt_block(ev)
    assert "[UNEXPECTED] registry.npmjs.org" in block
    assert "REFUSE" in block
    assert "Evidence permalink: https://app.garnet.ai/public/runs/1" in block


def test_explainer_sample_tree_ignored():
    explainer = (
        "<details><summary><sub>💡 Reading this review</sub></summary>\n<pre>\n"
        "<em>Runner.Worker</em>\n└─ <strong>bash</strong>\n   └─ <strong>curl</strong>\n"
        "      └─ → evil-example.com\n</pre>\n</details>\n"
    )
    body = COMMENT.replace("**See what ran**", explainer + "**See what ran**")
    ev = parse_comment(body, HEAD, _config(ALLOW_ALL))
    assert "evil-example.com" not in {d["dest"] for d in ev.destinations}
    assert ev.status == "pass"


def test_citation_block_cites_verifiable_evidence():
    ev = parse_comment(COMMENT, HEAD, _config([r"^localhost$"]))
    block = citation_block(ev)
    assert f"<code>{HEAD[:7]}</code>" in block
    assert "**unexpected**" in block
    assert "`registry.npmjs.org`" in block
    assert "process lineage" in block
    assert "https://app.garnet.ai/public/runs/1" in block
    assert f"must equal `{HEAD[:7]}`" in block


def test_citation_block_pass_and_missing():
    ev = parse_comment(COMMENT, HEAD, _config(ALLOW_ALL))
    block = citation_block(ev)
    assert "**pass**" in block
    assert "matches the expected-egress policy" in block
    assert citation_block(RuntimeEvidence(status="missing")) is None


def test_evidence_dict_round_trip():
    ev = parse_comment(COMMENT, HEAD, _config(ALLOW_ALL))
    d = evidence_dict(ev)
    assert d["status"] == "pass"
    assert d["commit_sha"] == HEAD
    assert d["destinations"] == ev.destinations
    assert d["permalinks"] == ev.permalinks
    assert evidence_dict(None) is None


def test_prompt_block_missing():
    assert "none recorded" in prompt_block(RuntimeEvidence(status="missing"))


def test_load_config_validates(tmp_path):
    (tmp_path / "runtime-evidence.yml").write_text("version: 1\ntrusted_bots: [x]\nnope: 1\n")
    with pytest.raises(RuntimeEvidenceError):
        load_config(tmp_path)
    assert load_config(tmp_path.parent / "absent") is None
    (tmp_path / "runtime-evidence.yml").write_text(
        "version: 1\ntrusted_bots: ['garnet[bot]']\nexpected_destinations: ['^a$']\nbypass_categories: [deps_toolchain]\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.trusted_bots == frozenset({"garnet[bot]"})
    assert cfg.bypass_categories == frozenset({"deps_toolchain"})
