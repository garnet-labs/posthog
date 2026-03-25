#!/usr/bin/env python3
"""
Sandbox container entrypoint.

Two-phase startup:
  1. Root phase (UID 0): create sandbox user, configure system, bind-mount
     node_modules onto the cache volume, then re-exec as the sandbox user.
  2. User phase: install dependencies, apply overlays, and launch mprocs
     inside tmux.
"""

from __future__ import annotations

import os
import re
import sys
import time
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from textwrap import dedent

WORKSPACE = Path("/workspace")
SANDBOX_HOME = Path("/tmp/sandbox-home")
OVERLAY_DIR = Path("/usr/local/share/sandbox")
PROGRESS_FILE = Path("/tmp/sandbox-progress")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    """Print to container stdout only (root phase)."""
    print(f"[{_ts()}] ==> {msg}", flush=True)  # noqa: T201


def info(msg: str) -> None:
    """Log to stdout and write to progress file for the host script."""
    print(f"[{_ts()}] ==> {msg}", flush=True)  # noqa: T201
    with PROGRESS_FILE.open("a") as f:
        f.write(f"[{_ts()}] ==> {msg}\n")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def run_quiet(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True)


def write_file(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mode is not None:
        path.chmod(mode)


def write_file_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        write_file(path, content)


def patch_file(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    path.write_text(text.replace(old, new))


# ---------------------------------------------------------------------------
# Root phase — runs as UID 0
# ---------------------------------------------------------------------------


def create_sandbox_user(uid: int, gid: int) -> None:
    """Create passwd/group/shadow entries so tools resolve the UID."""
    if run_quiet(["getent", "passwd", str(uid)]).returncode == 0:
        return

    with open("/etc/passwd", "a") as f:
        f.write(f"sandbox:x:{uid}:{gid}:sandbox:{SANDBOX_HOME}:/bin/bash\n")
    if run_quiet(["getent", "group", str(gid)]).returncode != 0:
        with open("/etc/group", "a") as f:
            f.write(f"sandbox:x:{gid}:\n")
    with open("/etc/shadow", "a") as f:
        f.write("sandbox:*:19000:0:99999:7:::\n")


def export_environment(uid: int, gid: int) -> None:
    """Write env vars to /etc/environment and /etc/profile.d for SSH sessions."""
    extra_vars = {
        "HOME": str(SANDBOX_HOME),
        "UV_CACHE_DIR": "/cache/uv",
        "UV_LINK_MODE": "copy",
        "XDG_CACHE_HOME": "/tmp/sandbox-cache",
        "CARGO_TARGET_DIR": "/cache/cargo-target",
        "npm_config_store_dir": "/cache/pnpm",
        "COREPACK_ENABLE_AUTO_PIN": "0",
        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
    }
    skip = {"HOSTNAME", "TERM", "SHELL", "PWD", "SHLVL", "_", "OLDPWD", "HOME", "USER", "LOGNAME"}

    lines = [f"{k}={v}" for k, v in os.environ.items() if k not in skip]
    lines.extend(f"{k}={v}" for k, v in extra_vars.items())

    Path("/etc/environment").write_text("\n".join(lines) + "\n")
    Path("/etc/profile.d/sandbox-env.sh").write_text("\n".join(f"export {line}" for line in lines) + "\n")


def start_sshd(uid: int, gid: int) -> None:
    """Start sshd if authorized keys are present."""
    keys = Path("/tmp/sandbox-authorized-keys")
    if not keys.exists() or keys.stat().st_size == 0:
        return

    ssh_dir = SANDBOX_HOME / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(keys, ssh_dir / "authorized_keys")
    ssh_dir.chmod(0o700)
    (ssh_dir / "authorized_keys").chmod(0o600)
    run(["chown", "-R", f"{uid}:{gid}", str(ssh_dir)])

    run(
        [
            "/usr/sbin/sshd",
            "-p",
            "2222",
            "-o",
            "PidFile=/tmp/sshd.pid",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "PermitRootLogin=no",
        ]
    )
    log("sshd listening on port 2222")


def copy_claude_auth(uid: int, gid: int) -> None:
    """Copy Claude Code auth files into the sandbox home."""
    claude_dir = SANDBOX_HOME / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    for name in (".credentials.json", "settings.json", "settings.local.json"):
        src = Path(f"/tmp/claude-auth/{name}")
        if src.exists():
            shutil.copy2(src, claude_dir / name)

    src = Path("/tmp/claude-auth.json")
    if src.exists():
        shutil.copy2(src, SANDBOX_HOME / ".claude.json")

    run(["chown", "-R", f"{uid}:{gid}", str(SANDBOX_HOME)])


def bind_mount_node_modules(uid: int, gid: int) -> None:
    """Bind-mount node_modules dirs onto the /cache/node-modules volume.

    This redirects pnpm I/O from the slow VirtioFS bind mount to fast ext4
    storage inside the Docker VM.
    """
    log("Bind-mounting node_modules onto cache volume...")
    cache_root = Path("/cache/node-modules")

    for pkg_json in WORKSPACE.rglob("package.json"):
        # Skip anything inside node_modules or .git
        parts = pkg_json.parts
        if "node_modules" in parts or ".git" in parts:
            continue

        pkg_dir = pkg_json.parent
        rel = pkg_dir.relative_to(WORKSPACE)
        nm = pkg_dir / "node_modules"
        cache_dir = cache_root / rel

        nm.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        run(["chown", f"{uid}:{gid}", str(nm)])
        run(["mount", "--bind", str(cache_dir), str(nm)])

    run(["chown", "-R", f"{uid}:{gid}", str(cache_root)])


def root_phase() -> None:
    uid = int(os.environ.get("SANDBOX_UID", "1000"))
    gid = int(os.environ.get("SANDBOX_GID", "1000"))

    SANDBOX_HOME.mkdir(parents=True, exist_ok=True)
    Path("/tmp/sandbox-cache").mkdir(parents=True, exist_ok=True)
    run(["chown", f"{uid}:{gid}", str(SANDBOX_HOME), "/tmp/sandbox-cache"])

    create_sandbox_user(uid, gid)
    export_environment(uid, gid)
    start_sshd(uid, gid)
    copy_claude_auth(uid, gid)
    bind_mount_node_modules(uid, gid)

    # Re-exec as the sandbox user.
    os.execvp("gosu", ["gosu", f"{uid}:{gid}", sys.executable, __file__, *sys.argv[1:]])


# ---------------------------------------------------------------------------
# User phase — runs as the sandbox UID
# ---------------------------------------------------------------------------


def apply_overlays() -> None:
    """Copy sandbox-aware scripts from the Docker image onto the worktree.

    This is a pre-merge workaround: branches that don't have sandbox changes
    yet get the sandbox-aware versions overlaid at boot. Once the sandbox PR
    merges to master, these copies overwrite with identical files and the sed
    commands are no-ops.
    """
    info("Applying sandbox script overlays...")
    copies = {
        "bin/wait-for-docker": "bin/wait-for-docker",
        "bin/mprocs.yaml": "bin/mprocs.yaml",
        "bin/start-backend": "bin/start-backend",
        "bin/start-rust-service": "bin/start-rust-service",
        "posthog/management/commands/sandbox_migrate.py": "posthog/management/commands/sandbox_migrate.py",
        "nodejs/package.json": "nodejs/package.json",
        "rust/cyclotron-node/package.json": "rust/cyclotron-node/package.json",
    }
    for overlay_path, worktree_path in copies.items():
        src = OVERLAY_DIR / overlay_path
        dst = WORKSPACE / worktree_path
        if src.exists():
            shutil.copy2(src, dst)

    # Disable standalone migration procs — the entrypoint runs sandbox_migrate
    # before starting mprocs, so these are redundant.
    mprocs = WORKSPACE / "bin/mprocs.yaml"
    text = mprocs.read_text()
    for proc in ("migrate-postgres", "migrate-clickhouse", "migrate-persons-db"):
        text = re.sub(
            rf"(    {proc}:\n        shell: [^\n]+\n)",
            r"\1        autostart: false\n",
            text,
        )
    mprocs.write_text(text)

    # Patch JS_URL into source files.
    js_url = os.environ.get("JS_URL", "")
    if js_url:
        patch_file(WORKSPACE / "posthog/utils.py", "http://localhost:8234", js_url)
        js_port = js_url.rsplit(":", 1)[-1]
        patch_file(WORKSPACE / "posthog/utils.py", ':8234"', f':{js_port}"')

        patch_file(
            WORKSPACE / "frontend/vite.config.ts",
            "origin: 'http://localhost:8234'",
            f"origin: process.env.JS_URL || 'http://localhost:8234',\n"
            f"            hmr: process.env.JS_URL ? {{ clientPort: parseInt(process.env.JS_URL.split(':').pop()) }} : undefined",
        )

    patch_file(
        WORKSPACE / "turbo.json",
        '"passThroughEnv": ["SKIP_TYPEGEN", "COREPACK_ENABLE_DOWNLOAD_PROMPT", "SSL_CERT_FILE"]',
        '"passThroughEnv": ["SKIP_TYPEGEN", "COREPACK_ENABLE_DOWNLOAD_PROMPT", "SSL_CERT_FILE", "JS_URL"]',
    )

    # Add SESSION_COOKIE_NAME env var support if not present.
    web_settings = WORKSPACE / "posthog/settings/web.py"
    text = web_settings.read_text()
    if not re.search(r"SESSION_COOKIE_NAME.*get_from_env", text):
        text = text.replace(
            "CSRF_COOKIE_NAME",
            'SESSION_COOKIE_NAME = get_from_env("SESSION_COOKIE_NAME", "sessionid")\nCSRF_COOKIE_NAME',
            1,
        )
        web_settings.write_text(text)


def install_python_deps() -> None:
    info("Installing Python dependencies...")
    run(["uv", "sync", "--no-editable"])
    # Make hogli available — normally done by flox on-activate.sh.
    hogli_link = Path("/cache/python/bin/hogli")
    hogli_link.unlink(missing_ok=True)
    hogli_link.symlink_to("/workspace/bin/hogli")
    phrocs_link = WORKSPACE / "bin/phrocs"
    if not phrocs_link.exists():
        phrocs_link.symlink_to("/usr/local/bin/phrocs")


def install_node_deps() -> None:
    info("Installing Node dependencies...")
    # CI=1 suppresses interactive prompts. --no-frozen-lockfile is needed
    # because the pre-merge overlay may update package.json files.
    run(
        ["pnpm", "install", "--no-frozen-lockfile"],
        env={**os.environ, "CI": "1"},
    )


def fetch_rust_crates() -> None:
    """Pre-fetch Rust crate sources so concurrent cargo builds don't race."""
    info("Fetching Rust crate sources...")
    run(["cargo", "fetch"], cwd=str(WORKSPACE / "rust"))


def install_geoip() -> None:
    """Symlink the GeoIP database from the Docker image into the worktree."""
    mmdb = WORKSPACE / "share/GeoLite2-City.mmdb"
    if mmdb.exists() or mmdb.is_symlink():
        return
    mmdb.parent.mkdir(parents=True, exist_ok=True)
    mmdb.symlink_to("/share/GeoLite2-City.mmdb")


def ensure_demo_data() -> None:
    """Generate demo data on first boot; skip if already present."""
    result = run_quiet(
        [
            "psql",
            "-h",
            "db",
            "-U",
            "posthog",
            "-d",
            "posthog",
            "-tAc",
            "SELECT 1 FROM posthog_user WHERE email='test@posthog.com' LIMIT 1",
        ]
    )
    if result.stdout.strip() == b"1":
        info("Demo data already present, skipping generation.")
    else:
        info("Generating demo data (first boot)...")
        run(["python", "manage.py", "generate_demo_data"])


def create_kafka_topics() -> None:
    info("Pre-creating Kafka topics...")
    for topic in ("clickhouse_events_json", "exceptions_ingestion"):
        if run_quiet(["rpk", "topic", "describe", topic, "--brokers", "kafka:9092"]).returncode != 0:
            run(["rpk", "topic", "create", topic, "--brokers", "kafka:9092", "-p", "1", "-r", "1"])


def generate_mprocs_config() -> None:
    info("Generating mprocs config...")
    config_dir = WORKSPACE / ".posthog/.generated"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "mprocs.yaml"

    # Seed intents on first boot; on restart, reuse the saved config.
    needs_seed = not config_file.exists()
    if not needs_seed:
        needs_seed = "_posthog:" not in config_file.read_text()

    if needs_seed:
        intents = os.environ.get("SANDBOX_INTENTS", "product_analytics")
        info(f"Seeding intents: {intents}")
        lines = ["_posthog:", "  intents:"]
        for intent in intents.split(","):
            lines.append(f"  - {intent.strip()}")
        lines.append("procs: {}")
        config_file.write_text("\n".join(lines) + "\n")

    subprocess.run(["hogli", "dev:generate"], capture_output=True)


def setup_intellij_background() -> None:
    """Register IntelliJ IDEA backend in a background process."""
    idea_script = Path("/opt/idea/bin/remote-dev-server.sh")
    if not idea_script.exists():
        return

    pid = os.fork()
    if pid != 0:
        return  # Parent continues

    # Child process — runs in background
    os.environ["JAVA_TOOL_OPTIONS"] = f"-Duser.home={SANDBOX_HOME}"

    info("Registering IntelliJ IDEA for Gateway (background)...")
    result = subprocess.run(
        ["remote-dev-server.sh", "registerBackendLocationForGateway"],
        executable=str(idea_script),
        env={**os.environ, "REMOTE_DEV_NON_INTERACTIVE": "1"},
    )
    if result.returncode != 0:
        print(f"[{_ts()}] ERROR: IntelliJ backend registration failed (exit {result.returncode}).")  # noqa: T201

    # Install Python plugin if not already present
    jetbrains_dir = SANDBOX_HOME / ".local/share/JetBrains"
    has_python_plugin = any(jetbrains_dir.rglob("python*")) if jetbrains_dir.exists() else False
    if not has_python_plugin:
        info("Installing Python plugin...")
        result = subprocess.run(
            [
                "remote-dev-server.sh",
                "installPlugins",
                "PythonCore",
                "Pythonid",
                "intellij.python.dap.plugin",
                "com.intellij.python.django",
            ],
            executable=str(idea_script),
            env={**os.environ, "REMOTE_DEV_NON_INTERACTIVE": "1"},
        )
        if result.returncode != 0:
            print(f"[{_ts()}] ERROR: Plugin installation failed (exit {result.returncode}).")  # noqa: T201

    # Configure Python SDK
    idea_config = SANDBOX_HOME / ".config/JetBrains/IntelliJIdea2025.3"
    write_file_if_missing(
        idea_config / "options/jdk.table.xml",
        dedent("""\
            <application>
              <component name="ProjectJdkTable">
                <jdk version="2">
                  <name value="Python 3.12 (sandbox)" />
                  <type value="Python SDK" />
                  <homePath value="/cache/python/bin/python3" />
                  <roots>
                    <classPath><root type="composite" /></classPath>
                    <sourcePath><root type="composite" /></sourcePath>
                  </roots>
                  <additional />
                </jdk>
              </component>
            </application>
        """),
    )

    write_file_if_missing(
        WORKSPACE / ".idea/modules.xml",
        dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <project version="4">
              <component name="ProjectModuleManager">
                <modules>
                  <module fileurl="file://$PROJECT_DIR$/.idea/posthog.iml" filepath="$PROJECT_DIR$/.idea/posthog.iml" />
                </modules>
              </component>
            </project>
        """),
    )

    write_file_if_missing(
        WORKSPACE / ".idea/misc.xml",
        dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <project version="4">
              <component name="ProjectRootManager" version="2" project-jdk-name="Python 3.12 (sandbox)" project-jdk-type="Python SDK" />
              <component name="TestRunnerService">
                <option name="PROJECT_TEST_RUNNER" value="py.test" />
              </component>
            </project>
        """),
    )

    info("IntelliJ IDEA backend ready")
    os._exit(0)


def user_phase() -> None:
    PROGRESS_FILE.touch()

    os.environ.update(
        {
            "HOME": str(SANDBOX_HOME),
            "UV_CACHE_DIR": "/cache/uv",
            "UV_LINK_MODE": "copy",
            "XDG_CACHE_HOME": "/tmp/sandbox-cache",
            "COREPACK_ENABLE_AUTO_PIN": "0",
            "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
            "CARGO_TARGET_DIR": "/cache/cargo-target",
            "npm_config_store_dir": "/cache/pnpm",
        }
    )
    Path("/cache/cargo-target").mkdir(parents=True, exist_ok=True)

    # The worktree's .git file points to the host's .git/worktrees/ path,
    # which doesn't exist inside the container. Point GIT_DIR at a dummy
    # repo so all git commands find a valid repo without touching the host.
    run(["git", "init", "-q", "/tmp/sandbox-git"])
    os.environ["GIT_DIR"] = "/tmp/sandbox-git"
    os.chdir(WORKSPACE)

    apply_overlays()

    install_geoip()
    create_kafka_topics()

    def install_python_and_migrate() -> None:
        install_python_deps()
        run(["python", "manage.py", "sandbox_migrate", "--parallel", "--progress-file", str(PROGRESS_FILE)])
        ensure_demo_data()

    # Run dependency installs in parallel. Migrations and demo data are chained
    # after Python deps (uv ~1.5s) so they overlap with the slower pnpm/cargo.
    with ThreadPoolExecutor() as pool:
        futures = {
            pool.submit(install_python_and_migrate): "python deps + migrations",
            pool.submit(install_node_deps): "node deps",
            pool.submit(fetch_rust_crates): "rust crates",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[{_ts()}] ERROR: {name} failed: {e}", flush=True)  # noqa: T201
                raise

    # generate_mprocs_config needs the hogli symlink created by install_python_deps.
    generate_mprocs_config()
    # setup_intellij_background uses os.fork(), which is unsafe inside a
    # ThreadPoolExecutor, so it runs after the pool is closed.
    setup_intellij_background()

    info("Starting PostHog via mprocs in tmux...")
    lock = WORKSPACE / "bin/start.lock"
    lock.unlink(missing_ok=True)

    os.execvp("tmux", ["tmux", "-L", "sandbox", "new-session", "-s", "posthog", "bin/start --phrocs"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uid = int(os.environ.get("SANDBOX_UID", "1000"))
    if os.getuid() == 0 and uid != 0:
        root_phase()
    else:
        user_phase()
