import './VoiceMode.scss'

import { useActions, useValues } from 'kea'
import { useRef } from 'react'

import { IconArrowRight, IconX } from '@posthog/icons'
import { LemonButton } from '@posthog/lemon-ui'

import { cn } from 'lib/utils/css-classes'

import voiceListening from 'public/hedgehog/voice/listening.png'
import voiceTalking from 'public/hedgehog/voice/talking.gif'
import voiceThinking from 'public/hedgehog/voice/thinking.gif'

import { maxLogic } from '../maxLogic'
import { maxThreadLogic } from '../maxThreadLogic'
import { voiceLogic } from '../voiceLogic'

export function VoiceMode(): JSX.Element {
    const {
        recording,
        connecting,
        playbackActive,
        isMouthOpen,
        orbPointerDown,
        ttsLoading,
        activeTabId,
        voiceModeFullscreen,
        voiceModeEnabled,
        micPermissionDenied,
    } = useValues(voiceLogic)
    const { stopRecording, startRecording, stopPlayback, exitVoiceMode, setOrbPointerDown } = useActions(voiceLogic)
    /** Sync immediately so pointerup in the same frame still submits (React state may not have re-rendered). */
    const orbPressActiveRef = useRef(false)
    const { question } = useValues(maxLogic)
    const { threadLoading } = useValues(maxThreadLogic)
    const { askMax } = useActions(maxThreadLogic)

    const isAiSpeaking = playbackActive
    const isUserSpeaking = recording
    const isThinking = threadLoading && !isAiSpeaking && !isUserSpeaking
    /** Hedgehog accepts input while listening, while Max is speaking (to interrupt), or while reconnecting the mic after interrupt if you're still holding. */
    const orbInteractable = playbackActive || recording || (connecting && orbPointerDown)
    // Zen for listening, connecting, recording, and thinking — only swap to gifs during TTS.
    const showZenInOrb = !isAiSpeaking

    // "Listening" only when the STT session is actually recording — otherwise we lie and Send looks broken.
    let statusText = 'Waiting…'
    if (connecting && !orbPointerDown) {
        statusText = 'Connecting…'
    } else if (ttsLoading) {
        statusText = 'Loading voice…'
    } else if (isThinking) {
        statusText = 'Thinking…'
    } else if (orbPointerDown) {
        statusText = 'Release to send…'
    } else if (isAiSpeaking) {
        statusText = 'Hold to interrupt…'
    } else if (recording) {
        statusText = 'Listening…'
    }

    function handleOrbPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
        if (!orbInteractable) {
            return
        }
        if (e.pointerType === 'mouse' && e.button !== 0) {
            return
        }
        e.preventDefault()
        e.currentTarget.setPointerCapture(e.pointerId)
        orbPressActiveRef.current = true
        setOrbPointerDown(true)
        if (playbackActive) {
            stopPlayback()
        }
    }

    function handleOrbPointerEnd(e: React.PointerEvent<HTMLDivElement>): void {
        try {
            e.currentTarget.releasePointerCapture(e.pointerId)
        } catch {
            // Pointer was not captured on this target
        }
        const wasPressingOrb = orbPressActiveRef.current
        orbPressActiveRef.current = false
        setOrbPointerDown(false)
        if (wasPressingOrb && recording) {
            stopRecording()
        }
    }

    /** Mic failed to come back after a reply (or similar) — Send restarts STT instead of doing nothing. */
    const canResumeMic =
        !!voiceModeFullscreen &&
        voiceModeEnabled &&
        activeTabId != null &&
        !recording &&
        !connecting &&
        !playbackActive &&
        !ttsLoading &&
        !isThinking &&
        !micPermissionDenied

    function handleSend(): void {
        if (recording) {
            stopRecording()
        } else if (question.trim()) {
            askMax(question)
        } else if (canResumeMic && activeTabId) {
            startRecording(activeTabId)
        }
    }

    const canSend = recording || question.trim().length > 0 || canResumeMic

    return (
        <div className="flex flex-col flex-1 items-center justify-between overflow-hidden bg-bg-primary">
            {/* Orb area */}
            <div className="flex flex-col flex-1 items-center justify-center gap-6">
                <div
                    data-attr="max-voice-mode-orb"
                    className={cn(
                        'relative flex items-center justify-center w-48 h-48 transition-transform duration-150 ease-out',
                        orbInteractable && 'cursor-grab active:cursor-grabbing touch-none select-none',
                        orbPointerDown && orbInteractable && 'scale-[0.96]',
                        !orbInteractable && 'pointer-events-none'
                    )}
                    role={orbInteractable ? 'button' : undefined}
                    tabIndex={orbInteractable ? 0 : undefined}
                    aria-label={
                        orbInteractable
                            ? 'Hold on the hedgehog to keep talking. While Max is speaking, hold to interrupt and speak. Release to send.'
                            : undefined
                    }
                    onPointerDown={orbInteractable ? handleOrbPointerDown : undefined}
                    onPointerUp={orbInteractable ? handleOrbPointerEnd : undefined}
                    onPointerCancel={orbInteractable ? handleOrbPointerEnd : undefined}
                >
                    {/* Glow ring */}
                    <div
                        className={cn(
                            'absolute inset-0 rounded-full transition-opacity duration-700 VoiceMode__glow',
                            isUserSpeaking || isAiSpeaking ? 'opacity-40' : 'opacity-15'
                        )}
                    />
                    {/* Orb */}
                    <div
                        className={cn(
                            'relative w-40 h-40 rounded-full overflow-hidden flex items-center justify-center pointer-events-none',
                            isUserSpeaking && 'VoiceMode__orb--user',
                            isAiSpeaking && 'VoiceMode__orb--ai',
                            isThinking && 'VoiceMode__orb--thinking',
                            !isUserSpeaking && !isAiSpeaking && !isThinking && 'VoiceMode__orb--idle'
                        )}
                    >
                        {isAiSpeaking ? (
                            <img
                                src={voiceTalking}
                                alt="Speaking"
                                className="relative z-[1] max-w-[78%] max-h-[78%] w-auto h-auto object-contain pointer-events-none select-none"
                                draggable={false}
                                key="voice-mode-ai-talking"
                            />
                        ) : isThinking ? (
                            <img
                                src={voiceThinking}
                                alt=""
                                className="relative z-[1] max-w-[78%] max-h-[78%] w-auto h-auto object-contain pointer-events-none select-none"
                                draggable={false}
                                key="voice-mode-thinking"
                            />
                        ) : (
                            <img
                                src={voiceListening}
                                alt=""
                                className="relative z-[1] max-w-[78%] max-h-[78%] w-auto h-auto object-contain pointer-events-none select-none"
                                draggable={false}
                                key="voice-mode-listening"
                            />
                        )}
                    </div>
                </div>

                <p className="text-sm text-secondary">{statusText}</p>
            </div>

            {/* Controls */}
            <div className="flex items-center justify-center gap-3 pb-10">
                <LemonButton
                    data-attr="max-voice-mode-exit"
                    type="secondary"
                    size="medium"
                    icon={<IconX />}
                    onClick={exitVoiceMode}
                    tooltip="Close voice mode"
                />
                <LemonButton
                    data-attr="max-voice-mode-send"
                    type="primary"
                    size="medium"
                    icon={<IconArrowRight />}
                    onClick={handleSend}
                    tooltip={recording ? 'Stop recording and send' : canResumeMic ? 'Start microphone' : 'Send'}
                    disabledReason={!canSend ? 'Nothing to send' : undefined}
                />
            </div>
        </div>
    )
}
