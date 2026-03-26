import { actions, events, kea, listeners, path, reducers } from 'kea'

import api from 'lib/api'
import { lemonToast } from 'lib/lemon-ui/LemonToast'

import { connectGemini, float32ToPcmBase64 } from './geminiLiveSession'
import type { GeminiSession } from './geminiLiveSession'
import { maxLogic } from './maxLogic'
import type { voiceLogicType } from './voiceLogicType'

const MIC_RATE = 16000
const MIC_BUF = 4096

export const voiceLogic = kea<voiceLogicType>([
    path(['scenes', 'max', 'voiceLogic']),

    actions({
        startRecording: (tabId: string) => ({ tabId }),
        stopRecording: true,
        setRecording: (recording: boolean) => ({ recording }),
        setConnecting: (connecting: boolean) => ({ connecting }),
        setMicPermissionDenied: (denied: boolean) => ({ denied }),
        setVoiceModeEnabled: (enabled: boolean) => ({ enabled }),
        setVoiceModeFullscreen: (fullscreen: boolean) => ({ fullscreen }),
        setActiveTabId: (tabId: string | null) => ({ tabId }),
        playResponse: (text: string) => ({ text }),
        setPlaybackActive: (active: boolean) => ({ active }),
        stopPlayback: true,
        setInputAmplitude: (amplitude: number) => ({ amplitude }),
        setIsSpeaking: (isSpeaking: boolean) => ({ isSpeaking }),
        setMouthOpenness: (openness: number) => ({ openness }),
        setIsMouthOpen: (isMouthOpen: boolean) => ({ isMouthOpen }),
        setSilenceMs: (silenceMs: number) => ({ silenceMs }),
        disableVoiceMode: true,
        enterVoiceMode: (tabId: string) => ({ tabId }),
        exitVoiceMode: true,
        setOrbPointerDown: (down: boolean) => ({ down }),
        setTtsLoading: (loading: boolean) => ({ loading }),
        resetStreamingTtsOffsets: true,
        syncAssistantStreamingTts: (payload: {
            traceId: string | null
            messageId: string | undefined
            content: string
            isFinal: boolean
        }) => payload,
        playToolCallNarration: (payload: { dedupeKey: string; sentence: string }) => payload,
        enqueueToolWaitFill: true,
        muteMic: true,
        unmuteMic: true,
    }),

    reducers({
        recording: [false, { setRecording: (_, { recording }) => recording }],
        connecting: [false, { setConnecting: (_, { connecting }) => connecting }],
        playbackActive: [false, { setPlaybackActive: (_, { active }) => active }],
        inputAmplitude: [0, { setInputAmplitude: (_, { amplitude }) => amplitude }],
        isSpeaking: [false, { setIsSpeaking: (_, { isSpeaking }) => isSpeaking }],
        mouthOpenness: [0, { setMouthOpenness: (_, { openness }) => openness }],
        isMouthOpen: [false, { setIsMouthOpen: (_, { isMouthOpen }) => isMouthOpen }],
        silenceMs: [0, { setSilenceMs: (_, { silenceMs }) => silenceMs }],
        voiceModeEnabled: [
            false,
            {
                setVoiceModeEnabled: (_, { enabled }) => enabled,
                disableVoiceMode: () => false,
                enterVoiceMode: () => true,
                exitVoiceMode: () => false,
            },
        ],
        voiceModeFullscreen: [
            false,
            {
                setVoiceModeFullscreen: (_, { fullscreen }) => fullscreen,
                enterVoiceMode: () => true,
                exitVoiceMode: () => false,
            },
        ],
        micPermissionDenied: [false, { setMicPermissionDenied: (_, { denied }) => denied }],
        activeTabId: [null as string | null, { setActiveTabId: (_, { tabId }) => tabId }],
        orbPointerDown: [
            false,
            {
                setOrbPointerDown: (_, { down }) => down,
                stopRecording: () => false,
                exitVoiceMode: () => false,
                disableVoiceMode: () => false,
                enterVoiceMode: () => false,
            },
        ],
        ttsLoading: [
            false,
            {
                setTtsLoading: (_, { loading }) => loading,
                stopRecording: () => false,
                stopPlayback: () => false,
                exitVoiceMode: () => false,
                disableVoiceMode: () => false,
                enterVoiceMode: () => false,
            },
        ],
        micMuted: [
            false,
            {
                muteMic: () => true,
                unmuteMic: () => false,
                stopRecording: () => false,
                exitVoiceMode: () => false,
                enterVoiceMode: () => false,
            },
        ],
    }),

    listeners(({ actions, values, cache }) => ({
        startRecording: async ({ tabId }) => {
            actions.setActiveTabId(tabId)
            actions.setMicPermissionDenied(false)
            actions.setConnecting(true)

            // 1. Mic permission
            let stream: MediaStream
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        sampleRate: MIC_RATE,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true,
                    },
                })
            } catch {
                actions.setMicPermissionDenied(true)
                actions.setConnecting(false)
                return
            }

            // 2. Playback AudioContext at Gemini's output rate to avoid pitch shift
            if (!cache.audioCtx || (cache.audioCtx as AudioContext).state === 'closed') {
                cache.audioCtx = new AudioContext({ sampleRate: 24000 })
            }
            if ((cache.audioCtx as AudioContext).state === 'suspended') {
                await (cache.audioCtx as AudioContext).resume()
            }
            await ensurePlaybackWorklet(cache)

            // 3. Ephemeral token
            let token: string
            try {
                token = (await api.conversations.geminiLiveToken()).token
            } catch {
                stream.getTracks().forEach((t) => t.stop())
                actions.setConnecting(false)
                lemonToast.error('Failed to start voice mode.')
                return
            }

            cache.mediaStream = stream
            cache.errored = false
            cache.lastNarrationTraceId = null as string | null
            cache.lastNarrationContent = '' as string
            cache.pendingTranscription = '' as string

            // 4. Connect to Gemini
            const session = connectGemini(token, {
                onReady() {
                    void startMic(cache, stream, session, actions)
                        .then(() => {
                            actions.setConnecting(false)
                            actions.setRecording(true)
                            actions.setVoiceModeEnabled(true)
                        })
                        .catch(() => {
                            cache.errored = true
                            actions.stopRecording()
                            lemonToast.error('Failed to start microphone streaming.')
                        })
                },
                onAudio(b64) {
                    playChunk(cache, actions, b64)
                },
                onTurnComplete() {
                    // Flush pending user transcription to the agent
                    clearTimeout(cache.transcriptionDebounce as ReturnType<typeof setTimeout>)
                    const pending = (cache.pendingTranscription as string).trim()
                    if (pending) {
                        cache.pendingTranscription = ''
                        sendToAgent(pending, values.activeTabId)
                    }

                    setTimeout(() => {
                        const lastAt = (cache.lastPlaybackChunkAt as number | undefined) ?? 0
                        if (performance.now() - lastAt >= 500) {
                            stopVisuals(cache, actions)
                            actions.setPlaybackActive(false)
                        }
                    }, 300)
                },
                onInterrupted() {
                    flushPlayback(cache)
                    stopVisuals(cache, actions)
                    actions.setPlaybackActive(false)
                },
                onInputTranscription(text) {
                    // Debounce transcription and send to agent after speech pause
                    const accumulated = ((cache.pendingTranscription as string) || '') + ' ' + text
                    cache.pendingTranscription = accumulated.trim()

                    clearTimeout(cache.transcriptionDebounce as ReturnType<typeof setTimeout>)
                    cache.transcriptionDebounce = setTimeout(() => {
                        const p = (cache.pendingTranscription as string).trim()
                        if (p) {
                            cache.pendingTranscription = ''
                            sendToAgent(p, values.activeTabId)
                        }
                    }, 800)
                },
                onOutputTranscription() {
                    // Could display in UI if needed
                },
                onError(msg) {
                    cache.errored = true
                    if (values.recording || values.connecting) {
                        actions.stopRecording()
                        lemonToast.error(`Voice error: ${msg}`)
                    }
                },
                onClose() {
                    if (!cache.errored && cache.session === session && (values.recording || values.connecting)) {
                        cache.errored = true
                        actions.stopRecording()
                        lemonToast.warning('Voice session ended.')
                    }
                },
            })
            cache.session = session
        },

        stopRecording: () => {
            ;(cache.session as GeminiSession | undefined)?.close()
            cache.session = null
            clearTimeout(cache.transcriptionDebounce as ReturnType<typeof setTimeout>)

            cancelAnimationFrame(cache.micRaf as number)
            cache.micRaf = null
            ;(cache.captureNode as AudioWorkletNode | undefined)?.disconnect()
            ;(cache.micSource as MediaStreamAudioSourceNode | undefined)?.disconnect()
            const recCtx = cache.recCtx as AudioContext | undefined
            if (recCtx) {
                void recCtx.close()
            }
            cache.captureNode = null
            cache.micSource = null
            cache.recCtx = null
            ;(cache.mediaStream as MediaStream | undefined)?.getTracks().forEach((t) => t.stop())
            cache.mediaStream = null

            actions.setRecording(false)
            actions.setConnecting(false)
            actions.setInputAmplitude(0)
            actions.setIsSpeaking(false)
            actions.setMouthOpenness(0)
            actions.setIsMouthOpen(false)
        },

        enterVoiceMode: ({ tabId }) => {
            actions.setActiveTabId(tabId)
            actions.startRecording(tabId)
        },
        exitVoiceMode: () => {
            if (values.recording || values.connecting) {
                actions.stopRecording()
            }
            if (values.playbackActive) {
                actions.stopPlayback()
            }
        },
        stopPlayback: () => {
            flushPlayback(cache)
            stopVisuals(cache, actions)
            actions.setPlaybackActive(false)
        },
        setOrbPointerDown: ({ down }) => {
            cache.orbPointerDown = down
        },

        muteMic: () => {
            // Disable the mic track so no audio is captured/sent, but keep
            // the Gemini session alive so it can keep speaking.
            const stream = cache.mediaStream as MediaStream | undefined
            if (stream) {
                for (const track of stream.getAudioTracks()) {
                    track.enabled = false
                }
            }
            actions.setInputAmplitude(0)
            actions.setIsSpeaking(false)
            actions.setMouthOpenness(0)
            actions.setIsMouthOpen(false)
        },

        unmuteMic: () => {
            const stream = cache.mediaStream as MediaStream | undefined
            if (stream) {
                for (const track of stream.getAudioTracks()) {
                    track.enabled = true
                }
            }
        },

        /**
         * Agent streams assistant text — send directly to Gemini via
         * toolResponse (NON_BLOCKING, WHEN_IDLE scheduling). Safe to
         * call at any time without crashing the session.
         */
        syncAssistantStreamingTts: ({ traceId, content, isFinal }) => {
            const session = cache.session as GeminiSession | undefined
            if (!session?.isOpen()) {
                return
            }

            const prevTraceId = cache.lastNarrationTraceId as string | null
            const prevContent = cache.lastNarrationContent as string

            if (traceId !== prevTraceId) {
                cache.lastNarrationTraceId = traceId
                cache.lastNarrationContent = ''
            }

            const newContent = traceId === prevTraceId ? content.slice(prevContent.length) : content
            cache.lastNarrationContent = content

            if (newContent.trim()) {
                const prefix = isFinal ? 'Agent final response' : 'Agent reasoning'
                session.sendAgentEvent(`${prefix}: ${newContent}`)
            }

            if (isFinal) {
                cache.lastNarrationTraceId = null
                cache.lastNarrationContent = ''
            }
        },

        playToolCallNarration: ({ sentence }) => {
            const session = cache.session as GeminiSession | undefined
            if (!session?.isOpen()) {
                return
            }
            session.sendAgentEvent(`Agent tool call: ${sentence}`)
        },

        resetStreamingTtsOffsets: () => {
            cache.lastNarrationTraceId = null
            cache.lastNarrationContent = ''
        },

        enqueueToolWaitFill: () => {
            const session = cache.session as GeminiSession | undefined
            if (!session?.isOpen()) {
                return
            }
            session.sendAgentEvent('The agent is still working on the request. Please let the user know.')
        },

        playResponse: () => {},

        setPlaybackActive: ({ active }) => {
            if (!active) {
                stopVisuals(cache, actions)
            }
        },
    })),

    events(({ values, actions }) => ({
        beforeUnmount: () => {
            if (values.recording || values.connecting) {
                actions.stopRecording()
            }
        },
    })),
])

