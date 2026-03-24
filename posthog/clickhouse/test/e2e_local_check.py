# ruff: noqa: T201,E402 — standalone test script uses print() and deferred imports
"""E2E local test for the new ClickHouse migration system.

Tests core library functions without requiring Django or Docker.
We bypass posthog/__init__.py entirely by pre-populating sys.modules
with a fake posthog package, then let real subpackages load normally.
"""

import os
import sys
import types

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Strategy: create a real-ish posthog package in sys.modules that has __path__
# set correctly, so subpackage imports (posthog.clickhouse...) work, but skip
# executing posthog/__init__.py (which drags in celery -> django -> world).
# ---------------------------------------------------------------------------

_posthog_pkg = types.ModuleType("posthog")
_posthog_pkg.__path__ = [os.path.join(PROJECT_ROOT, "posthog")]
_posthog_pkg.__package__ = "posthog"
_posthog_pkg.celery_app = None
sys.modules["posthog"] = _posthog_pkg


# Also pre-populate posthog.celery so nothing tries to import it
_posthog_celery = types.ModuleType("posthog.celery")
_posthog_celery.app = None
sys.modules["posthog.celery"] = _posthog_celery

# Fake django.conf.settings for NewStyleMigration._get_template_variables()
_django = types.ModuleType("django")
_django_conf = types.ModuleType("django.conf")


class _FakeSettings:
    CLICKHOUSE_DATABASE = "posthog"
    CLICKHOUSE_CLUSTER = "posthog"
    CLICKHOUSE_SINGLE_SHARD_CLUSTER = ""


_django_conf.settings = _FakeSettings()
_django.conf = _django_conf
sys.modules["django"] = _django
sys.modules["django.conf"] = _django_conf

# ---------------------------------------------------------------------------
# Now the real imports -- these modules have no heavyweight dependencies
# ---------------------------------------------------------------------------
from pathlib import Path

from posthog.clickhouse.migrations.jinja_env import render_sql
from posthog.clickhouse.migrations.manifest import parse_manifest
from posthog.clickhouse.migrations.new_style import NewStyleMigration
from posthog.clickhouse.migrations.runner import _ROLE_MAP, compute_checksum, discover_migrations
from posthog.clickhouse.migrations.sql_parser import parse_sql_sections
from posthog.clickhouse.migrations.tracking import get_tracking_ddl
from posthog.clickhouse.migrations.validator import validate_migration

# --------------------------------------------------------------------------
# Test 1: Parse the test migration manifest
# --------------------------------------------------------------------------
manifest = parse_manifest(Path("posthog/clickhouse/migrations/0222_test_new_migration_system/manifest.yaml"))
print(f"PASS  Test 1 - Manifest parsed: {manifest.description}")
print(f"       Steps: {len(manifest.steps)}, Rollback: {len(manifest.rollback)}")
assert len(manifest.steps) == 1
assert len(manifest.rollback) == 1

# --------------------------------------------------------------------------
# Test 2: Parse SQL sections
# --------------------------------------------------------------------------
up_sql = Path("posthog/clickhouse/migrations/0222_test_new_migration_system/up.sql").read_text()
sections = parse_sql_sections(up_sql)
print(f"PASS  Test 2 - SQL parsed: {len(sections)} section(s)")

# --------------------------------------------------------------------------
# Test 3: Render Jinja2 template
# --------------------------------------------------------------------------
rendered = render_sql("SELECT * FROM {{ database }}.events", {"database": "posthog"})
assert rendered == "SELECT * FROM posthog.events"
print(f"PASS  Test 3 - Jinja2 rendered: {rendered}")

# --------------------------------------------------------------------------
# Test 4: Jinja2 blocks rejected
# --------------------------------------------------------------------------
try:
    render_sql("{% for i in range(10) %}x{% endfor %}", {})
    print("FAIL  Test 4 - Should have rejected block tag")
    sys.exit(1)
except ValueError as e:
    print(f"PASS  Test 4 - Jinja2 block rejected: {e}")

# --------------------------------------------------------------------------
# Test 5: Validate the test migration
# --------------------------------------------------------------------------
results = validate_migration(Path("posthog/clickhouse/migrations/0222_test_new_migration_system"))
# The down.sql contains DROP TABLE which triggers a warning (not error) -- that's expected
errors = [r for r in results if r.severity == "error"]
warnings = [r for r in results if r.severity == "warning"]
if errors:
    print(f"FAIL  Test 5 - Validation errors: {[r.message for r in errors]}")
    sys.exit(1)
elif warnings:
    print(f"PASS  Test 5 - Test migration validates (warnings only, as expected for DROP in down.sql):")
    for w in warnings:
        print(f"       [{w.rule}] {w.message}")
else:
    print("PASS  Test 5 - Test migration validates clean")

# --------------------------------------------------------------------------
# Test 6: Discover migrations
# --------------------------------------------------------------------------
migrations = discover_migrations()
new_style_list = [m for m in migrations if m.get("style") == "new"]
print(f"PASS  Test 6 - Discovered {len(migrations)} total migrations, {len(new_style_list)} new-style")
assert len(new_style_list) >= 1, "Expected at least 1 new-style migration"

# --------------------------------------------------------------------------
# Test 7: Compute checksum
# --------------------------------------------------------------------------
checksum = compute_checksum("SELECT 1")
assert len(checksum) == 64  # SHA256 hex digest
print(f"PASS  Test 7 - Checksum: {checksum[:16]}...")

# --------------------------------------------------------------------------
# Test 8: Tracking table DDL
# --------------------------------------------------------------------------
ddl = get_tracking_ddl("posthog")
assert "MergeTree()" in ddl
assert "ReplicatedMergeTree" not in ddl
print("PASS  Test 8 - Tracking table uses local MergeTree (no ZK dependency)")

# --------------------------------------------------------------------------
# Test 9: NewStyleMigration
# --------------------------------------------------------------------------
migration = NewStyleMigration(Path("posthog/clickhouse/migrations/0222_test_new_migration_system"))
steps = migration.get_steps()
print(f"PASS  Test 9 - NewStyleMigration: {len(steps)} step(s)")
for step, sql in steps:
    print(f"       Step: {step.comment} -> {step.node_roles}")
    print(f"       SQL: {sql[:60]}...")
assert len(steps) == 1

rollback_steps = migration.get_rollback_steps()
assert len(rollback_steps) == 1
print(f"       Rollback: {len(rollback_steps)} step(s)")

# --------------------------------------------------------------------------
# Test 10: Role mapping
# --------------------------------------------------------------------------
print(f"PASS  Test 10 - Role mapping: {list(_ROLE_MAP.keys())}")
assert "DATA" in _ROLE_MAP
assert "COORDINATOR" in _ROLE_MAP
assert "ALL" in _ROLE_MAP

print("\n=== ALL E2E TESTS PASSED ===")
