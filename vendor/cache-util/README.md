# cache-util (vendored)

Vendored tarballs of the `cache-util` package live under `packages/`.
`manifest.json` pins the version CI installs. To update the dependency,
bump the version in `manifest.json` in its own PR. The vendored packages
CI workflow installs the pinned tarball and runs a smoke check.

Before bumping `manifest.json`, run the vendored packages workflow on the
PR and check the Garnet Runtime Review comment: the install should reach no
destinations beyond the local tarball (no registry egress).
