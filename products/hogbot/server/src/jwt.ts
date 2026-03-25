import { createVerify } from 'crypto'

import type { HogbotJwtPayload } from './types'

const AUDIENCE = 'posthog:sandbox_connection'

export class JwtValidationError extends Error {
    constructor(
        message: string,
        readonly code: string
    ) {
        super(message)
    }
}

function decodeBase64Url(value: string): string {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
    const padding = normalized.length % 4 === 0 ? '' : '='.repeat(4 - (normalized.length % 4))
    return Buffer.from(`${normalized}${padding}`, 'base64').toString('utf-8')
}

export function validateJwt(authorizationHeader: string | undefined, publicKey: string): HogbotJwtPayload {
    if (!authorizationHeader) {
        throw new JwtValidationError('Missing Authorization header', 'missing_authorization')
    }

    const [scheme, token] = authorizationHeader.split(' ')
    if (scheme !== 'Bearer' || !token) {
        throw new JwtValidationError('Invalid Authorization header', 'invalid_authorization')
    }

    const parts = token.split('.')
    if (parts.length !== 3) {
        throw new JwtValidationError('Malformed JWT', 'malformed_token')
    }

    const [encodedHeader, encodedPayload, encodedSignature] = parts
    const header = JSON.parse(decodeBase64Url(encodedHeader)) as { alg?: string }
    if (header.alg !== 'RS256') {
        throw new JwtValidationError('Unsupported JWT algorithm', 'invalid_algorithm')
    }

    const signature = Buffer.from(encodedSignature.replace(/-/g, '+').replace(/_/g, '/'), 'base64')
    const signingInput = `${encodedHeader}.${encodedPayload}`
    const verifier = createVerify('RSA-SHA256')
    verifier.update(signingInput)
    verifier.end()
    const isValid = verifier.verify(publicKey, signature)
    if (!isValid) {
        throw new JwtValidationError('Invalid JWT signature', 'invalid_signature')
    }

    const payload = JSON.parse(decodeBase64Url(encodedPayload)) as Partial<HogbotJwtPayload>
    if (!payload || typeof payload !== 'object') {
        throw new JwtValidationError('Invalid token payload', 'invalid_payload')
    }
    if (payload.aud !== AUDIENCE) {
        throw new JwtValidationError('Invalid token audience', 'invalid_audience')
    }
    if (typeof payload.exp !== 'number' || payload.exp <= Math.floor(Date.now() / 1000)) {
        throw new JwtValidationError('JWT has expired', 'expired_token')
    }
    if (payload.scope !== 'hogbot') {
        throw new JwtValidationError('Invalid token scope', 'invalid_scope')
    }
    if (typeof payload.team_id !== 'number') {
        throw new JwtValidationError('Missing team_id in token', 'missing_team')
    }
    if (typeof payload.user_id !== 'number') {
        throw new JwtValidationError('Missing user_id in token', 'missing_user')
    }
    if (typeof payload.distinct_id !== 'string') {
        throw new JwtValidationError('Missing distinct_id in token', 'missing_distinct_id')
    }

    return payload as HogbotJwtPayload
}
