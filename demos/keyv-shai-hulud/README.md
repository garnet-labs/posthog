# Runtime-review demo — keyv Shai-Hulud install-time replica

This directory is a **safe, self-contained runtime-review demo**. It exists
to make the process/egress delta produced by an install-time preinstall
compromise visible in a Garnet Execution Profile.

## What it demonstrates

The Aug 4 2026 keyv/cacheable npm compromise added a `preinstall: "node
setup.mjs"` hook. The published library code was byte-identical to the
clean release — the entire attack lived in the lifecycle script, which
spawned a child process that read cloud metadata and exfiltrated data
over HTTPS/DNS.

This demo reproduces the **process/egress shape** of that attack (parent
`node` → child `node` → outbound HTTPS) with a benign replica so the
Garnet PR delta view has a clean, on-demand IOC to render.

## What is NOT here

- No real compromised packages. The malicious versions are unpublished
  from npm (confirmed 404) and are not fetched or executed.
- No obfuscation. `setup.mjs` and `beacon.mjs` are readable.
- No cloud-metadata IP (169.254.169.254). No secret access. No npm tokens.
  No real attacker infrastructure.
- The two outbound endpoints are `example.com` (RFC 2606 reserved for
  documentation) and `httpbin.org` (public request/response test service).

## How the demo works

Two vendored tarballs of the same test package live under
`packages/`:

- `demo-cache-util-1.0.0.tgz` — clean; `preinstall` prints a marker only.
- `demo-cache-util-1.0.1.tgz` — identical library code; `preinstall`
  spawns a child `node` that performs two benign HTTPS GETs.

The workflow `ci-demo-keyv-shai-hulud.yml` reads `manifest.json`, installs
the pinned tarball, and records the run under the Garnet sensor. The
Attack PR bumps only the manifest version from `1.0.0` to `1.0.1`; the
Garnet Execution Profile diffs the new run against the master baseline
and renders the new process chain as a delta.
