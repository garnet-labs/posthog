import './VoiceMode.scss'

import { useActions, useValues } from 'kea'

import { IconArrowRight, IconX } from '@posthog/icons'
import { LemonButton } from '@posthog/lemon-ui'

import { cn } from 'lib/utils/css-classes'

import { maxLogic } from '../maxLogic'
import { maxThreadLogic } from '../maxThreadLogic'
import { voiceLogic } from '../voiceLogic'

export function VoiceMode(): JSX.Element {
    const { recording, connecting, playbackActive } = useValues(voiceLogic)
    const { stopRecording, exitVoiceMode } = useActions(voiceLogic)
    const { question } = useValues(maxLogic)
    const { threadLoading } = useValues(maxThreadLogic)
    const { askMax } = useActions(maxThreadLogic)

    const isAiSpeaking = playbackActive
    const isUserSpeaking = recording
    const isThinking = threadLoading && !isAiSpeaking && !isUserSpeaking

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
                            'relative w-40 h-40 rounded-full',
                            isUserSpeaking && 'VoiceMode__orb--user',
                            isAiSpeaking && 'VoiceMode__orb--ai',
                            isThinking && 'VoiceMode__orb--thinking',
                            !isUserSpeaking && !isAiSpeaking && !isThinking && 'VoiceMode__orb--idle'
                        )}
                    />
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
