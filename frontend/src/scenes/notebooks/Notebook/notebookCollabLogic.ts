import { actions, afterMount, beforeUnmount, kea, key, listeners, path, props, reducers, selectors } from 'kea'
import { getVersion, receiveTransaction, sendableSteps } from '@tiptap/pm/collab'
import { Step } from '@tiptap/pm/transform'

import api from 'lib/api'
import { JSONContent, TTEditor } from 'lib/components/RichContentEditor/types'

import type { notebookCollabLogicType } from './notebookCollabLogicType'

const SAVE_DEBOUNCE_MS = 5000
const RECONNECT_DELAY_MS = 2000
const MAX_RECONNECT_DELAY_MS = 30000

export type NotebookCollabProps = {
    shortId: string
}

export type CollabStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export const notebookCollabLogic = kea<notebookCollabLogicType>([
    props({} as NotebookCollabProps),
    path((key) => ['scenes', 'notebooks', 'Notebook', 'notebookCollabLogic', key]),
    key(({ shortId }) => shortId),

    actions({
        // Session management
        joinSession: true,
        sessionJoined: (clientId: string, version: number, doc: JSONContent) => ({ clientId, version, doc }),
        setStatus: (status: CollabStatus) => ({ status }),

        // Step sync
        sendSteps: true,
        stepsAccepted: (version: number) => ({ version }),
        stepsRejected: (version: number, steps: Record<string, any>[]) => ({ version, steps }),
        receiveSteps: (steps: Record<string, any>[], version: number) => ({ steps, version }),

        // Editor binding
        bindEditor: (editor: TTEditor) => ({ editor }),
        unbindEditor: true,

        // Persistence
        scheduleSave: true,
        saveDocument: true,

        // SSE
        connectSSE: true,
        disconnectSSE: true,

        // Error handling
        setError: (error: string) => ({ error }),
        clearError: true,
    }),

    reducers({
        status: [
            'disconnected' as CollabStatus,
            {
                setStatus: (_, { status }) => status,
                sessionJoined: () => 'connected' as CollabStatus,
            },
        ],
        clientId: [
            null as string | null,
            {
                sessionJoined: (_, { clientId }) => clientId,
            },
        ],
        error: [
            null as string | null,
            {
                setError: (_, { error }) => error,
                clearError: () => null,
                sessionJoined: () => null,
            },
        ],
        isSending: [
            false,
            {
                sendSteps: () => true,
                stepsAccepted: () => false,
                stepsRejected: () => false,
            },
        ],
    }),

    selectors({
        isCollaborating: [(s) => [s.status], (status): boolean => status === 'connected'],
    }),

    listeners(({ values, actions, cache, props }) => ({
        joinSession: async () => {
            actions.setStatus('connecting')
            try {
                const response = await api.create(
                    `api/projects/@current/notebooks/${props.shortId}/collab/join/`
                )
                actions.sessionJoined(response.client_id, response.version, response.doc)
            } catch (e: any) {
                console.error('Failed to join collab session', e)
                actions.setError('Failed to join collaboration session')
                actions.setStatus('error')
            }
        },

        sessionJoined: () => {
            actions.connectSSE()
        },

        bindEditor: ({ editor }) => {
            cache.editor = editor

            // Listen for transactions to detect local changes
            cache.transactionHandler = () => {
                if (values.isCollaborating && !cache.isSending) {
                    actions.sendSteps()
                }
            }
        },

        unbindEditor: () => {
            cache.editor = null
            cache.transactionHandler = null
        },

        sendSteps: async (_, breakpoint) => {
            const editor = cache.editor as TTEditor | null
            if (!editor || !values.clientId) {
                return
            }

            // Small debounce to batch rapid edits
            await breakpoint(50)

            const state = editor.state
            const sendable = sendableSteps(state)
            if (!sendable) {
                return
            }

            try {
                const response = await api.create(
                    `api/projects/@current/notebooks/${props.shortId}/collab/steps/`,
                    {
                        client_id: values.clientId,
                        version: sendable.version,
                        steps: sendable.steps.map((step) => step.toJSON()),
                    }
                )

                if (response.accepted) {
                    actions.stepsAccepted(response.version)
                    actions.scheduleSave()
                } else {
                    actions.stepsRejected(response.version, response.steps)
                }
            } catch (e: any) {
                console.error('Failed to send steps', e)
                // Retry after a delay
                setTimeout(() => actions.sendSteps(), 1000)
            }
        },

        stepsAccepted: () => {
            // The collab plugin tracks confirmed steps internally.
            // When the SSE sends back confirmation, receiveTransaction is called.
            // After confirmation, check if there are more steps to send.
            const editor = cache.editor as TTEditor | null
            if (!editor) {
                return
            }
            const sendable = sendableSteps(editor.state)
            if (sendable) {
                actions.sendSteps()
            }
        },

        stepsRejected: ({ steps }) => {
            // Rebase: apply the missed steps from the server, then retry our pending steps
            const editor = cache.editor as TTEditor | null
            if (!editor || !steps.length) {
                return
            }

            applyRemoteSteps(editor, steps)

            // After rebasing, try sending our steps again
            const sendable = sendableSteps(editor.state)
            if (sendable) {
                actions.sendSteps()
            }
        },

        receiveSteps: ({ steps }) => {
            const editor = cache.editor as TTEditor | null
            if (!editor || !steps.length) {
                return
            }

            applyRemoteSteps(editor, steps)

            // After receiving remote steps, check if we have local changes to send
            const sendable = sendableSteps(editor.state)
            if (sendable) {
                actions.sendSteps()
            }
        },

        connectSSE: () => {
            if (cache.eventSource) {
                cache.eventSource.close()
            }

            const clientId = values.clientId
            if (!clientId) {
                return
            }

            cache.reconnectAttempts = 0
            const url = `/api/projects/@current/notebooks/${props.shortId}/collab/events/?client_id=${encodeURIComponent(clientId)}`

            const connectEventSource = (): void => {
                const eventSource = new EventSource(url)
                cache.eventSource = eventSource

                eventSource.addEventListener('connected', () => {
                    cache.reconnectAttempts = 0
                })

                eventSource.addEventListener('steps', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data)
                        actions.receiveSteps(data.steps, data.version)
                    } catch (e) {
                        console.error('Failed to parse SSE steps event', e)
                    }
                })

                eventSource.addEventListener('confirm', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data)
                        // Confirmation that our steps were accepted
                        // The collab plugin handles this via sendableSteps returning null
                        actions.stepsAccepted(data.version)
                    } catch (e) {
                        console.error('Failed to parse SSE confirm event', e)
                    }
                })

                eventSource.onerror = () => {
                    eventSource.close()
                    cache.eventSource = null

                    // Reconnect with exponential backoff
                    cache.reconnectAttempts = (cache.reconnectAttempts || 0) + 1
                    const delay = Math.min(
                        RECONNECT_DELAY_MS * Math.pow(2, cache.reconnectAttempts - 1),
                        MAX_RECONNECT_DELAY_MS
                    )

                    cache.reconnectTimeout = setTimeout(() => {
                        if (values.status === 'connected') {
                            connectEventSource()
                        }
                    }, delay)
                }
            }

            connectEventSource()
        },

        disconnectSSE: () => {
            if (cache.eventSource) {
                cache.eventSource.close()
                cache.eventSource = null
            }
            if (cache.reconnectTimeout) {
                clearTimeout(cache.reconnectTimeout)
                cache.reconnectTimeout = null
            }
        },

        scheduleSave: async (_, breakpoint) => {
            await breakpoint(SAVE_DEBOUNCE_MS)
            actions.saveDocument()
        },

        saveDocument: async () => {
            const editor = cache.editor as TTEditor | null
            if (!editor || !values.clientId) {
                return
            }

            const version = getVersion(editor.state)
            const content = editor.getJSON()
            const textContent = editor.getText()

            try {
                await api.create(
                    `api/projects/@current/notebooks/${props.shortId}/collab/save/`,
                    {
                        content,
                        version,
                        text_content: textContent,
                    }
                )
            } catch (e: any) {
                console.error('Failed to persist notebook', e)
            }
        },
    })),

    afterMount(() => {
        // Join will be triggered when the feature flag is active and the editor is ready
    }),

    beforeUnmount(({ actions, cache }) => {
        // Save before unmounting
        const editor = cache.editor as TTEditor | null
        if (editor && cache.clientId) {
            actions.saveDocument()
        }
        actions.disconnectSSE()
        actions.unbindEditor()
        if (cache.reconnectTimeout) {
            clearTimeout(cache.reconnectTimeout)
        }
    }),
])

/**
 * Apply remote steps from the server to the editor.
 */
function applyRemoteSteps(editor: TTEditor, stepsJson: Record<string, any>[]): void {
    const schema = editor.state.schema
    try {
        const steps = stepsJson.map((stepJson) => Step.fromJSON(schema, stepJson))
        // All remote steps get a generic client ID - the collab plugin uses this
        // to distinguish local from remote changes
        const clientIDs = steps.map(() => 'server')
        const tr = receiveTransaction(editor.state, steps, clientIDs, {
            mapSelectionBackward: true,
        })
        editor.view.dispatch(tr)
    } catch (e) {
        console.error('Failed to apply remote steps', e)
    }
}
