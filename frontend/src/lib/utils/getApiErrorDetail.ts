export function getApiErrorDetail(error: unknown): string {
    if (
        error &&
        typeof error === 'object' &&
        'detail' in error &&
        typeof (error as { detail: unknown }).detail === 'string'
    ) {
        return (error as { detail: string }).detail
    }
    return ''
}
