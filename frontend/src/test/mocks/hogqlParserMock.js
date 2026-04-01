// Jest-compatible mock for @posthog/hogql-parser
// The real ESM module uses import.meta.url which doesn't work in Jest's CJS environment.
// This wrapper loads the CJS build of the WASM parser directly.

const path = require('path')

const wasmCjsPath = path.resolve(__dirname, '../../../../common/hogql_parser/dist/hogql_parser_wasm.cjs')

async function createHogQLParser() {
    const factory = require(wasmCjsPath)
    return await factory()
}

module.exports = createHogQLParser
module.exports.default = createHogQLParser
