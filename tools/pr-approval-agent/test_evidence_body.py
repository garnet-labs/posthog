"""Tests for evidence_body.py, the PR-description evidence-block sync."""

from evidence_body import BEGIN_MARKER, END_MARKER, evidence_block, upsert_block
from runtime_evidence import RuntimeEvidence, parse_comment
from test_runtime_evidence import COMMENT, HEAD, V66_COMMENT


def test_recorded_block_lists_every_chain():
    evidence = parse_comment(COMMENT, HEAD)
    block = evidence_block(evidence, HEAD)
    assert block.startswith(BEGIN_MARKER)
    assert block.endswith(END_MARKER)
    assert f"head `{HEAD[:7]}`" in block
    assert "status: **recorded**" in block
    for d in evidence.destinations:
        assert f"`{d['dest']}`" in block
    assert "NEW chain" not in block


def test_diverged_block_marks_new_chains():
    evidence = parse_comment(V66_COMMENT, HEAD)
    assert evidence.status == "diverged"
    block = evidence_block(evidence, HEAD)
    assert "status: **diverged**" in block
    assert "**NEW chain**" in block
    assert "must be explained by this diff" in block


def test_missing_block_fails_closed():
    block = evidence_block(RuntimeEvidence(status="missing"), HEAD)
    assert "No usable runtime evidence" in block
    assert f"`{HEAD[:7]}`" in block
    assert "Do not assume execution was clean" in block


def test_upsert_appends_when_no_markers():
    body = "Original description."
    block = evidence_block(RuntimeEvidence(status="missing"), HEAD)
    merged = upsert_block(body, block)
    assert merged.startswith("Original description.")
    assert merged.count(BEGIN_MARKER) == 1


def test_upsert_replaces_existing_block_in_place():
    old = f"Intro.\n\n{BEGIN_MARKER}\nstale evidence\n{END_MARKER}\n\nOutro."
    block = evidence_block(parse_comment(COMMENT, HEAD), HEAD)
    merged = upsert_block(old, block)
    assert "stale evidence" not in merged
    assert merged.count(BEGIN_MARKER) == 1
    assert merged.startswith("Intro.")
    assert merged.rstrip().endswith("Outro.")


def test_upsert_is_idempotent():
    block = evidence_block(parse_comment(COMMENT, HEAD), HEAD)
    once = upsert_block("Body.", block)
    assert upsert_block(once, block) == once
