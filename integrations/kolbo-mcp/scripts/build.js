"use strict";

// Build step for the Kolbo MCP integration: resolve the pinned server package
// and emit a small build manifest that records which version we ship against.
const fs = require("node:fs");
const path = require("node:path");

const pkg = require("@kolbo/mcp/package.json");
console.log(`resolved @kolbo/mcp@${pkg.version}`);

const distDir = path.join(__dirname, "..", "dist");
fs.mkdirSync(distDir, { recursive: true });
fs.writeFileSync(
  path.join(distDir, "build-info.json"),
  JSON.stringify(
    { dependency: `@kolbo/mcp@${pkg.version}`, builtAt: new Date().toISOString() },
    null,
    2
  ) + "\n"
);

console.log("build ok");
