import './VoiceMode.scss'

import { useActions, useValues } from 'kea'

import { IconArrowRight, IconX } from '@posthog/icons'
import { LemonButton } from '@posthog/lemon-ui'

import { cn } from 'lib/utils/css-classes'

import voiceClosed from 'public/hedgehog/voice/closed.gif'
import voiceTalking from 'public/hedgehog/voice/talking.gif'
import voiceZen from 'public/hedgehog/voice/zen.svg'

import { maxLogic } from '../maxLogic'
import { maxThreadLogic } from '../maxThreadLogic'
import { voiceLogic } from '../voiceLogic'

export function VoiceMode(): JSX.Element {
    const { recording, connecting, playbackActive, isMouthOpen } = useValues(voiceLogic)
    const { stopRecording, exitVoiceMode } = useActions(voiceLogic)
    const { question } = useValues(maxLogic)
    const { threadLoading } = useValues(maxThreadLogic)
    const { askMax } = useActions(maxThreadLogic)

    const isAiSpeaking = playbackActive
    const isUserSpeaking = recording
    const isThinking = threadLoading && !isAiSpeaking && !isUserSpeaking
    // Zen for listening, connecting, recording, and thinking — only swap to gifs during TTS.
    const showZenInOrb = !isAiSpeaking

    let statusText = 'Listening…'
    if (connecting) {
        statusText = 'Connecting…'
    } else if (isThinking) {
        statusText = 'Thinking…'
    } else if (isAiSpeaking) {
        statusText = 'Speaking…'
    }

    function handleSend(): void {
        if (recording) {
            stopRecording()
        } else if (question.trim()) {
            askMax(question)
        }
    }

    const canSend = recording || question.trim().length > 0

    return (
        <div className="flex flex-col flex-1 items-center justify-between overflow-hidden bg-bg-primary">
            {/* Orb area */}
            <div className="flex flex-col flex-1 items-center justify-center gap-6">
                <div className="relative flex items-center justify-center w-48 h-48">
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
                            'relative w-40 h-40 rounded-full overflow-hidden flex items-center justify-center',
                            isUserSpeaking && 'VoiceMode__orb--user',
                            isAiSpeaking && 'VoiceMode__orb--ai',
                            isThinking && 'VoiceMode__orb--thinking',
                            !isUserSpeaking && !isAiSpeaking && !isThinking && 'VoiceMode__orb--idle'
                        )}
                    >
                        {showZenInOrb ? (
                            <img
                                src={voiceZen}
                                alt=""
                                className="relative z-[1] max-w-[78%] max-h-[78%] w-auto h-auto object-contain pointer-events-none select-none"
                                draggable={false}
                            />
                        ) : isAiSpeaking ? (
                            <img
                                src={isMouthOpen ? voiceTalking : voiceClosed}
                                alt={isMouthOpen ? 'Speaking' : 'Idle'}
                                className="relative z-[1] max-w-[78%] max-h-[78%] w-auto h-auto object-contain pointer-events-none select-none"
                                draggable={false}
                                key={isMouthOpen ? 'voice-mode-ai-talking' : 'voice-mode-ai-closed'}
                            />
                        ) : null}
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
                    tooltip={recording ? 'Stop recording and send' : 'Send'}
                    disabledReason={!canSend ? 'Nothing to send' : undefined}
                />
            </div>
        </div>
    )
}
