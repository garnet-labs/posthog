import { actions, events, kea, listeners, path, reducers } from 'kea'

import api from 'lib/api'
import { lemonToast } from 'lib/lemon-ui/LemonToast'

import { stripMarkdown } from '~/lib/utils/stripMarkdown'

import { pickRandomWaitFillTweets, waitFillClipTtsText } from './ceoToolWaitTweets'
import { maxLogic } from './maxLogic'
import { maxThreadLogic } from './maxThreadLogic'
import { commonPrefixLength, consumeSpeakableSegmentsFromDelta, streamingTtsKey } from './streamingVoiceTts'
import type { voiceLogicType } from './voiceLogicType'

type TtsQueueKind = 'main' | 'waitFill'

interface TtsQueueItem {
    kind: TtsQueueKind
    text: string
}

const ELEVENLABS_WSS = 'wss://api.elevenlabs.io/v1/speech-to-text/realtime'
const STT_SAMPLE_RATE = 16000
const STT_BUFFER_SIZE = 4096
// How long to wait after the last transcript (partial or committed) before we *consider* auto-send.
// Natural mid-sentence pauses often exceed 500ms; too low cuts users off.
const TURN_COMPLETE_DEBOUNCE_MS = 850
// After debounce, require this much local (mic) silence so we don't stop while you're still talking
// but STT hasn't emitted a partial yet.
const MIN_SILENCE_BEFORE_AUTO_STOP_MS = 400

/** ElevenLabs `pcm_44100`: mono int16 little-endian */
const TTS_PCM_SAMPLE_RATE = 44100
const TTS_PCM_BYTES_PER_FRAME = 2
/** ~23ms — start playback as soon as this much PCM has arrived */
const TTS_FIRST_PLAY_MIN_BYTES = 2048
/** Steady-state chunk size (~46ms) */
const TTS_STREAM_CHUNK_BYTES = 4096
/** After AudioContext.resume(), scheduling at currentTime can clip the first ~20–50ms; small lookahead fixes it */
const TTS_FIRST_SOURCE_SCHEDULE_LOOKAHEAD_SEC = 0.03
/** <1 slows playback (wall-clock segment length = buffer.duration / rate) */
const TTS_PLAYBACK_RATE = 0.98

function pcmS16leToAudioBuffer(audioCtx: AudioContext, pcm: Uint8Array): AudioBuffer {
    const frameCount = Math.floor(pcm.length / TTS_PCM_BYTES_PER_FRAME)
    const clipped = pcm.subarray(0, frameCount * TTS_PCM_BYTES_PER_FRAME)
    const buffer = audioCtx.createBuffer(1, frameCount, TTS_PCM_SAMPLE_RATE)
    const channel = buffer.getChannelData(0)
    const view = new DataView(clipped.buffer, clipped.byteOffset, clipped.byteLength)
    for (let i = 0; i < frameCount; i++) {
        channel[i] = view.getInt16(i * TTS_PCM_BYTES_PER_FRAME, true) / 32768
    }
    return buffer
}

