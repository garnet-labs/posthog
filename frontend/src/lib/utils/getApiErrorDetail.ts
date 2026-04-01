export function getApiErrorDetail(error: unknown): string | undefined {
    if (error !== null && typeof error === 'object') {
        if ('detail' in error && typeof error.detail === 'string') {
            return error.detail
        }

        if ('data' in error && error.data && typeof error.data === 'object') {
            for (const value of Object.values(error.data as Record<string, unknown>)) {
                if (Array.isArray(value) && typeof value[0] === 'string') {
                    return value[0]
                }

                if (typeof value === 'string') {
                    return value
                }
            }
        }
    }

    return undefined
}
