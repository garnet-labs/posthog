# Service hostname consolidation

All local dev services (Postgres, Redis, ClickHouse, Kafka, etc.) now use Docker service names (`db`, `redis7`, `clickhouse`, `kafka`, `objectstorage`, `temporal`) as defaults everywhere — Django settings, `bin/start`, `bin/start-rust-service`. These resolve via `/etc/hosts` on the host and Docker DNS in containers. Same names, both contexts, zero overrides needed.

**Changes:**

- **Django settings**: defaults changed from `localhost` → service names (gated on `DEBUG`)
- **`bin/start`**: exports service names for Node.js/Rust vars that have `localhost` defaults in their own configs (`CDP_REDIS_HOST`, `TEMPORAL_HOST`, `PERSONS_DATABASE_URL`, etc.)
- **`bin/start-rust-service`**: defaults changed from `localhost` → service names
- **`dev-services.env`**: new shared env file for credentials and connection strings, referenced by both `docker-compose.base.yml` and `docker-compose.sandbox.yml`
- **Flox `/etc/hosts`**: now includes all service names (`db`, `redis7`, `seaweedfs`, `temporal`)
- **Sandbox compose**: added `seaweedfs` to match dev stack

**Result:** Sandbox env vars went from ~55 to 9 — only sandbox-specific settings remain (identity, session cookies, debug flags). Everything else comes from shared defaults.
