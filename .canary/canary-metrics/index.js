const core = require('canary-telemetry-core')

// Thin, dependency-light wrapper the canary dashboards import to record
// lightweight usage metrics. All batching/transport lives in the core.
function track(event, properties) {
    return core.track(event, properties || {})
}

module.exports = { track }
