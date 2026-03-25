import { actions, kea, listeners, path, reducers } from 'kea'

import api from 'lib/api'
import { lemonToast } from 'lib/lemon-ui/LemonToast'

import { stripMarkdown } from '~/lib/utils/stripMarkdown'

import { maxLogic } from './maxLogic'
import { maxThreadLogic } from './maxThreadLogic'
import type { voiceLogicType } from './voiceLogicType'

export const voiceLogic = kea<voiceLogicType>([
    path(['scenes', 'max', 'voiceLogic']),

    actions({
        startRecording: (tabId: string) => ({ tabId }),
        stopRecording: true,
        setRecording: (recording: boolean) => ({ recording }),
        setTranscribing: (transcribing: boolean) => ({ transcribing }),
        setMicPermissionDenied: (denied: boolean) => ({ denied }),
        setVoiceModeEnabled: (enabled: boolean) => ({ enabled }),
        setActiveTabId: (tabId: string | null) => ({ tabId }),
        transcriptionComplete: (text: string) => ({ text }),
        transcriptionFailed: true,
        playResponse: (text: string) => ({ text }),
        setPlaybackActive: (active: boolean) => ({ active }),
        stopPlayback: true,
        disableVoiceMode: true,
    }),

    reducers({
        recording: [false, { setRecording: (_, { recording }) => recording }],
        transcribing: [false, { setTranscribing: (_, { transcribing }) => transcribing }],
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

            let stream: MediaStream
            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            } catch {
                actions.setMicPermissionDenied(true)
                return
            }

            // Unlock AudioContext on user gesture for later TTS auto-play
            if (!cache.audioContext) {
                cache.audioContext = new AudioContext()
            }
            if (cache.audioContext.state === 'suspended') {
                await cache.audioContext.resume()
            }

            cache.mediaStream = stream
            cache.audioChunks = [] as Blob[]
            const recorder = new MediaRecorder(stream)
            cache.mediaRecorder = recorder

            recorder.ondataavailable = (event: BlobEvent) => {
                if (event.data.size > 0) {
                    cache.audioChunks.push(event.data)
                }
            }

            recorder.onstop = () => {
                const mimeType = recorder.mimeType
                const blob = new Blob(cache.audioChunks, { type: mimeType })
                cache.audioChunks = []

                // Release mic
                cache.mediaStream?.getTracks().forEach((t: MediaStreamTrack) => t.stop())
                cache.mediaStream = null

                if (blob.size === 0) {
                    actions.setTranscribing(false)
                    return
                }

                actions.setTranscribing(true)
                api.conversations
                    .transcribe(blob)
                    .then(({ text }) => {
                        actions.setTranscribing(false)
                        if (text?.trim()) {
                            actions.transcriptionComplete(text.trim())
                        } else {
                            lemonToast.warning('No speech detected. Try again.')
                        }
                    })
                    .catch(() => {
                        actions.setTranscribing(false)
                        actions.transcriptionFailed()
                    })
            }

            recorder.start()
            actions.setRecording(true)
            actions.setVoiceModeEnabled(true)
        },

        stopRecording: () => {
            const recorder = cache.mediaRecorder as MediaRecorder | undefined
            if (recorder && recorder.state !== 'inactive') {
                recorder.stop()
            }
            actions.setRecording(false)
        },

        transcriptionComplete: ({ text }) => {
            const tabId = values.activeTabId
            if (!tabId) {
                return
            }
            const mountedMaxLogic = maxLogic.findMounted({ tabId })
            if (mountedMaxLogic) {
                mountedMaxLogic.actions.setQuestion(text)
            }

            const mountedThreadLogic = maxThreadLogic.findMounted()
            if (mountedThreadLogic) {
                mountedThreadLogic.actions.askMax(text)
            }
        },

        transcriptionFailed: () => {
            lemonToast.error('Transcription failed. Please try again.')
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
])
