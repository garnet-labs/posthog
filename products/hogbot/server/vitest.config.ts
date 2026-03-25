import { existsSync } from 'fs'
import path from 'path'

const moduleRootCandidates = [
    path.resolve(__dirname, '../../../node_modules/.pnpm/node_modules'),
    path.resolve(__dirname, '../../../../code/node_modules'),
]
const moduleRoot = moduleRootCandidates.find((candidate) => existsSync(candidate)) ?? moduleRootCandidates[0]

export default {
    root: __dirname,
    resolve: {
        alias: {
            hono: path.resolve(moduleRoot, 'hono'),
            '@hono/node-server': path.resolve(moduleRoot, '@hono/node-server'),
        },
    },
    test: {
        css: false,
        environment: 'node',
        globals: true,
        include: ['src/__tests__/**/*.test.ts'],
    },
}
