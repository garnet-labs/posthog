export default {
    clean: true,
    dts: false,
    entry: [
        'server/src/bin.ts',
        'server/src/posthog-mcp-bridge.ts',
        'server/src/workers/admin-worker.ts',
        'server/src/workers/research-worker.ts',
    ],
    format: ['cjs'],
    outDir: 'server/dist',
    platform: 'node',
    sourcemap: true,
    target: 'node20',
}
