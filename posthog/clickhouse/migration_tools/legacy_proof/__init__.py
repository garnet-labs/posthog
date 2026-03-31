# Legacy-to-declarative migration proof system.
#
# This package generates declarative proof artifacts from legacy .py ClickHouse
# migrations and provides tooling to compare, replay, and validate the generated
# output against the legacy migration path.
#
# Generated artifacts live outside the active migration discovery path and are
# NOT used for production migration execution.
