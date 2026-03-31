"""Proof-only Django settings that inherit from posthog.settings.

Keeps PostHog's full INSTALLED_APPS to avoid circular import issues,
but sets flags that prevent database-dependent initialization during
app startup.
"""

import os

# Ensure defaults that prevent side effects during import
os.environ.setdefault("SECRET_KEY", "standalone-proof-key")
os.environ.setdefault("DEBUG", "1")
os.environ.setdefault("DATABASE_URL", "postgres://localhost:5432/posthog")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("CLICKHOUSE_HOST", "localhost")
os.environ.setdefault("CLICKHOUSE_DATABASE", "posthog")
os.environ.setdefault("CLICKHOUSE_CLUSTER", "posthog")
os.environ["SKIP_ASYNC_MIGRATIONS_SETUP"] = "1"

# This flag tells PostHog's app config to skip DB-dependent ready() work
os.environ["POSTHOG_PROOF_MODE"] = "1"

# Import everything from the real settings
from posthog.settings import *  # noqa: F401,F403

# Force test mode to avoid cloud-deployment routing
TEST = True
E2E_TESTING = False
