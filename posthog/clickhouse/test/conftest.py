"""Pytest conftest — loads stubs before test modules are imported."""

from __future__ import annotations

import os
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import posthog.clickhouse.test._stubs as _stubs  # noqa: F401, E402
