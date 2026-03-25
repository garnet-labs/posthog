type GitHubInstallationConfig = {
    installation_id?: string | number | null
    account?: {
        type?: string | null
        name?: string | null
    } | null
} | null

export function getGitHubInstallationSettingsUrl(config?: GitHubInstallationConfig): string | null {
    const installationId = config?.installation_id
    if (!installationId) {
        return null
    }

    const accountType = config?.account?.type
    const accountName = config?.account?.name

    if (accountType === 'Organization' && accountName) {
        return `https://github.com/organizations/${encodeURIComponent(accountName)}/settings/installations/${installationId}`
    }

    return `https://github.com/settings/installations/${installationId}`
}

export function normalizeGitHubRepositoryValue(value?: string | null): string | null {
    if (!value) {
        return null
    }

    const repositoryParts = value.split('/', 2)
    return repositoryParts.length === 2 ? repositoryParts[1] : value
}
