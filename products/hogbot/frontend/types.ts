export type HogbotTab = 'chat' | 'research' | 'tasks'

/** A file on the sandbox filesystem, returned by the sandbox file listing endpoint. */
export interface SandboxFile {
    path: string
    filename: string
    size: number
    modified_at: string
}

export interface HogbotSceneLogicProps {
    tabId: string
}
