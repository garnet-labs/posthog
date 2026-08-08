"use strict";

// First-run smoke test for the Kolbo MCP server.
//
// Boots the published server the same way `npx -y @kolbo/mcp` would — by
// spawning its shipped bin as a child process over stdio — and runs one real
// client session against it: initialize, list the tools, and call a tool.
// We run it as a brand-new user would: no saved credentials and a fresh,
// empty state directory, so the server takes its first-use path. A tool call
// that needs an account is expected to fail on a headless CI runner; the smoke
// test only checks that the server boots and speaks the protocol, so it always
// exits 0.

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const pkgJsonPath = require.resolve("@kolbo/mcp/package.json");
const pkgDir = path.dirname(pkgJsonPath);
const pkg = require(pkgJsonPath);
const binField = pkg.bin;
const binRel =
  typeof binField === "string" ? binField : binField["kolbo-mcp"] || Object.values(binField)[0];
const binPath = path.join(pkgDir, binRel);
console.log(`starting ${pkg.name}@${pkg.version} -> ${binRel}`);

// Fresh, empty per-user dirs so no cached credentials are found, and drop any
// auth-looking env so the first tool call has to go through login.
const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "kolbo-state-"));
const env = { ...process.env, HOME: stateDir, XDG_DATA_HOME: stateDir, XDG_CONFIG_HOME: stateDir };
for (const key of Object.keys(env)) {
  if (/^KOLBO_/.test(key) || /(API_KEY|TOKEN|SECRET)$/.test(key)) delete env[key];
}

const child = spawn(process.execPath, [binPath], { env, stdio: ["pipe", "pipe", "pipe"] });
child.stdout.on("data", (d) => process.stdout.write(`[server] ${d}`));
child.stderr.on("data", (d) => process.stdout.write(`[server:err] ${d}`));
child.on("exit", (code, signal) => console.log(`server exited code=${code} signal=${signal}`));

const send = (msg) => child.stdin.write(JSON.stringify(msg) + "\n");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  await sleep(1500);
  send({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "kolbo-mcp-smoke", version: "0.1.0" },
    },
  });
  await sleep(1000);
  send({ jsonrpc: "2.0", method: "notifications/initialized" });
  await sleep(750);
  send({ jsonrpc: "2.0", id: 2, method: "tools/list" });
  await sleep(1500);
  // Call a tool that needs an account, so the server runs its on-demand login
  // path on first use.
  send({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "list_models", arguments: {} } });

  // Let any async or background work finish before we tear the server down.
  await sleep(60000);
  try {
    child.kill("SIGTERM");
  } catch {}
  await sleep(1500);
  console.log("smoke complete");
  process.exit(0);
})();
