# Runtime-review demo — an install-time script that reaches instance metadata

This is a benign replica, built to be recorded. It exists so a Garnet
Execution Profile has an install-time execution chain worth looking at.

## What it does

Two versions of one vendored in-house tarball live under `packages/`:

- `demo-config-store-1.0.0.tgz` — the `preinstall` hook prints a marker.
- `demo-config-store-1.0.1.tgz` — same `index.js`, byte for byte. The
  `preinstall` hook spawns a child `node` process that makes one HTTP GET
  to `169.254.169.254` (the cloud instance metadata address) and one to
  `example.com`.

Both responses are discarded. The child prints a status marker and exits.

`manifest.json` pins which tarball the workflow installs. The version bump
is the whole change between the two commits of the demo pull request, and
the library code is identical across it, so the only thing that differs is
install-time behavior.

## What it does not do

It reads no credential, token, or environment value. It writes nothing
outside `/tmp`. It sends no data anywhere. Nothing is obfuscated: read
`setup.mjs` and `collect.mjs` inside the 1.0.1 tarball.

## Why it matters

The published library code is the part a reviewer reads. The lifecycle
script is the part that runs. A diff of the pull request shows one line
changing in `manifest.json`. The recorded profile shows a new process under
`npm install` and where it went.

## The recording

`.github/workflows/ci-demo-install-time-imds-reach.yml` runs the install
under the Garnet sensor and waits for the sensor to settle, because a
preinstall child can outlive the `npm` process that started it.

This is what the 1.0.1 install recorded on a GitHub-hosted runner:

```
Runner.Worker
└─ bash
   └─ node                       npm install
      └─ dash
         └─ node                 preinstall: setup.mjs
            └─ node              collect.mjs
               ├─ → 169.254.169.254 (instance metadata)
               └─ → example.com
```

Public Execution Profile:
https://app.garnet.ai/public/runs/31131775657?profile=019fd971-db1a-7dad-882e-0c245ddb782f