// ── Send user transcription to the PostHog agent ──

function sendToAgent(text: string, tabId: string | null): void {
    if (!tabId || !text.trim()) {
        return
    }
    try {
        const logic = maxLogic.findMounted({ tabId })
        if (logic) {
            logic.actions.askMax(text, true)
        }
    } catch {
        // maxLogic not mounted for this tab
    }
}

// ── Mic capture via AudioWorklet ──

async function startMic(cache: any, stream: MediaStream, session: GeminiSession, actions: any): Promise<void> {
    const recCtx = new AudioContext({ sampleRate: MIC_RATE })
    cache.recCtx = recCtx

    const src = recCtx.createMediaStreamSource(stream)
    const analyser = recCtx.createAnalyser()
    analyser.fftSize = 2048
    analyser.smoothingTimeConstant = 0.2

    const workletCode = `class C extends AudioWorkletProcessor {
        constructor() { super(); this.buf = new Float32Array(${MIC_BUF}); this.idx = 0 }
        process(inputs) {
            const ch = inputs[0]?.[0]
            if (!ch) return true
            for (let i = 0; i < ch.length; i++) {
                this.buf[this.idx++] = ch[i]
                if (this.idx >= ${MIC_BUF}) {
                    this.port.postMessage({ type: 'audio', data: this.buf.slice() })
                    this.idx = 0
                }
            }
            return true
        }
    }
    registerProcessor('mic-capture', C)`

    const url = URL.createObjectURL(new Blob([workletCode], { type: 'application/javascript' }))
    await recCtx.audioWorklet.addModule(url)
    URL.revokeObjectURL(url)

    const node = new AudioWorkletNode(recCtx, 'mic-capture')
    src.connect(analyser)
    src.connect(node)

    node.port.onmessage = (event: MessageEvent<{ type: string; data: Float32Array }>) => {
        if (session.isOpen() && event.data?.type === 'audio') {
            session.sendAudio(float32ToPcmBase64(event.data.data))
        }
    }

    cache.captureNode = node
    cache.micSource = src
    cache.analyser = analyser
    cache.analyserBuf = new Uint8Array(analyser.fftSize)
    cache.hangover = 0
    cache.lastSound = performance.now()
    cache.smoothOpen = 0
    cache.mouthOpen = false

    // Amplitude animation loop for hedgehog
    const loop = (): void => {
        if (!cache.analyser || !session.isOpen()) {
            return
        }
        const a = cache.analyser as AnalyserNode
        const d = cache.analyserBuf as Uint8Array
        a.getByteTimeDomainData(d as unknown as Uint8Array<ArrayBuffer>)

        let sq = 0
        for (let i = 0; i < d.length; i++) {
            const x = (d[i] - 128) / 128
            sq += x * x
        }
        const rms = Math.sqrt(sq / d.length)
        const now = performance.now()

        if (rms >= 0.025) {
            cache.hangover = now + 150
            cache.lastSound = now
        }
        const speaking = now <= (cache.hangover as number)
        const silenceMs = Math.max(0, now - (cache.lastSound as number))

        const norm = Math.max(0, Math.min(1, (rms - 0.015) / 0.105))
        const sm = (cache.smoothOpen as number) + 0.15 * (norm - (cache.smoothOpen as number))
        cache.smoothOpen = sm
        const wasOpen = cache.mouthOpen as boolean
        const isOpen = wasOpen ? sm >= 0.1 : sm >= 0.18
        cache.mouthOpen = isOpen

        actions.setInputAmplitude(rms)
        actions.setIsSpeaking(speaking)
        actions.setMouthOpenness(sm)
        actions.setIsMouthOpen(isOpen)
        actions.setSilenceMs(silenceMs)

        cache.micRaf = requestAnimationFrame(loop)
    }
    cache.micRaf = requestAnimationFrame(loop)
}

