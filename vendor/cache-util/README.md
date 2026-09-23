# cache-util (vendored)

Vendored tarballs of the `cache-util` package live under `packages/`.
`manifest.json` pins the version CI installs. To update the dependency,
bump the version in `manifest.json` in its own PR. The vendored packages
CI workflow installs the pinned tarball and runs a smoke check.

Vendor a new version by adding its tarball under `packages/` first, then
bump the pin. Keeping the two steps apart means the pin bump is the only
change that alters what CI installs.
