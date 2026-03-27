# Sandbox follow-up tasks

Prioritized by impact and effort.

## 1. ~~Unify service hostnames across CI~~ (DONE in this PR)

CI workflows updated to use full `/etc/hosts` entry. Django defaults changed to service names unconditionally.

## 2. Change Rust/Node.js config defaults to service names

Rust `envconfig` defaults and Node.js `config.ts` defaults hardcode `localhost`. Change to service names (`db`, `redis7`, etc.). Safe because production always sets env vars and local dev uses `/etc/hosts`. Blocked by #1 (CI needs hosts entries first).

**Impact:** Eliminates the Node.js/Rust exports in `bin/start`. The startup scripts become pure process launchers with no env var wiring.

## 3. Remove overlay system after merge stabilizes

Once active branches have merged master (a few weeks after landing), remove `apply_overlays()` from `bin/sandbox-entrypoint.py` and the `COPY` overlay block from `Dockerfile.sandbox`. The overlaid files will exist in every branch.

**Impact:** Removes ~60 lines of pre-merge workaround code and simplifies the Docker image.

## 4. Consolidate persons DB env var names

Node.js reads `PERSONS_DATABASE_URL`/`PERSONS_READONLY_DATABASE_URL`. Rust reads `PERSONS_WRITE_DATABASE_URL`/`PERSONS_READ_DATABASE_URL`. Django reads `PERSONS_DB_WRITER_URL`/`PERSONS_DB_READER_URL`. Standardize on one set of names. Cross-cutting change across three runtimes.

**Impact:** Eliminates 4 redundant env vars and the "Rust and Node use different names" confusion.

## 5. Remove ClickHouse cargo cult vars

`CLICKHOUSE_API_USER`, `CLICKHOUSE_API_PASSWORD`, `CLICKHOUSE_APP_USER`, `CLICKHOUSE_APP_PASSWORD` are set in 6 places and read by nothing. ClickHouse credentials come from `users-dev.xml`. Remove from `bin/start-backend`, `bin/start-worker`, `bin/start-celery`, `dev-services.env`.

**Impact:** Small cleanup, removes dead config that confuses people reading the code.

## 6. Sandbox pause/unpause support

Docker compose `pause`/`unpause` sends SIGSTOP/SIGCONT for instant resume with memory preserved. Would make `sandbox stop`/`sandbox start` near-instant instead of doing a full container restart with dependency reinstall.

**Impact:** Dramatic UX improvement for switching between sandboxes.

## 7. Use sandbox image as CI worker

The `Dockerfile.sandbox` installs the same toolchain as CI workflows set up manually (Python, Node, Rust, uv, pnpm, cargo). Running CI tests inside the sandbox container image would eliminate duplicated setup logic across 7+ workflow files, remove the need for `/etc/hosts` hacks (Docker DNS handles service names), and guarantee tests run in the same environment developers use. The image is already built and published by `cd-sandbox-base-image.yml`.

**Impact:** Single source of truth for dev/CI toolchain. Faster CI (no setup steps). Fewer workflow maintenance headaches.

## 8. Cloud sandbox architecture

Hetzner fleet with orchestrator for agentic development at PostHog scale. Small always-on agent hosts, idle timeouts, simple server management table. Discussed but no code written.

**Impact:** Enables sandboxes for remote/CI agents and team-wide development workflows.