function teardownPlaybackVisuals(cache: any, actions: any): void {
    cache.playbackVisualActive = false
    const rafId = cache.playbackAmplitudeRafId as number | null | undefined
    if (rafId) {
        cancelAnimationFrame(rafId)
    }
    cache.playbackAmplitudeRafId = null
    const gain = cache.playbackGainNode as GainNode | undefined
    if (gain) {
        try {
            gain.disconnect()
        } catch {
            // Already disconnected
        }
        cache.playbackGainNode = null
    }
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

function ensureTtsQueueState(cache: any): void {
    if (!cache.ttsQueue) {
        cache.ttsQueue = [] as TtsQueueItem[]
    }
    if (!cache.ttsWaitFillQueue) {
        cache.ttsWaitFillQueue = [] as TtsQueueItem[]
    }
    if (!cache.ttsDeferredQueue) {
        cache.ttsDeferredQueue = [] as TtsQueueItem[]
    }
}

/** Assistant TTS waits here while wait-fill clips (tweets) are still queued, playing, or a second clip may follow. */
function shouldDeferMainForWaitFill(cache: any): boolean {
    if (!cache.toolWaitFillEnabled) {
        return false
    }
    if ((cache.ttsWaitFillQueue as TtsQueueItem[]).length > 0) {
        return true
    }
    if (cache.playingTtsKind === 'waitFill') {
        return true
    }
    // Between first and optional second clip — still holding the phase open
    if (cache.waitFillOptionalSecondLine) {
        return true
    }
    return false
}

/**
 * After each wait-fill clip: optionally queue a second tweet only if assistant TTS isn't ready yet;
 * otherwise end the wait-fill phase and merge deferred assistant audio.
 */
function maybeContinueAfterWaitFillClip(cache: any): void {
    if (!cache.toolWaitFillEnabled) {
        return
    }

    const deferredLen = (cache.ttsDeferredQueue as TtsQueueItem[] | undefined)?.length ?? 0
    const second = cache.waitFillOptionalSecondLine as string | undefined

    if (second && deferredLen === 0) {
        ;(cache.ttsWaitFillQueue as TtsQueueItem[]).push({ kind: 'waitFill', text: second })
        cache.waitFillOptionalSecondLine = undefined
        // Caller drain loop continues — do not call drainTtsQueue (re-entrant guard)
        return
    }

    cache.waitFillOptionalSecondLine = undefined

    if ((cache.ttsWaitFillQueue as TtsQueueItem[]).length > 0) {
        return
    }
    if (cache.playingTtsKind === 'waitFill') {
        return
    }

    cache.toolWaitFillEnabled = false
    const def = cache.ttsDeferredQueue as TtsQueueItem[] | undefined
    if (def?.length) {
        const main = cache.ttsQueue as TtsQueueItem[]
        main.unshift(...def)
        def.length = 0
    }
}

function hasQueuedTts(cache: any): boolean {
    ensureTtsQueueState(cache)
    const mainLen = (cache.ttsQueue as TtsQueueItem[]).length
    const waitLen =
        cache.toolWaitFillEnabled && cache.ttsWaitFillQueue ? (cache.ttsWaitFillQueue as TtsQueueItem[]).length : 0
    return mainLen + waitLen > 0
}

function dequeueNextTts(cache: any): TtsQueueItem | null {
    ensureTtsQueueState(cache)
    const main = cache.ttsQueue as TtsQueueItem[]
    if (main.length > 0) {
        return main.shift() ?? null
    }
    if (cache.toolWaitFillEnabled && (cache.ttsWaitFillQueue as TtsQueueItem[]).length > 0) {
        return (cache.ttsWaitFillQueue as TtsQueueItem[]).shift() ?? null
    }
    return null
}

function concatUint8(a: Uint8Array, b: Uint8Array): Uint8Array {
    const out = new Uint8Array(a.length + b.length)
    out.set(a, 0)
    out.set(b, a.length)
    return out
}

function stopAllTtsSources(cache: any): void {
    const list = cache.ttsPlaybackSources as AudioBufferSourceNode[] | undefined
    if (list?.length) {
        for (const s of list) {
            try {
                s.stop()
            } catch {
                // Already stopped
            }
        }
        list.length = 0
    }
    cache.currentSource = null
}

async function playTtsClip(
    cache: any,
    actions: any,
    plainText: string,
    generationAtStart: number,
    kind: TtsQueueKind = 'main'
): Promise<void> {
    cache.playingTtsKind = kind
    try {
        const response = await api.conversations.tts(plainText)

        if (cache.ttsDrainGeneration !== generationAtStart) {
            return
        }

        if (!response.ok) {
            const errBody = await response.text().catch(() => '')
            throw new Error(errBody || `TTS request failed (${response.status})`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
            throw new Error('TTS response has no body')
        }

        if (!cache.audioContext) {
            cache.audioContext = new AudioContext()
        }
        const audioCtx = cache.audioContext as AudioContext
        if (audioCtx.state === 'suspended') {
            await audioCtx.resume()
        }

        if (cache.ttsDrainGeneration !== generationAtStart) {
            void reader.cancel()
            return
        }

        cache.playbackScheduleTime = undefined
        cache.ttsPlaybackSources = [] as AudioBufferSourceNode[]

        const gain = audioCtx.createGain()
        gain.gain.value = 1
        cache.playbackGainNode = gain

        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 2048
        analyser.smoothingTimeConstant = 0.2
        gain.connect(analyser)
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

        let pcmBuffer: Uint8Array<ArrayBufferLike> = new Uint8Array(0)
        let streamEnded = false
        let pendingSources = 0
        let startedPlayback = false
        let firstChunk = true
        let firstSourceInClip = true

        await new Promise<void>((resolve) => {
            const tryResolve = (): void => {
                if (streamEnded && pendingSources === 0) {
                    cache.currentSource = null
                    stopAllTtsSources(cache)
                    teardownPlaybackVisuals(cache, actions)
                    resolve()
                }
            }

            const schedulePcm = (pcm: Uint8Array): void => {
                const audioBuffer = pcmS16leToAudioBuffer(audioCtx, pcm)
                if (audioBuffer.length === 0) {
                    return
                }

                const source = audioCtx.createBufferSource()
                source.buffer = audioBuffer
                source.playbackRate.value = TTS_PLAYBACK_RATE
                source.connect(gain)

                let nextT = cache.playbackScheduleTime as number | undefined
                if (nextT === undefined || nextT < audioCtx.currentTime) {
                    nextT = audioCtx.currentTime
                }
                if (firstSourceInClip) {
                    nextT += TTS_FIRST_SOURCE_SCHEDULE_LOOKAHEAD_SEC
                    firstSourceInClip = false
                }
                const wallSeconds = audioBuffer.duration / TTS_PLAYBACK_RATE
                cache.playbackScheduleTime = nextT + wallSeconds

                pendingSources++
                ;(cache.ttsPlaybackSources as AudioBufferSourceNode[]).push(source)
                source.onended = () => {
                    const list = cache.ttsPlaybackSources as AudioBufferSourceNode[]
                    const idx = list.indexOf(source)
                    if (idx >= 0) {
                        list.splice(idx, 1)
                    }
                    pendingSources--
                    tryResolve()
                }

                try {
                    source.start(nextT)
                } catch {
                    const list = cache.ttsPlaybackSources as AudioBufferSourceNode[]
                    const idx = list.indexOf(source)
                    if (idx >= 0) {
                        list.splice(idx, 1)
                    }
                    pendingSources--
                    tryResolve()
                }

                if (!startedPlayback) {
                    startedPlayback = true
                    actions.setPlaybackActive(true)
                    cache.playbackVisualActive = true
                    cache.playbackAmplitudeRafId = requestAnimationFrame(playbackAmplitudeLoop)
                }
            }

            const drainPcmBuffer = (): void => {
                while (true) {
                    const minBytes = firstChunk ? TTS_FIRST_PLAY_MIN_BYTES : TTS_STREAM_CHUNK_BYTES
                    if (!streamEnded && pcmBuffer.length < minBytes) {
                        break
                    }
                    if (pcmBuffer.length < TTS_PCM_BYTES_PER_FRAME) {
                        break
                    }

                    let takeLen: number
                    if (streamEnded && pcmBuffer.length < minBytes) {
                        takeLen = pcmBuffer.length - (pcmBuffer.length % TTS_PCM_BYTES_PER_FRAME)
                    } else {
                        takeLen = Math.min(minBytes, pcmBuffer.length)
                        takeLen -= takeLen % TTS_PCM_BYTES_PER_FRAME
                    }
                    if (takeLen < TTS_PCM_BYTES_PER_FRAME) {
                        break
                    }

                    const chunk = pcmBuffer.subarray(0, takeLen)
                    pcmBuffer = pcmBuffer.slice(takeLen)
                    schedulePcm(chunk)
                    if (firstChunk) {
                        firstChunk = false
                    }
                }
            }

            const pump = async (): Promise<void> => {
                try {
                    for (;;) {
                        if (cache.ttsDrainGeneration !== generationAtStart) {
                            void reader.cancel()
                            stopAllTtsSources(cache)
                            teardownPlaybackVisuals(cache, actions)
                            resolve()
                            return
                        }

                        const { done, value } = await reader.read()
                        if (cache.ttsDrainGeneration !== generationAtStart) {
                            void reader.cancel()
                            stopAllTtsSources(cache)
                            teardownPlaybackVisuals(cache, actions)
                            resolve()
                            return
                        }

                        if (value?.byteLength) {
                            const buf = new ArrayBuffer(value.byteLength)
                            const chunk = new Uint8Array(buf)
                            chunk.set(value)
                            pcmBuffer = pcmBuffer.length ? concatUint8(pcmBuffer, chunk) : chunk
                            drainPcmBuffer()
                        }

                        if (done) {
                            streamEnded = true
                            drainPcmBuffer()
                            tryResolve()
                            return
                        }
                    }
                } catch {
                    stopAllTtsSources(cache)
                    teardownPlaybackVisuals(cache, actions)
                    resolve()
                }
            }

            void pump()
        })
    } finally {
        cache.playingTtsKind = undefined
    }
}

async function drainTtsQueue(cache: any, actions: any): Promise<void> {
    ensureTtsQueueState(cache)
    if (cache.ttsDrainRunning) {
        return
    }
    cache.ttsDrainRunning = true
    try {
        while (true) {
            const item = dequeueNextTts(cache)
            if (!item) {
                break
            }
            const generationAtStart = cache.ttsDrainGeneration as number
            try {
                await playTtsClip(cache, actions, item.text, generationAtStart, item.kind)
            } catch {
                teardownPlaybackVisuals(cache, actions)
            }
            if (cache.ttsDrainGeneration !== generationAtStart) {
                break
            }
            if (item.kind === 'waitFill') {
                maybeContinueAfterWaitFillClip(cache)
            }
        }
    } finally {
        cache.ttsDrainRunning = false
        ensureTtsQueueState(cache)
        if (hasQueuedTts(cache)) {
            void drainTtsQueue(cache, actions)
        }
    }
    ensureTtsQueueState(cache)
    const pendingTtsSources = (cache.ttsPlaybackSources as AudioBufferSourceNode[] | undefined)?.length ?? 0
    if (!hasQueuedTts(cache) && pendingTtsSources === 0) {
        actions.setPlaybackActive(false)
    }
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
        resetStreamingTtsOffsets: true,
        syncAssistantStreamingTts: (payload: {
            traceId: string | null
            messageId: string | undefined
            content: string
            isFinal: boolean
        }) => payload,
        playToolCallNarration: (payload: { dedupeKey: string; sentence: string }) => payload,
        /** Queue interstitial TTS while tools run (after tool-call narration). */
        enqueueToolWaitFill: true,
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

            // Mic + STT token in parallel — previously serial (mic then HTTP), which added full token RTT on top of permission latency.
            const [micSettled, tokenSettled] = await Promise.allSettled([
                navigator.mediaDevices.getUserMedia({ audio: true }),
                api.conversations.sttToken(),
            ])

            if (micSettled.status === 'rejected') {
                actions.setMicPermissionDenied(true)
                actions.setConnecting(false)
                return
            }

            const stream = micSettled.value

            if (tokenSettled.status === 'rejected') {
                stream.getTracks().forEach((t) => t.stop())
                actions.setConnecting(false)
                lemonToast.error('Failed to start voice input.')
                return
            }

            const token = tokenSettled.value.token

            // Unlock AudioContext on user gesture for later TTS auto-play
            if (!cache.audioContext) {
                cache.audioContext = new AudioContext()
            }
            if (cache.audioContext.state === 'suspended') {
                await cache.audioContext.resume()
            }

            cache.mediaStream = stream
            cache.committedParts = [] as string[]
            cache.currentPartial = ''

            const params = new URLSearchParams({
                token,
                model_id: 'scribe_v2_realtime',
                commit_strategy: 'vad',
                audio_format: `pcm_${STT_SAMPLE_RATE}`,
                // VAD tuning: higher threshold rejects background noise; silence length trades latency vs mid-utterance splits
                vad_threshold: '0.7',
                // Longer = fewer premature segment commits on short pauses (pairs with client debounce above)
                vad_silence_threshold_secs: '0.85',
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
                // When no new transcript arrives for TURN_COMPLETE_DEBOUNCE_MS, we may auto-send (after local silence check).
                // Hold-to-talk on the orb sets cache.orbPointerDown — no auto-send until release.
                if (values.voiceModeEnabled && fullText) {
                    clearTimeout(cache.turnTimer as ReturnType<typeof setTimeout> | undefined)
                    const tryAutoStop = (): void => {
                        cache.turnTimer = null
                        const v = voiceLogic.findMounted()
                        if (!v?.values.recording || !v?.values.voiceModeEnabled || v.values.orbPointerDown) {
                            return
                        }
                        const lastNonSilentAt = cache.lastNonSilentAt as number | undefined
                        const quietFor =
                            lastNonSilentAt != null ? Math.max(0, performance.now() - lastNonSilentAt) : Infinity
                        if (quietFor < MIN_SILENCE_BEFORE_AUTO_STOP_MS) {
                            cache.turnTimer = setTimeout(tryAutoStop, 120)
                            return
                        }
                        v.actions.stopRecording()
                    }
                    cache.turnTimer = setTimeout(tryAutoStop, TURN_COMPLETE_DEBOUNCE_MS)
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

            const plainText = stripMarkdown(text).slice(0, 5000)
            if (!plainText) {
                return
            }

            ensureTtsQueueState(cache)
            if (cache.ttsDrainGeneration === undefined) {
                cache.ttsDrainGeneration = 0
            }
            const item: TtsQueueItem = { kind: 'main', text: plainText }
            if (shouldDeferMainForWaitFill(cache)) {
                ;(cache.ttsDeferredQueue as TtsQueueItem[]).push(item)
            } else {
                ;(cache.ttsQueue as TtsQueueItem[]).push(item)
            }
            void drainTtsQueue(cache, actions)
        },

        resetStreamingTtsOffsets: () => {
            cache.ttsStreamLastFullPlainByKey = new Map<string, string>()
            cache.ttsStreamPendingPlainByKey = new Map<string, string>()
            cache.ttsStreamingLastMessageIdByTrace = {} as Record<string, string | undefined>
            cache.toolNarrationSpoken = new Set<string>()
            cache.toolCallNarrationRecent = [] as string[]
            cache.toolWaitFillEnabled = false
            cache.waitFillOptionalSecondLine = undefined
            ensureTtsQueueState(cache)
            ;(cache.ttsWaitFillQueue as TtsQueueItem[]).length = 0
            ;(cache.ttsDeferredQueue as TtsQueueItem[]).length = 0
        },

        enqueueToolWaitFill: async () => {
            if (!values.voiceModeEnabled) {
                return
            }
            ensureTtsQueueState(cache)
            if (cache.ttsDrainGeneration === undefined) {
                cache.ttsDrainGeneration = 0
            }
            const waitTweets = pickRandomWaitFillTweets(2)
            const waitTotal = waitTweets.length
            let lines: string[]
            try {
                const res = await api.conversations.waitFillTtsLines({ tweets: waitTweets })
                if (!res.lines?.length || res.lines.length !== waitTweets.length) {
                    throw new Error('wait_fill_tts bad response shape')
                }
                lines = res.lines
            } catch {
                lines = waitTweets.map((tweet, i) => waitFillClipTtsText(tweet, i, waitTotal))
            }
            cache.waitFillOptionalSecondLine = undefined
            if (lines.length >= 1) {
                ;(cache.ttsWaitFillQueue as TtsQueueItem[]).push({ kind: 'waitFill', text: lines[0] })
                if (lines.length >= 2) {
                    cache.waitFillOptionalSecondLine = lines[1]
                }
            }
            cache.toolWaitFillEnabled = true
            void drainTtsQueue(cache, actions)
        },

        playToolCallNarration: ({ dedupeKey, sentence }) => {
            if (!values.voiceModeEnabled || !sentence.trim()) {
                return
            }
            if (!cache.toolNarrationSpoken) {
                cache.toolNarrationSpoken = new Set<string>()
            }
            if (cache.toolNarrationSpoken.has(dedupeKey)) {
                return
            }
            cache.toolNarrationSpoken.add(dedupeKey)
            if (!cache.toolCallNarrationRecent) {
                cache.toolCallNarrationRecent = [] as string[]
            }
            const recent = cache.toolCallNarrationRecent as string[]
            recent.push(sentence.trim())
            while (recent.length > 10) {
                recent.shift()
            }
            actions.playResponse(sentence.trim())
            actions.enqueueToolWaitFill()
        },

        syncAssistantStreamingTts: ({ traceId, messageId, content, isFinal }) => {
            if (!values.voiceModeEnabled) {
                return
            }

            if (!cache.ttsStreamLastFullPlainByKey) {
                cache.ttsStreamLastFullPlainByKey = new Map<string, string>()
            }
            if (!cache.ttsStreamPendingPlainByKey) {
                cache.ttsStreamPendingPlainByKey = new Map<string, string>()
            }
            if (!cache.ttsStreamingLastMessageIdByTrace) {
                cache.ttsStreamingLastMessageIdByTrace = {} as Record<string, string | undefined>
            }

            const tid = traceId ?? 'none'
            const prevId = cache.ttsStreamingLastMessageIdByTrace[tid]
            if (prevId && prevId !== messageId && messageId) {
                const oldKey = streamingTtsKey(traceId, prevId)
                const newKey = streamingTtsKey(traceId, messageId)
                const lastFull = cache.ttsStreamLastFullPlainByKey.get(oldKey)
                if (lastFull !== undefined) {
                    cache.ttsStreamLastFullPlainByKey.set(newKey, lastFull)
                }
                cache.ttsStreamLastFullPlainByKey.delete(oldKey)
                const pend = cache.ttsStreamPendingPlainByKey.get(oldKey)
                if (pend !== undefined) {
                    cache.ttsStreamPendingPlainByKey.set(newKey, pend)
                }
                cache.ttsStreamPendingPlainByKey.delete(oldKey)
            }
            if (messageId) {
                cache.ttsStreamingLastMessageIdByTrace[tid] = messageId
            }

            const key = streamingTtsKey(traceId, messageId)
            const plainNew = stripMarkdown(content).slice(0, 5000)
            const lastFull = cache.ttsStreamLastFullPlainByKey.get(key) ?? ''
            const pending = cache.ttsStreamPendingPlainByKey.get(key) ?? ''

            // Append-only plain: raw content only grows, but stripMarkdown can rewrite the prefix each tick.
            // Feeding cumulative plain.slice(offset) skips text when the prefix shifts. Instead: extend only
            // by plainNew.slice(lastFull.length) when possible; on prefix repair, splice after LCP.
            let combined: string
            if (lastFull.length === 0) {
                combined = plainNew
            } else if (plainNew.startsWith(lastFull)) {
                combined = pending + plainNew.slice(lastFull.length)
            } else {
                const lcp = commonPrefixLength(lastFull, plainNew)
                combined = pending + plainNew.slice(lcp)
            }

            if (!combined && !isFinal) {
                return
            }

            const { segments, consumed } = consumeSpeakableSegmentsFromDelta(combined, isFinal)
            cache.ttsStreamPendingPlainByKey.set(key, combined.slice(consumed))
            cache.ttsStreamLastFullPlainByKey.set(key, plainNew)

            for (const segment of segments) {
                const t = stripMarkdown(segment).trim()
                if (t) {
                    actions.playResponse(t)
                }
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
            cache.ttsDrainGeneration = (cache.ttsDrainGeneration ?? 0) + 1
            ensureTtsQueueState(cache)
            ;(cache.ttsQueue as TtsQueueItem[]).length = 0
            cache.toolWaitFillEnabled = false
            cache.waitFillOptionalSecondLine = undefined
            ;(cache.ttsWaitFillQueue as TtsQueueItem[]).length = 0
            ;(cache.ttsDeferredQueue as TtsQueueItem[]).length = 0
            cache.playbackScheduleTime = undefined

            stopAllTtsSources(cache)

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
