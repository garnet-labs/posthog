"""Tests for evidence_status.py, the garnet/runtime-evidence commit-status mirror."""

import re

import evidence_status
from evidence_status import status_payload
from runtime_evidence import RuntimeEvidence, RuntimeEvidenceConfig, parse_comment
from test_runtime_evidence import ALLOW_ALL, COMMENT, HEAD


def _config(patterns: list[str]) -> RuntimeEvidenceConfig:
    return RuntimeEvidenceConfig(
        trusted_bots=frozenset({"garnet-runtime-review[bot]"}),
        expected_destinations=tuple(re.compile(p) for p in patterns),
        bypass_categories=frozenset({"deps_toolchain"}),
    )


def test_pass_maps_to_success():
    evidence = parse_comment(COMMENT, HEAD, _config(ALLOW_ALL))
    assert evidence.status == "pass"
    state, description = status_payload(evidence)
    assert state == "success"
    assert description == "pass: 3 recorded destination(s), all expected"


def test_unexpected_maps_to_failure_naming_destinations():
    evidence = parse_comment(COMMENT, HEAD, _config([r"^localhost$"]))
    assert evidence.status == "unexpected"
    state, description = status_payload(evidence)
    assert state == "failure"
    assert description == "1 unexpected destination(s): registry.npmjs.org"


def test_missing_maps_to_pending():
    for evidence in (
        RuntimeEvidence(status="missing"),
        # Stale comment: marker for an older head.
        parse_comment(COMMENT, "0" * 40, _config(ALLOW_ALL)),
        # Head-pinned waiting-state comment with zero parseable destinations.
        parse_comment(
            f"<!-- garnet-runtime-review -->\n<!-- garnet:commit {HEAD} -->\nstill recording",
            HEAD,
            _config(ALLOW_ALL),
        ),
    ):
        assert evidence.status == "missing"
        state, description = status_payload(evidence)
        assert state == "pending"
        assert "fail-closed" in description


def test_main_posts_status_from_live_shapes(monkeypatch, capsys):
    posted = {}

    def fake_gh_json(args):
        endpoint = args[0]
        if endpoint.endswith("/pulls/65"):
            return {"head": {"sha": HEAD}, "html_url": "https://github.com/o/r/pull/65"}
        posted["args"] = args
        return {}

    monkeypatch.setattr(evidence_status, "_gh_json", fake_gh_json)
    monkeypatch.setattr(
        evidence_status,
        "fetch_runtime_evidence",
        lambda repo, pr, head, config: parse_comment(COMMENT, head, _config(ALLOW_ALL)),
    )
    monkeypatch.setattr("sys.argv", ["evidence_status.py", "65", "--repo", "o/r"])

    assert evidence_status.main() == 0
    assert posted["args"][0] == f"repos/o/r/statuses/{HEAD}"
    values = posted["args"][2::2]
    assert "state=success" in values
    assert "context=garnet/runtime-evidence" in values
    assert any(v.startswith("description=pass: 3 recorded") for v in values)
    assert any(v.startswith("target_url=https://app.garnet.ai/public/runs/") for v in values)
    assert "success" in capsys.readouterr().out


def test_main_without_config_posts_nothing(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(evidence_status, "_gh_json", lambda args: calls.append(args))
    monkeypatch.setattr(evidence_status, "load_config", lambda _p: None)
    monkeypatch.setattr("sys.argv", ["evidence_status.py", "65", "--repo", "o/r"])

    assert evidence_status.main() == 0
    assert calls == []
    assert "not posting" in capsys.readouterr().out


def test_posted_description_fits_github_status_limit(monkeypatch):
    # GitHub rejects status descriptions over 140 chars; main() must slice
    # before posting. Worst realistic case: several long unexpected hostnames.
    posted = {}

    def fake_gh_json(args):
        if args[0].endswith("/pulls/65"):
            return {"head": {"sha": HEAD}, "html_url": "https://github.com/o/r/pull/65"}
        posted["args"] = args
        return {}

    long = [{"dest": "a" * 60 + f"{i}.evil.example", "note": "", "lineage": [], "expected": False} for i in range(5)]
    evidence = RuntimeEvidence(status="unexpected", commit_sha=HEAD, destinations=long)
    assert len(status_payload(evidence)[1]) > 140

    monkeypatch.setattr(evidence_status, "_gh_json", fake_gh_json)
    monkeypatch.setattr(evidence_status, "fetch_runtime_evidence", lambda *a: evidence)
    monkeypatch.setattr("sys.argv", ["evidence_status.py", "65", "--repo", "o/r"])

    assert evidence_status.main() == 0
    (description,) = [v for v in posted["args"][2::2] if v.startswith("description=")]
    assert len(description.removeprefix("description=")) <= 140