// ── Playback via AudioWorklet ──

async function ensurePlaybackWorklet(cache: any): Promise<void> {
    if (cache.playbackWorklet) {
        return
    }

    const ctx = cache.audioCtx as AudioContext

    const workletCode = `class P extends AudioWorkletProcessor {
        constructor() {
            super()
            this.q = []
            this.port.onmessage = (e) => {
                if (e.data === 'flush') this.q = []
                else if (e.data instanceof Float32Array) this.q.push(e.data)
            }
        }
        process(_, outputs) {
            const ch = outputs[0]?.[0]
            if (!ch) return true
            let oi = 0
            while (oi < ch.length && this.q.length > 0) {
                const buf = this.q[0]
                if (!buf || buf.length === 0) { this.q.shift(); continue }
                const n = Math.min(ch.length - oi, buf.length)
                for (let i = 0; i < n; i++) ch[oi++] = buf[i]
                if (n < buf.length) this.q[0] = buf.slice(n)
                else this.q.shift()
            }
            while (oi < ch.length) ch[oi++] = 0
            return true
        }
    }
    registerProcessor('pcm-playback', P)`

    const url = URL.createObjectURL(new Blob([workletCode], { type: 'application/javascript' }))
    await ctx.audioWorklet.addModule(url)
    URL.revokeObjectURL(url)

    const node = new AudioWorkletNode(ctx, 'pcm-playback')
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 2048
    analyser.smoothingTimeConstant = 0.2
    node.connect(analyser)
    analyser.connect(ctx.destination)

    cache.playbackWorklet = node
    cache.pbAnalyser = analyser
    cache.pbData = new Uint8Array(analyser.fftSize)
    cache.pbSmooth = 0
    cache.pbOpen = false
}

