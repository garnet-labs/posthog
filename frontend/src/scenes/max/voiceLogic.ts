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
// How long to wait after the last transcript (partial or committed) before auto-sending
const TURN_COMPLETE_DEBOUNCE_MS = 1600

function teardownPlaybackVisuals(cache: any, actions: any): void {
    cache.playbackVisualActive = false
    const rafId = cache.playbackAmplitudeRafId as number | null | undefined
    if (rafId) {
        cancelAnimationFrame(rafId)
    }
    cache.playbackAmplitudeRafId = null
    const a = cache.playbackAnalyser as AnalyserNode | undefined
    if (a) {
        try {
            a.disconnect()
        } catch {
            // Already disconnected
        }
        cache.playbackAnalyser = null
    }
    cache.playbackAnalyserData = null
    actions.setMouthOpenness(0)
    actions.setIsMouthOpen(false)
}

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
        /** While true, VAD debounce will not auto-stop; release pointer to send (ChatGPT-style hold-to-talk). */
        setOrbPointerDown: (down: boolean) => ({ down }),
        /** True while downloading/decoding TTS before playback starts (voice UI should not pretend the mic is live). */
        setTtsLoading: (loading: boolean) => ({ loading }),
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
                // startRecording does not clear — user may press the orb to interrupt TTS while still holding.
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
    }),

    listeners(({ actions, values, cache }) => ({
        startRecording: async ({ tabId }) => {
            actions.setActiveTabId(tabId)
            actions.setMicPermissionDenied(false)
            actions.setConnecting(true)
            actions.setInputAmplitude(0)
            actions.setIsSpeaking(false)
            actions.setMouthOpenness(0)
            actions.setIsMouthOpen(false)
            actions.setSilenceMs(0)

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
                // VAD tuning: higher threshold rejects background noise; longer silence avoids cutting off mid-thought
                vad_threshold: '0.7',
                vad_silence_threshold_secs: '1.0',
                min_speech_duration_ms: '200',
            })
            const ws = new WebSocket(`${ELEVENLABS_WSS}?${params.toString()}`)
            cache.sttWebSocket = ws

            ws.onopen = () => {
                // Create a dedicated AudioContext at the STT sample rate for recording
                const recordingCtx = new AudioContext({ sampleRate: STT_SAMPLE_RATE })
                cache.recordingAudioContext = recordingCtx

                const source = recordingCtx.createMediaStreamSource(stream)
                const analyser = recordingCtx.createAnalyser()
                analyser.fftSize = 2048
                analyser.smoothingTimeConstant = 0.2
                // ScriptProcessorNode needs a path to destination to fire onaudioprocess.
                // Route through a silent gain node so mic audio doesn't play through speakers.
                const processor = recordingCtx.createScriptProcessor(STT_BUFFER_SIZE, 1, 1)
                const silentGain = recordingCtx.createGain()
                silentGain.gain.value = 0

                source.connect(analyser)
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

                const timeDomainData = new Uint8Array(analyser.fftSize)
                cache.inputAnalyser = analyser
                cache.inputAnalyserData = timeDomainData
                cache.speakingHangoverUntil = 0
                cache.lastNonSilentAt = performance.now()
                cache.lastAmplitudeUpdateAt = null
                cache.smoothedMouthOpenness = 0
                cache.isMouthOpen = false

                const amplitudeLoop = (): void => {
                    if (!cache.inputAnalyser || !cache.inputAnalyserData || !values.recording) {
                        cache.inputAmplitudeRafId = null
                        return
                    }

                    const analyserNode = cache.inputAnalyser as AnalyserNode
                    const data = cache.inputAnalyserData as Uint8Array
                    analyserNode.getByteTimeDomainData(data as unknown as Uint8Array<ArrayBuffer>)

                    // RMS of centered time-domain signal. Output range is ~[0..1].
                    let sumSquares = 0
                    for (let i = 0; i < data.length; i++) {
                        const x = (data[i] - 128) / 128
                        sumSquares += x * x
                    }
                    const rms = Math.sqrt(sumSquares / data.length)

                    // Noise gate + short hangover so "speaking" doesn't flicker between phonemes.
                    const threshold = 0.025
                    const now = performance.now()
                    if (rms >= threshold) {
                        cache.speakingHangoverUntil = now + 150
                        cache.lastNonSilentAt = now
                    }
                    const speakingHangoverUntil = cache.speakingHangoverUntil as number
                    const isSpeaking = now <= speakingHangoverUntil

                    // Mouth openness is a faster, more "twitchy" signal than isSpeaking:
                    // - normalize RMS into 0..1 above a small noise floor
                    // - smooth a bit to avoid frame-by-frame jitter
                    const noiseFloor = 0.015
                    const maxLevel = 0.12
                    const normalized = Math.max(0, Math.min(1, (rms - noiseFloor) / (maxLevel - noiseFloor)))

                    const previousNow = cache.lastAmplitudeUpdateAt as number | null
                    const dtMs = previousNow ? now - previousNow : 16
                    cache.lastAmplitudeUpdateAt = now

                    // EMA smoothing: higher alpha = snappier. Scale with dt to be stable across refresh rates.
                    const alpha = Math.max(0.05, Math.min(0.35, dtMs / 60))
                    const previousSmoothed = cache.smoothedMouthOpenness as number
                    const smoothed = previousSmoothed + alpha * (normalized - previousSmoothed)
                    cache.smoothedMouthOpenness = smoothed

                    // Hysteresis so we "open" quickly and "close" only when clearly quiet.
                    const openThreshold = 0.18
                    const closeThreshold = 0.1
                    const prevIsMouthOpen = cache.isMouthOpen as boolean
                    const nextIsMouthOpen = prevIsMouthOpen ? smoothed >= closeThreshold : smoothed >= openThreshold
                    cache.isMouthOpen = nextIsMouthOpen

                    const lastNonSilentAt = cache.lastNonSilentAt as number
                    const silenceMs = Math.max(0, now - lastNonSilentAt)

                    actions.setInputAmplitude(rms)
                    actions.setIsSpeaking(isSpeaking)
                    actions.setMouthOpenness(smoothed)
                    actions.setIsMouthOpen(nextIsMouthOpen)
                    actions.setSilenceMs(silenceMs)

                    cache.inputAmplitudeRafId = requestAnimationFrame(amplitudeLoop)
                }

                cache.scriptProcessor = processor
                cache.recordingSource = source
                cache.silentGain = silentGain

                actions.setConnecting(false)
                actions.setRecording(true)
                actions.setVoiceModeEnabled(true)

                cache.inputAmplitudeRafId = requestAnimationFrame(amplitudeLoop)
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

                // Turn detection: restart timer on every transcript that carries text.
                // When no new transcript arrives for TURN_COMPLETE_DEBOUNCE_MS, auto-send.
                // Hold-to-talk on the orb sets cache.orbPointerDown — no auto-send until release.
                if (values.voiceModeEnabled && fullText) {
                    clearTimeout(cache.turnTimer as ReturnType<typeof setTimeout> | undefined)
                    cache.turnTimer = setTimeout(() => {
                        cache.turnTimer = null
                        if (
                            values.recording &&
                            values.voiceModeEnabled &&
                            !(cache.orbPointerDown as boolean | undefined)
                        ) {
                            actions.stopRecording()
                        }
                    }, TURN_COMPLETE_DEBOUNCE_MS)
                }
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

        setOrbPointerDown: ({ down }) => {
            cache.orbPointerDown = down
            if (down) {
                clearTimeout(cache.turnTimer as ReturnType<typeof setTimeout> | undefined)
                cache.turnTimer = null
            }
        },

        stopRecording: () => {
            cache.orbPointerDown = false
            // Clear any pending turn detection timer
            clearTimeout(cache.turnTimer as ReturnType<typeof setTimeout> | undefined)
            cache.turnTimer = null

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
            const rafId = cache.inputAmplitudeRafId as number | null | undefined
            if (rafId) {
                cancelAnimationFrame(rafId)
            }
            cache.inputAmplitudeRafId = null
            cache.inputAnalyser = null
            cache.inputAnalyserData = null
            cache.speakingHangoverUntil = null

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
            actions.setInputAmplitude(0)
            actions.setIsSpeaking(false)
            actions.setMouthOpenness(0)
            actions.setIsMouthOpen(false)
            actions.setSilenceMs(0)

            if (finalText && wasRecording) {
                const tabId = values.activeTabId
                if (!tabId) {
                    return
                }
                const mountedMaxLogic = maxLogic.findMounted({ tabId })
                mountedMaxLogic?.actions.setQuestion(finalText)

                // maxThreadLogic is keyed as `${conversationId}-${tabId}`; findMounted() without props never matches.
                const conversationId = mountedMaxLogic?.values.threadLogicKey
                const mountedThreadLogic =
                    conversationId != null ? maxThreadLogic.findMounted({ tabId, conversationId }) : undefined
                mountedThreadLogic?.actions.askMax(finalText)
            } else if (!finalText && wasRecording) {
                if (values.voiceModeEnabled && values.activeTabId) {
                    actions.startRecording(values.activeTabId)
                } else {
                    lemonToast.warning('No speech detected. Try again.')
                }
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

            // Tear down previous TTS visual loop / analyser
            cache.playbackVisualActive = false
            const prevPlaybackRaf = cache.playbackAmplitudeRafId as number | null | undefined
            if (prevPlaybackRaf) {
                cancelAnimationFrame(prevPlaybackRaf)
            }
            cache.playbackAmplitudeRafId = null
            const prevPlaybackAnalyser = cache.playbackAnalyser as AnalyserNode | undefined
            if (prevPlaybackAnalyser) {
                try {
                    prevPlaybackAnalyser.disconnect()
                } catch {
                    // Already disconnected
                }
                cache.playbackAnalyser = null
            }
            cache.playbackAnalyserData = null

            // Strip markdown for cleaner speech
            const plainText = stripMarkdown(text).slice(0, 5000)
            if (!plainText) {
                return
            }

            actions.setTtsLoading(true)
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

                const analyser = audioCtx.createAnalyser()
                analyser.fftSize = 2048
                analyser.smoothingTimeConstant = 0.2
                source.connect(analyser)
                analyser.connect(audioCtx.destination)

                cache.playbackAnalyser = analyser
                cache.playbackAnalyserData = new Uint8Array(analyser.fftSize)
                cache.playbackLastAmplitudeUpdateAt = null
                cache.playbackSmoothedMouthOpenness = 0
                cache.playbackMouthOpenHysteresis = false

                actions.setMouthOpenness(0)
                actions.setIsMouthOpen(false)

                const playbackAmplitudeLoop = (): void => {
                    if (!cache.playbackVisualActive) {
                        cache.playbackAmplitudeRafId = null
                        return
                    }
                    const analyserNode = cache.playbackAnalyser as AnalyserNode | undefined
                    const data = cache.playbackAnalyserData as Uint8Array | undefined
                    if (!analyserNode || !data) {
                        cache.playbackAmplitudeRafId = null
                        return
                    }

                    analyserNode.getByteTimeDomainData(data as unknown as Uint8Array<ArrayBuffer>)

                    let sumSquares = 0
                    for (let i = 0; i < data.length; i++) {
                        const x = (data[i] - 128) / 128
                        sumSquares += x * x
                    }
                    const rms = Math.sqrt(sumSquares / data.length)

                    const noiseFloor = 0.015
                    const maxLevel = 0.12
                    const normalized = Math.max(0, Math.min(1, (rms - noiseFloor) / (maxLevel - noiseFloor)))

                    const now = performance.now()
                    const previousNow = cache.playbackLastAmplitudeUpdateAt as number | null
                    const dtMs = previousNow ? now - previousNow : 16
                    cache.playbackLastAmplitudeUpdateAt = now

                    const alpha = Math.max(0.05, Math.min(0.35, dtMs / 60))
                    const previousSmoothed = cache.playbackSmoothedMouthOpenness as number
                    const smoothed = previousSmoothed + alpha * (normalized - previousSmoothed)
                    cache.playbackSmoothedMouthOpenness = smoothed

                    const openThreshold = 0.18
                    const closeThreshold = 0.1
                    const prevIsMouthOpen = cache.playbackMouthOpenHysteresis as boolean
                    const nextIsMouthOpen = prevIsMouthOpen ? smoothed >= closeThreshold : smoothed >= openThreshold
                    cache.playbackMouthOpenHysteresis = nextIsMouthOpen

                    actions.setMouthOpenness(smoothed)
                    actions.setIsMouthOpen(nextIsMouthOpen)

                    cache.playbackAmplitudeRafId = requestAnimationFrame(playbackAmplitudeLoop)
                }

                cache.currentSource = source
                actions.setTtsLoading(false)
                if (!voiceLogic.findMounted()?.values.voiceModeEnabled) {
                    cache.currentSource = null
                    return
                }
                actions.setPlaybackActive(true)
                cache.playbackVisualActive = true
                cache.playbackAmplitudeRafId = requestAnimationFrame(playbackAmplitudeLoop)

                source.onended = () => {
                    cache.currentSource = null
                    teardownPlaybackVisuals(cache, actions)
                    actions.setPlaybackActive(false)
                }

                source.start()
            } catch {
                actions.setTtsLoading(false)
                teardownPlaybackVisuals(cache, actions)
                actions.setPlaybackActive(false)
            }
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

        setPlaybackActive: ({ active }) => {
            // Auto-resume mic recording after TTS finishes in voice mode
            if (!active && values.voiceModeEnabled && !values.recording && !values.connecting && !values.ttsLoading) {
                const tabId = values.activeTabId
                if (tabId) {
                    actions.startRecording(tabId)
                }
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
            teardownPlaybackVisuals(cache, actions)
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
