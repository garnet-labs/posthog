/**
 * Minimal Gemini Live API WebSocket wrapper.
 * Mic PCM 16kHz in → Gemini → PCM 24kHz audio out.
 * Client-to-server via ephemeral token (v1alpha constrained endpoint).
 */

const WS_URL =
    'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained'
const MODEL = 'gemini-2.5-flash-native-audio-preview-12-2025'

export interface GeminiCallbacks {
    onAudio: (pcmBase64: string) => void
    onTurnComplete: () => void
    onInterrupted: () => void
    onError: (msg: string) => void
    onClose: () => void
    onReady: () => void
}

export interface GeminiSession {
    sendAudio: (pcmBase64: string) => void
    close: () => void
    isOpen: () => boolean
}

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
                },
            })
        )
        ready = true
        cb.onReady()
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
            return
        }

        const sc = msg.serverContent
        if (!sc) {
            return
        }

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
        if (sc.turnComplete) {
            cb.onTurnComplete()
        }
    }

    ws.onerror = () => cb.onError('WebSocket error')
    ws.onclose = () => cb.onClose()

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