function playChunk(cache: any, actions: any, b64: string): void {
    const node = cache.playbackWorklet as AudioWorkletNode | undefined
    if (!node) {
        return
    }

    node.port.postMessage(decodePcmBase64ToFloat32(b64))
    cache.lastPlaybackChunkAt = performance.now()

    if (!cache.pbVisual) {
        actions.setPlaybackActive(true)
        cache.pbVisual = true

        const loop = (): void => {
            if (!cache.pbVisual) {
                return
            }
            const an = cache.pbAnalyser as AnalyserNode | undefined
            const d = cache.pbData as Uint8Array | undefined
            if (!an || !d) {
                return
            }
            an.getByteTimeDomainData(d as unknown as Uint8Array<ArrayBuffer>)
            let sq = 0
            for (let i = 0; i < d.length; i++) {
                const x = (d[i] - 128) / 128
                sq += x * x
            }
            const rms = Math.sqrt(sq / d.length)
            const norm = Math.max(0, Math.min(1, (rms - 0.015) / 0.105))
            const sm = (cache.pbSmooth as number) + 0.15 * (norm - (cache.pbSmooth as number))
            cache.pbSmooth = sm
            const wasOpen = cache.pbOpen as boolean
            const isOpen = wasOpen ? sm >= 0.1 : sm >= 0.18
            cache.pbOpen = isOpen
            actions.setMouthOpenness(sm)
            actions.setIsMouthOpen(isOpen)
            cache.pbRaf = requestAnimationFrame(loop)
        }
        cache.pbRaf = requestAnimationFrame(loop)
    }
}

function flushPlayback(cache: any): void {
    const node = cache.playbackWorklet as AudioWorkletNode | undefined
    if (node) {
        node.port.postMessage('flush')
    }
}

function stopVisuals(cache: any, actions: any): void {
    cache.pbVisual = false
    cancelAnimationFrame(cache.pbRaf as number)
    cache.pbRaf = null
    actions.setMouthOpenness(0)
    actions.setIsMouthOpen(false)
}

function decodePcmBase64ToFloat32(b64: string): Float32Array {
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) {
        bytes[i] = bin.charCodeAt(i)
    }
    const i16 = new Int16Array(bytes.buffer)
    const f32 = new Float32Array(i16.length)
    for (let i = 0; i < i16.length; i++) {
        f32[i] = i16[i] / 32768
    }
    return f32
}
