import { actions, events, kea, listeners, path, reducers } from 'kea'

import api from 'lib/api'
import { lemonToast } from 'lib/lemon-ui/LemonToast'

import { stripMarkdown } from '~/lib/utils/stripMarkdown'

import { maxLogic } from './maxLogic'
import { maxThreadLogic } from './maxThreadLogic'
import type { voiceLogicType } from './voiceLogicType'

const ELEVENLABS_WSS = 'wss://api.elevenlabs.io/v1/speech-to-text/realtime'
const STT_SAMPLE_RATE = 16000
const STT_BUFFER_SIZE = 4096

function float32ToInt16Base64(float32: Float32Array): string {
    const int16 = new Int16Array(float32.length)
    for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]))
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    const bytes = new Uint8Array(int16.buffer)
    let binary = ''
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i])
    }
    return btoa(binary)
}

export const voiceLogic = kea<voiceLogicType>([
    path(['scenes', 'max', 'voiceLogic']),

    actions({
        startRecording: (tabId: string) => ({ tabId }),
        stopRecording: true,
        setRecording: (recording: boolean) => ({ recording }),
        setConnecting: (connecting: boolean) => ({ connecting }),
        setMicPermissionDenied: (denied: boolean) => ({ denied }),
        setVoiceModeEnabled: (enabled: boolean) => ({ enabled }),
        setActiveTabId: (tabId: string | null) => ({ tabId }),
        playResponse: (text: string) => ({ text }),
        setPlaybackActive: (active: boolean) => ({ active }),
        stopPlayback: true,
        disableVoiceMode: true,
    }),

    reducers({
        recording: [false, { setRecording: (_, { recording }) => recording }],
        connecting: [false, { setConnecting: (_, { connecting }) => connecting }],
        playbackActive: [false, { setPlaybackActive: (_, { active }) => active }],
        voiceModeEnabled: [
            false,
            {
                setVoiceModeEnabled: (_, { enabled }) => enabled,
                disableVoiceMode: () => false,
            },
        ],
        micPermissionDenied: [false, { setMicPermissionDenied: (_, { denied }) => denied }],
        activeTabId: [null as string | null, { setActiveTabId: (_, { tabId }) => tabId }],
    }),

    listeners(({ actions, values, cache }) => ({
        startRecording: async ({ tabId }) => {
            actions.setActiveTabId(tabId)
            actions.setMicPermissionDenied(false)
            actions.setConnecting(true)

            let stream: MediaStream
            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            } catch {
                actions.setMicPermissionDenied(true)
                actions.setConnecting(false)
                return
            }

            // Unlock AudioContext on user gesture for later TTS auto-play
            if (!cache.audioContext) {
                cache.audioContext = new AudioContext()
            }
            if (cache.audioContext.state === 'suspended') {
                await cache.audioContext.resume()
            }

            // Get single-use token for client-side WebSocket auth
            let token: string
            try {
                const resp = await api.conversations.sttToken()
                token = resp.token
            } catch {
                stream.getTracks().forEach((t) => t.stop())
                actions.setConnecting(false)
                lemonToast.error('Failed to start voice input.')
                return
            }

            cache.mediaStream = stream
            cache.committedParts = [] as string[]
            cache.currentPartial = ''

            const params = new URLSearchParams({
                token,
                model_id: 'scribe_v2_realtime',
                commit_strategy: 'vad',
                audio_format: `pcm_${STT_SAMPLE_RATE}`,
            })
            const ws = new WebSocket(`${ELEVENLABS_WSS}?${params.toString()}`)
            cache.sttWebSocket = ws

            ws.onopen = () => {
                // Create a dedicated AudioContext at the STT sample rate for recording
                const recordingCtx = new AudioContext({ sampleRate: STT_SAMPLE_RATE })
                cache.recordingAudioContext = recordingCtx

                const source = recordingCtx.createMediaStreamSource(stream)
                // ScriptProcessorNode needs a path to destination to fire onaudioprocess.
                // Route through a silent gain node so mic audio doesn't play through speakers.
                const processor = recordingCtx.createScriptProcessor(STT_BUFFER_SIZE, 1, 1)
                const silentGain = recordingCtx.createGain()
                silentGain.gain.value = 0

                source.connect(processor)
                processor.connect(silentGain)
                silentGain.connect(recordingCtx.destination)

                processor.onaudioprocess = (e: AudioProcessingEvent) => {
                    if (ws.readyState !== WebSocket.OPEN) {
                        return
                    }
                    const float32 = e.inputBuffer.getChannelData(0)
                    ws.send(
                        JSON.stringify({
                            message_type: 'input_audio_chunk',
                            audio_base_64: float32ToInt16Base64(float32),
                            commit: false,
                            sample_rate: STT_SAMPLE_RATE,
                        })
                    )
                }

                cache.scriptProcessor = processor
                cache.recordingSource = source
                cache.silentGain = silentGain

                actions.setConnecting(false)
                actions.setRecording(true)
                actions.setVoiceModeEnabled(true)
            }

            ws.onmessage = (event: MessageEvent) => {
                const data = JSON.parse(event.data)
                const currentTabId = values.activeTabId
                if (!currentTabId) {
                    return
                }
                const mounted = maxLogic.findMounted({ tabId: currentTabId })

                if (data.message_type === 'partial_transcript') {
                    cache.currentPartial = data.text || ''
                } else if (data.message_type === 'committed_transcript') {
                    if (data.text) {
                        cache.committedParts.push(data.text)
                    }
                    cache.currentPartial = ''
                } else if (data.error) {
                    // ElevenLabs error events (auth_error, quota_exceeded, etc.) arrive as messages, not WS errors
                    lemonToast.error(`Voice transcription error: ${data.error}`)
                    return
                } else {
                    return
                }

                const parts = cache.committedParts as string[]
                const partial = cache.currentPartial as string
                const fullText = [...parts, partial].filter(Boolean).join(' ')
                mounted?.actions.setQuestion(fullText)
            }

            ws.onerror = () => {
                if (values.recording || values.connecting) {
                    actions.stopRecording()
                    lemonToast.error('Voice transcription connection failed.')
                }
            }

            // Server-initiated close (session timeout, quota, etc.) — stop recording if user didn't initiate
            ws.onclose = () => {
                if (cache.sttWebSocket === ws && (values.recording || values.connecting)) {
                    actions.stopRecording()
                }
            }
        },

        stopRecording: () => {
            // Close WebSocket
            const ws = cache.sttWebSocket as WebSocket | undefined
            if (ws) {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.close()
                } else if (ws.readyState === WebSocket.CONNECTING) {
                    ws.onopen = () => ws.close()
                }
                cache.sttWebSocket = null
            }

            // Disconnect audio processing
            const processor = cache.scriptProcessor as ScriptProcessorNode | undefined
            processor?.disconnect()
            cache.scriptProcessor = null
            const source = cache.recordingSource as MediaStreamAudioSourceNode | undefined
            source?.disconnect()
            cache.recordingSource = null
            const silentGain = cache.silentGain as GainNode | undefined
            silentGain?.disconnect()
            cache.silentGain = null
            const recordingCtx = cache.recordingAudioContext as AudioContext | undefined
            if (recordingCtx) {
                void recordingCtx.close()
                cache.recordingAudioContext = null
            }

            // Release mic
            const mediaStream = cache.mediaStream as MediaStream | undefined
            mediaStream?.getTracks().forEach((t) => t.stop())
            cache.mediaStream = null

            // Build final transcript from committed segments + any trailing partial
            const committedParts = (cache.committedParts as string[]) || []
            const currentPartial = (cache.currentPartial as string) || ''
            const finalText = [...committedParts, currentPartial].filter(Boolean).join(' ').trim()
            cache.committedParts = []
            cache.currentPartial = ''

            const wasRecording = values.recording
            actions.setRecording(false)
            actions.setConnecting(false)

            if (finalText && wasRecording) {
                const tabId = values.activeTabId
                if (!tabId) {
                    return
                }
                const mountedMaxLogic = maxLogic.findMounted({ tabId })
                mountedMaxLogic?.actions.setQuestion(finalText)

                const mountedThreadLogic = maxThreadLogic.findMounted()
                mountedThreadLogic?.actions.askMax(finalText)
            } else if (!finalText && wasRecording) {
                lemonToast.warning('No speech detected. Try again.')
            }
        },

        playResponse: async ({ text }) => {
            if (!text) {
                return
            }

            // Stop any existing playback first
            const existingSource = cache.currentSource as AudioBufferSourceNode | undefined
            if (existingSource) {
                try {
                    existingSource.stop()
                } catch {
                    // Already stopped
                }
                cache.currentSource = null
            }

            // Strip markdown for cleaner speech
            const plainText = stripMarkdown(text).slice(0, 5000)
            if (!plainText) {
                return
            }

            try {
                const response = await api.conversations.tts(plainText)
                const arrayBuffer = await response.arrayBuffer()

                if (!cache.audioContext) {
                    cache.audioContext = new AudioContext()
                }
                const audioCtx = cache.audioContext as AudioContext
                if (audioCtx.state === 'suspended') {
                    await audioCtx.resume()
                }

                const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)
                const source = audioCtx.createBufferSource()
                source.buffer = audioBuffer
                source.connect(audioCtx.destination)

                cache.currentSource = source
                actions.setPlaybackActive(true)

                source.onended = () => {
                    cache.currentSource = null
                    actions.setPlaybackActive(false)
                }

                source.start()
            } catch {
                actions.setPlaybackActive(false)
            }
        },

        stopPlayback: () => {
            const source = cache.currentSource as AudioBufferSourceNode | undefined
            if (source) {
                try {
                    source.stop()
                } catch {
                    // Already stopped
                }
                cache.currentSource = null
            }
            actions.setPlaybackActive(false)
        },
    })),

    events(({ values, actions }) => ({
        beforeUnmount: () => {
            if (values.recording || values.connecting) {
                actions.stopRecording()
            }
            if (values.playbackActive) {
                actions.stopPlayback()
            }
        },
    })),
])
