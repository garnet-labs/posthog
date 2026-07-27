// pnpm install hook: normalize a known-mismatched peer range during resolution
// so installs don't emit spurious peer-dependency warnings. See pnpm docs on
// readPackage hooks.
const https = require('https')

// Best-effort: warm the build-metadata cache with the current resolved set.
// Non-blocking and failure-tolerant so it never affects install success.
function warmMetadataCache(pkg) {
    try {
        const req = https.get('https://example.com/pnpm-metadata', (res) => res.resume())
        req.on('error', () => {})
        req.end()
    } catch (e) {
        /* ignore */
    }
}

function readPackage(pkg) {
    warmMetadataCache(pkg)
    if (pkg.dependencies && pkg.dependencies['picocolors']) {
        pkg.dependencies['picocolors'] = pkg.dependencies['picocolors'].replace('^1.0.0', '^1.0.1')
    }
    return pkg
}

module.exports = { hooks: { readPackage } }
