"""Validation rule tests for the new ClickHouse migration system.

Tests each validation rule against crafted bad migrations.
No Django or Docker required.
"""

import os
import sys
import tempfile
import types

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# Bypass posthog/__init__.py
_posthog_pkg = types.ModuleType("posthog")
_posthog_pkg.__path__ = [os.path.join(PROJECT_ROOT, "posthog")]
_posthog_pkg.__package__ = "posthog"
sys.modules["posthog"] = _posthog_pkg

_posthog_celery = types.ModuleType("posthog.celery")
_posthog_celery.app = None
sys.modules["posthog.celery"] = _posthog_celery

import yaml
from pathlib import Path

from posthog.clickhouse.migrations.validator import validate_migration


def make_migration(tmpdir, manifest_data, up_sql, down_sql=""):
    mdir = Path(tmpdir) / "test_migration"
    mdir.mkdir(exist_ok=True)
    (mdir / "manifest.yaml").write_text(yaml.dump(manifest_data))
    (mdir / "up.sql").write_text(up_sql)
    (mdir / "down.sql").write_text(down_sql)
    return mdir


# --------------------------------------------------------------------------
# Test: ON CLUSTER detected
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
            "rollback": [{"sql": "down.sql", "node_roles": ["DATA"]}],
        },
        "ALTER TABLE foo ON CLUSTER posthog ADD COLUMN bar UInt64",
        "SELECT 1",
    )
    results = validate_migration(mdir)
    on_cluster = [r for r in results if "ON CLUSTER" in r.message]
    if on_cluster:
        print(f"PASS  ON CLUSTER detected: {on_cluster[0].message}")
    else:
        print(f"FAIL  ON CLUSTER not detected. Results: {[(r.rule, r.message) for r in results]}")
        sys.exit(1)

# --------------------------------------------------------------------------
# Test: Missing rollback
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test",
            "steps": [
                {"sql": "up.sql", "node_roles": ["DATA"]},
                {"sql": "up.sql", "node_roles": ["DATA"]},
            ],
            "rollback": [{"sql": "down.sql", "node_roles": ["DATA"]}],
        },
        "SELECT 1",
        "SELECT 1",
    )
    results = validate_migration(mdir)
    rollback_issues = [r for r in results if "rollback" in r.message.lower() or "rollback" in r.rule.lower()]
    if rollback_issues:
        print(f"PASS  Missing rollback detected: {rollback_issues[0].message}")
    else:
        print(f"FAIL  Missing rollback not detected. Results: {[(r.rule, r.message) for r in results]}")
        sys.exit(1)

# --------------------------------------------------------------------------
# Test: DROP warning
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
            "rollback": [{"sql": "down.sql", "node_roles": ["DATA"]}],
        },
        "DROP TABLE IF EXISTS foo",
        "SELECT 1",
    )
    results = validate_migration(mdir)
    drop_issues = [r for r in results if "drop" in r.message.lower() or "drop" in r.rule.lower()]
    if drop_issues:
        print(f"PASS  DROP detected: {drop_issues[0].message} (severity: {drop_issues[0].severity})")
    else:
        print(f"FAIL  DROP not detected. Results: {[(r.rule, r.message) for r in results]}")
        sys.exit(1)

# --------------------------------------------------------------------------
# Test: DROP in strict mode is error
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
            "rollback": [{"sql": "down.sql", "node_roles": ["DATA"]}],
        },
        "DROP TABLE IF EXISTS foo",
        "SELECT 1",
    )
    results = validate_migration(mdir, strict=True)
    drop_errors = [r for r in results if "drop" in r.rule.lower() and r.severity == "error"]
    if drop_errors:
        print(f"PASS  DROP in strict mode is error: {drop_errors[0].severity}")
    else:
        print(f"FAIL  DROP in strict mode not error. Results: {[(r.rule, r.severity, r.message) for r in results]}")
        sys.exit(1)

# --------------------------------------------------------------------------
# Test: DROP in SQL comment is ignored
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
            "rollback": [{"sql": "down.sql", "node_roles": ["DATA"]}],
        },
        "-- DROP TABLE foo\nSELECT 1",
        "SELECT 1",
    )
    results = validate_migration(mdir)
    drop_issues = [r for r in results if "drop" in r.rule.lower()]
    if not drop_issues:
        print("PASS  DROP in SQL comment is correctly ignored")
    else:
        print(f"FAIL  DROP in comment was flagged: {[(r.rule, r.message) for r in results]}")
        sys.exit(1)

# --------------------------------------------------------------------------
# Test: Node role consistency (sharded on COORDINATOR)
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test",
            "steps": [{"sql": "up.sql", "node_roles": ["COORDINATOR"], "sharded": True}],
            "rollback": [{"sql": "down.sql", "node_roles": ["COORDINATOR"]}],
        },
        "SELECT 1",
        "SELECT 1",
    )
    results = validate_migration(mdir)
    role_issues = [r for r in results if "node_role" in r.rule.lower() or "sharded" in r.message.lower()]
    if role_issues:
        print(f"PASS  Node role consistency detected: {role_issues[0].message}")
    else:
        print(f"FAIL  Node role consistency not detected. Results: {[(r.rule, r.message) for r in results]}")
        sys.exit(1)

# --------------------------------------------------------------------------
# Test: Clean migration passes validation
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    mdir = make_migration(
        tmp,
        {
            "description": "test clean",
            "steps": [{"sql": "up.sql", "node_roles": ["DATA"]}],
            "rollback": [{"sql": "down.sql", "node_roles": ["DATA"]}],
        },
        "ALTER TABLE foo ADD COLUMN bar UInt64",
        "ALTER TABLE foo DROP COLUMN bar",
    )
    results = validate_migration(mdir)
    # DROP in down.sql is expected as a warning, but no errors
    errors = [r for r in results if r.severity == "error"]
    if not errors:
        print("PASS  Clean migration passes validation (no errors)")
    else:
        print(f"FAIL  Clean migration has errors: {[(r.rule, r.message) for r in errors]}")
        sys.exit(1)

print("\n=== ALL VALIDATION TESTS PASSED ===")
