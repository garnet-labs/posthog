export type HogbotTab = 'chat' | 'research' | 'tasks'

export enum MessageRole {
    USER = 'user',
    AGENT = 'agent',
    SYSTEM = 'system',
}

export enum MessageType {
    TEXT = 'text',
    PROACTIVE = 'proactive',
}

export interface HogbotMessage {
    id: string
    role: MessageRole
    type: MessageType
    content: string
    created_at: string
}

export interface ResearchDocument {
    id: string
    filename: string
    title: string
    content: string
    created_at: string
    updated_at: string
}

export interface HogbotSceneLogicProps {
    tabId: string
}
