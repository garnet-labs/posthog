# cache-util (vendored)

Vendored tarballs of the `cache-util` package live under `packages/`.
`manifest.json` pins the version CI installs. To update the dependency,
bump the version in `manifest.json` in its own PR; the vendored packages
CI workflow installs the pinned tarball and runs a smoke check.
