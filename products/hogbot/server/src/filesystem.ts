import fs from 'fs'
import path from 'path'

const { lstat, readdir, readFile, realpath, stat } = fs.promises

export const DEFAULT_FILE_CONTENT_MAX_BYTES = 1024 * 1024
export const MAX_FILE_CONTENT_MAX_BYTES = 5 * 1024 * 1024

export type FilesystemEntryType = 'file' | 'directory' | 'symlink'
export type FilesystemContentEncoding = 'utf-8' | 'base64'

export interface FilesystemEntry {
    path: string
    name: string
    type: FilesystemEntryType
    size: number
    ctime_ms: number
    mtime_ms: number
    is_symbolic_link: boolean
}

export interface FilesystemStatResponse {
    entry: FilesystemEntry
}

export interface FilesystemListResponse {
    directory: FilesystemEntry
    entries: FilesystemEntry[]
}

export interface FilesystemContentResponse {
    file: FilesystemEntry
    encoding: FilesystemContentEncoding
    content: string
    truncated: boolean
}

export class FilesystemError extends Error {
    constructor(
        message: string,
        readonly statusCode: 400 | 404 = 400
    ) {
        super(message)
        this.name = 'FilesystemError'
    }
}

interface ResolvedFilesystemPath {
    repositoryRoot: string
    requestedPath: string
    absolutePath: string
}

function normalizeRequestedPath(requestedPath?: string): string {
    const rawPath = requestedPath?.trim() || '/'
    if (rawPath.includes('\0')) {
        throw new FilesystemError('Path contains invalid null bytes')
    }

    const relativeInput = rawPath === '/' || rawPath === '.' ? '.' : rawPath.replace(/^\/+/, '')
    const normalizedRelative = path.posix.normalize(relativeInput)
    if (normalizedRelative === '..' || normalizedRelative.startsWith('../')) {
        throw new FilesystemError('Path must stay within the workspace root')
    }
    return normalizedRelative === '.' ? '/' : `/${normalizedRelative}`
}

function ensureWithinRepository(repositoryRoot: string, candidatePath: string): void {
    const relative = path.relative(repositoryRoot, candidatePath)
    if (relative === '') {
        return
    }
    if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
        throw new FilesystemError('Path escapes the workspace root')
    }
}

async function resolveFilesystemPath(repositoryPath: string, requestedPath?: string): Promise<ResolvedFilesystemPath> {
    const repositoryRoot = await realpath(repositoryPath)
    const normalizedPath = normalizeRequestedPath(requestedPath)
    const relativePath = normalizedPath === '/' ? '' : normalizedPath.slice(1)
    const absolutePath = path.resolve(repositoryRoot, relativePath)

    ensureWithinRepository(repositoryRoot, absolutePath)

    try {
        const resolvedPath = await realpath(absolutePath)
        ensureWithinRepository(repositoryRoot, resolvedPath)
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
            throw new FilesystemError(`Path not found: ${normalizedPath}`, 404)
        }
        throw error
    }

    return {
        repositoryRoot,
        requestedPath: normalizedPath,
        absolutePath,
    }
}

function getEntryName(requestedPath: string): string {
    return requestedPath === '/' ? '/' : path.posix.basename(requestedPath)
}

async function buildEntry(
    repositoryRoot: string,
    requestedPath: string,
    absolutePath: string
): Promise<FilesystemEntry> {
    const lstats = await lstat(absolutePath)

    if (lstats.isSymbolicLink()) {
        try {
            const resolvedPath = await realpath(absolutePath)
            ensureWithinRepository(repositoryRoot, resolvedPath)
            const resolvedStats = await stat(absolutePath)
            return {
                path: requestedPath,
                name: getEntryName(requestedPath),
                type: resolvedStats.isDirectory() ? 'directory' : 'file',
                size: resolvedStats.size,
                ctime_ms: resolvedStats.ctimeMs,
                mtime_ms: resolvedStats.mtimeMs,
                is_symbolic_link: true,
            }
        } catch {
            return {
                path: requestedPath,
                name: getEntryName(requestedPath),
                type: 'symlink',
                size: lstats.size,
                ctime_ms: lstats.ctimeMs,
                mtime_ms: lstats.mtimeMs,
                is_symbolic_link: true,
            }
        }
    }

    return {
        path: requestedPath,
        name: getEntryName(requestedPath),
        type: lstats.isDirectory() ? 'directory' : 'file',
        size: lstats.size,
        ctime_ms: lstats.ctimeMs,
        mtime_ms: lstats.mtimeMs,
        is_symbolic_link: false,
    }
}

function decodeUtf8(buffer: Buffer | Uint8Array): string {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer)
}

export async function statFilesystemEntry(
    repositoryPath: string,
    requestedPath?: string
): Promise<FilesystemStatResponse> {
    const resolved = await resolveFilesystemPath(repositoryPath, requestedPath)
    return {
        entry: await buildEntry(resolved.repositoryRoot, resolved.requestedPath, resolved.absolutePath),
    }
}

export async function listFilesystemDirectory(
    repositoryPath: string,
    requestedPath?: string
): Promise<FilesystemListResponse> {
    const resolved = await resolveFilesystemPath(repositoryPath, requestedPath)
    const directory = await buildEntry(resolved.repositoryRoot, resolved.requestedPath, resolved.absolutePath)
    if (directory.type !== 'directory') {
        throw new FilesystemError(`Path is not a directory: ${resolved.requestedPath}`)
    }

    const children = await readdir(resolved.absolutePath)
    const entries = await Promise.all(
        children.map((childName: string) =>
            buildEntry(
                resolved.repositoryRoot,
                resolved.requestedPath === '/' ? `/${childName}` : `${resolved.requestedPath}/${childName}`,
                path.join(resolved.absolutePath, childName)
            )
        )
    )

    entries.sort((left: FilesystemEntry, right: FilesystemEntry) => {
        if (left.type !== right.type) {
            if (left.type === 'directory') {
                return -1
            }
            if (right.type === 'directory') {
                return 1
            }
        }
        return left.name.localeCompare(right.name)
    })

    return { directory, entries }
}

export async function readFilesystemFile(
    repositoryPath: string,
    requestedPath?: string,
    encoding: FilesystemContentEncoding = 'utf-8',
    maxBytes = DEFAULT_FILE_CONTENT_MAX_BYTES
): Promise<FilesystemContentResponse> {
    if (maxBytes > MAX_FILE_CONTENT_MAX_BYTES) {
        throw new FilesystemError(`max_bytes must be <= ${MAX_FILE_CONTENT_MAX_BYTES}`)
    }

    const resolved = await resolveFilesystemPath(repositoryPath, requestedPath)
    const file = await buildEntry(resolved.repositoryRoot, resolved.requestedPath, resolved.absolutePath)
    if (file.type !== 'file') {
        throw new FilesystemError(`Path is not a file: ${resolved.requestedPath}`)
    }

    const buffer = await readFile(resolved.absolutePath)
    const truncated = buffer.length > maxBytes
    const contentBuffer = truncated ? buffer.subarray(0, maxBytes) : buffer
    return {
        file,
        encoding,
        content: encoding === 'base64' ? contentBuffer.toString('base64') : decodeUtf8(contentBuffer),
        truncated,
    }
}
