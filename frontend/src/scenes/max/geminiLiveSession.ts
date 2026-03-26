/**
 * Gemini Live API WebSocket wrapper for real-time voice narration.
 *
 * Mic PCM 16kHz in → Gemini → PCM 24kHz audio out.
 * Client-to-server via ephemeral token (v1alpha constrained endpoint).
 *
 * Agent events are injected via toolResponse (NON_BLOCKING function
 * calling with WHEN_IDLE scheduling). This is the only safe way to
 * feed external data into a live audio session without interrupting
 * or crashing the WebSocket.
 */

const WS_URL =
    'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained'
const MODEL = 'gemini-2.5-flash-native-audio-preview-12-2025'

const SYSTEM_INSTRUCTION = `You are the voice interface for Max, PostHog's AI assistant. Your job is to narrate what the agent is doing in a natural, conversational way.

Rules:
- When the user speaks, immediately acknowledge with a brief filler like "Let me look into that..." or "On it..." — keep it under 10 words.
- You have a tool called "agent_update" that receives live status from the PostHog agent. When you get results from it, narrate them naturally.
- When a tool is being called, say something like "I'm checking the data now..." or "Running that query..."
- When results arrive, summarize them conversationally.
- Keep responses concise and natural — you're a voice assistant, not a text reader.
- Match the energy of the user — casual questions get casual answers.
- If the agent is still working, use natural fillers: "Still looking...", "Almost there...", "Just a moment..."
- When narrating final results, be clear and structured but brief.`

export interface GeminiCallbacks {
    onAudio: (pcmBase64: string) => void
    onTurnComplete: () => void
    onInterrupted: () => void
    onError: (msg: string) => void
    onClose: () => void
    onReady: () => void
    onInputTranscription: (text: string) => void
    onOutputTranscription: (text: string) => void
}

export interface GeminiSession {
    sendAudio: (pcmBase64: string) => void
    /**
     * Inject an agent event as a tool response. Uses NON_BLOCKING
     * function calling with WHEN_IDLE scheduling so Gemini narrates
     * the event when it's not speaking, without interrupting anything.
     */
    sendAgentEvent: (text: string) => void
    close: () => void
    isOpen: () => boolean
}

let toolCallCounter = 0

export function connectGemini(token: string, cb: GeminiCallbacks): GeminiSession {
    const ws = new WebSocket(`${WS_URL}?access_token=${encodeURIComponent(token)}`)
    let ready = false

    ws.onopen = () => {
        ws.send(
            JSON.stringify({
                setup: {
                    model: `models/${MODEL}`,
                    generationConfig: {
                        responseModalities: ['AUDIO'],
                        speechConfig: {
                            voiceConfig: {
                                prebuiltVoiceConfig: { voiceName: 'Orus' },
                            },
                        },
                    },
                    systemInstruction: {
                        parts: [{ text: SYSTEM_INSTRUCTION }],
                    },
                    tools: [
                        {
                            functionDeclarations: [
                                {
                                    name: 'agent_update',
                                    description:
                                        'Receives live status updates from the PostHog AI agent. Called automatically when the agent has new information to share.',
                                    behavior: 'NON_BLOCKING',
                                    parameters: {
                                        type: 'OBJECT',
                                        properties: {
                                            status: {
                                                type: 'STRING',
                                                description: 'The agent status update text',
                                            },
                                        },
                                    },
                                },
                            ],
                        },
                    ],
                    inputAudioTranscription: {},
                    outputAudioTranscription: {},
                },
            })
        )
    }

    ws.onmessage = (e) => {
        if (typeof e.data === 'string') {
            try {
                handleMessage(JSON.parse(e.data))
            } catch {
                /* ignore unparseable */
            }
        } else if (e.data instanceof Blob) {
            void e.data.text().then((text) => {
                try {
                    handleMessage(JSON.parse(text))
                } catch {
                    /* ignore */
                }
            })
        }
    }

    function handleMessage(msg: any): void {
        if (msg.setupComplete != null) {
            ready = true
            cb.onReady()
            return
        }

        if (msg.goAway) {
            console.warn('[GeminiLive] goAway', msg.goAway.timeLeft)
        }

        // Handle tool calls from Gemini — auto-respond with empty result
        // since we push data via toolResponse proactively
        if (msg.toolCall?.functionCalls) {
            const responses = msg.toolCall.functionCalls.map((fc: any) => ({
                id: fc.id,
                name: fc.name,
                response: { result: 'ok', scheduling: 'SILENT' },
            }))
            ws.send(JSON.stringify({ toolResponse: { functionResponses: responses } }))
            return
        }

        const sc = msg.serverContent
        if (sc) {
            if (sc.interrupted) {
                cb.onInterrupted()
            }
            if (sc.modelTurn?.parts) {
                for (const p of sc.modelTurn.parts) {
                    if (p.inlineData?.data) {
                        cb.onAudio(p.inlineData.data)
                    }
                }
            }
            if (sc.inputTranscription?.text) {
                cb.onInputTranscription(sc.inputTranscription.text)
            }
            if (sc.outputTranscription?.text) {
                cb.onOutputTranscription(sc.outputTranscription.text)
            }
            if (sc.turnComplete) {
                cb.onTurnComplete()
            }
        }
    }

    ws.onerror = (ev) => {
        console.error('[GeminiLive] error', ev)
        cb.onError('WebSocket error')
    }
    ws.onclose = (ev) => {
        console.warn('[GeminiLive] closed', ev.code, ev.reason)
        cb.onClose()
    }

    return {
        sendAudio(pcmBase64: string) {
            if (ws.readyState === WebSocket.OPEN && ready) {
                ws.send(
                    JSON.stringify({
                        realtimeInput: {
                            audio: { data: pcmBase64, mimeType: 'audio/pcm' },
                        },
                    })
                )
            }
        },

        sendAgentEvent(text: string) {
            if (ws.readyState !== WebSocket.OPEN || !ready) {
                return
            }
            // Inject agent data as a proactive tool response.
            // WHEN_IDLE scheduling means Gemini will narrate it after
            // finishing its current speech — no interruption.
            const id = `agent_${++toolCallCounter}`
            ws.send(
                JSON.stringify({
                    toolResponse: {
                        functionResponses: [
                            {
                                id,
                                name: 'agent_update',
                                response: {
                                    result: text,
                                    scheduling: 'WHEN_IDLE',
                                },
                            },
                        ],
                    },
                })
            )
        },

        close() {
            try {
                ws.close()
            } catch {
                /* */
            }
        },

        isOpen() {
            return ws.readyState === WebSocket.OPEN && ready
        },
    }
}

export function float32ToPcmBase64(f32: Float32Array): string {
    const i16 = new Int16Array(f32.length)
    for (let i = 0; i < f32.length; i++) {
        const s = Math.max(-1, Math.min(1, f32[i]))
        i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    const bytes = new Uint8Array(i16.buffer)
    let bin = ''
    for (let i = 0; i < bytes.length; i++) {
        bin += String.fromCharCode(bytes[i])
    }
    return btoa(bin)
}
