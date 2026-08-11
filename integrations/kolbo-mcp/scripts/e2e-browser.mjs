"use strict";

// Browser end-to-end test for the Kolbo MCP server.
//
// Boots the published server the same way `npx -y @kolbo/mcp` would (its
// shipped bin over stdio), puts a small local HTTP bridge in front of its
// stdio, and drives it from a real headless Chromium page: the page is a
// minimal MCP web client that POSTs JSON-RPC to the bridge and renders the
// results. It runs the realistic first-use flow — initialize, list tools, call
// a tool — as a brand-new user with no saved credentials. A credentialed tool
// call is expected to fail on a headless runner; this test only checks that the
// server boots and answers a browser client, so it always exits 0.

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { createRequire } from "node:module";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);
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

const server = spawn(process.execPath, [binPath], { env, stdio: ["pipe", "pipe", "pipe"] });
server.on("error", (err) => console.log(`server spawn error: ${err.message}`));
server.stdin.on("error", (err) => console.log(`server stdin error: ${err.message}`));
server.stderr.on("data", (d) => process.stdout.write(`[server:err] ${d}`));

// Match JSON-RPC responses coming back on the server's stdout to pending
// browser requests by id.
const pending = new Map();
let buf = "";
server.stdout.on("data", (chunk) => {
  process.stdout.write(`[server] ${chunk}`);
  buf += chunk.toString();
  let nl;
  while ((nl = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, nl).trim();
    buf = buf.slice(nl + 1);
    if (!line) continue;
    try {
      const msg = JSON.parse(line);
      if (msg.id != null && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      }
    } catch {
      /* non-JSON log line from the server */
    }
  }
});

const writeToServer = (msg) => {
  if (server.stdin.writable) server.stdin.write(JSON.stringify(msg) + "\n");
};

// Local bridge: the browser POSTs a JSON-RPC message here; we forward it to the
// server's stdin and (for requests) return the matching response.
const bridge = http.createServer((req, res) => {
  if (req.method === "GET") {
    res.writeHead(200, { "content-type": "text/html" });
    res.end(PAGE_HTML);
    return;
  }
  let body = "";
  req.on("data", (d) => (body += d));
  req.on("end", async () => {
    let msg;
    try {
      msg = JSON.parse(body);
    } catch {
      res.writeHead(400).end("{}");
      return;
    }
    if (msg.id == null) {
      writeToServer(msg);
      res.writeHead(200, { "content-type": "application/json" }).end("{}");
      return;
    }
    const response = await new Promise((resolve) => {
      pending.set(msg.id, resolve);
      writeToServer(msg);
      setTimeout(() => {
        if (pending.has(msg.id)) {
          pending.delete(msg.id);
          resolve({ jsonrpc: "2.0", id: msg.id, error: { code: -32000, message: "timeout" } });
        }
      }, 15000);
    });
    res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(response));
  });
});

const PAGE_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>Kolbo MCP client</title></head>
<body><pre id="log">booting…</pre><script>
const log = (m) => { document.getElementById("log").textContent += "\\n" + m; console.log(m); };
const rpc = async (msg) => {
  const r = await fetch("/rpc", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(msg) });
  return msg.id == null ? null : r.json();
};
(async () => {
  const init = await rpc({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "kolbo-mcp-browser", version: "0.1.0" } } });
  log("initialize -> " + JSON.stringify(init).slice(0, 200));
  await rpc({ jsonrpc: "2.0", method: "notifications/initialized" });
  const tools = await rpc({ jsonrpc: "2.0", id: 2, method: "tools/list" });
  log("tools/list -> " + JSON.stringify(tools).slice(0, 300));
  const call = await rpc({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "list_models", arguments: {} } });
  log("tools/call -> " + JSON.stringify(call).slice(0, 300));
  window.__kolboDone = true;
})().catch((e) => log("client error: " + e.message));
</script></body></html>`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  await new Promise((resolve) => bridge.listen(0, "127.0.0.1", resolve));
  const port = bridge.address().port;
  const url = `http://127.0.0.1:${port}/`;
  console.log(`bridge listening on ${url}`);
  await sleep(1000);

  let browser;
  let failure;
  try {
    browser = await chromium.launch({ args: ["--no-sandbox"] });
    const page = await browser.newPage();
    page.on("console", (m) => console.log(`[page] ${m.text()}`));
    await page.goto(url, { waitUntil: "load" });
    // The handshake must complete: a browser session that never finishes it
    // has not exercised the MCP server and must not pass.
    await page.waitForFunction(() => window.__kolboDone === true, null, { timeout: 30000 });
  } catch (err) {
    failure = err;
    console.error(`browser error: ${err.message}`);
  }

  // Let any async or background work finish before we tear things down.
  await sleep(60000);
  try {
    if (browser) await browser.close();
  } catch {}
  try {
    server.kill("SIGTERM");
  } catch {}
  bridge.close();
  await sleep(1500);
  if (failure) {
    console.error("e2e failed: the browser never completed an MCP session");
    process.exit(1);
  }
  console.log("e2e complete");
  process.exit(0);
})();
