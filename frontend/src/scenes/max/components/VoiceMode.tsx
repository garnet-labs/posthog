import './VoiceMode.scss'

import { useActions, useValues } from 'kea'
import { useEffect, useMemo, useRef, useState } from 'react'

import { IconMicrophone, IconX } from '@posthog/icons'
import { LemonButton } from '@posthog/lemon-ui'

import { cn } from 'lib/utils/css-classes'

function IconMicrophoneOff(): JSX.Element {
    return (
        <span className="relative inline-flex items-center justify-center">
            <IconMicrophone />
            <span className="absolute inset-0 flex items-center justify-center">
                <span className="block w-[120%] h-[1.5px] bg-current rotate-[-45deg] rounded-full" />
            </span>
        </span>
    )
}

import { Query } from '~/queries/Query/Query'
import { ArtifactContentType } from '~/queries/schema/schema-assistant-messages'
import { isFunnelsQuery } from '~/queries/utils'

import voiceListening from 'public/hedgehog/voice/listening.png'
import voiceTalking from 'public/hedgehog/voice/talking.gif'
import voiceThinking from 'public/hedgehog/voice/thinking.gif'

import { maxThreadLogic, ThreadMessage } from '../maxThreadLogic'
import { isArtifactMessage, isMultiVisualizationMessage, visualizationTypeToQuery } from '../utils'
import { voiceLogic } from '../voiceLogic'

/** Animated sinusoid whose amplitude follows the voice input level. */
function SinusoidWave({ amplitude }: { amplitude: number }): JSX.Element {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const animRef = useRef<number>(0)
    const phaseRef = useRef(0)
    const smoothedRef = useRef(0)
    const amplitudeRef = useRef(amplitude)

    // Keep ref in sync so the animation loop always sees the latest value
    amplitudeRef.current = amplitude

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) {
            return
        }
        const ctx = canvas.getContext('2d')
        if (!ctx) {
            return
        }

        let lastTime = performance.now()

        const draw = (now: number): void => {
            const dt = (now - lastTime) / 1000
            lastTime = now

            const target = amplitudeRef.current
            const alpha = Math.min(1, dt * 8)
            smoothedRef.current += alpha * (target - smoothedRef.current)

            phaseRef.current += dt * 2

            const dpr = window.devicePixelRatio || 1
            const rect = canvas.getBoundingClientRect()
            const w = rect.width * dpr
            const h = rect.height * dpr
            if (canvas.width !== w || canvas.height !== h) {
                canvas.width = w
                canvas.height = h
            }

            ctx.clearRect(0, 0, w, h)

            const midY = h / 2
            const totalAmp = h * 0.4 * smoothedRef.current

            const waves = [
                { freq: 1.5, speed: 1.0, opacity: 0.6, color: 'var(--color-ai)' },
                { freq: 2.2, speed: -0.7, opacity: 0.3, color: '#38bdf8' },
                { freq: 3.0, speed: 1.3, opacity: 0.2, color: '#6c47ff' },
            ]

            for (const wave of waves) {
                ctx.beginPath()
                ctx.globalAlpha = wave.opacity
                if (wave.color.startsWith('var(')) {
                    ctx.strokeStyle = getComputedStyle(canvas).getPropertyValue('--color-ai').trim() || '#a855f7'
                } else {
                    ctx.strokeStyle = wave.color
                }
                ctx.lineWidth = 2 * dpr

                for (let x = 0; x <= w; x++) {
                    const t = x / w
                    const y = midY + Math.sin(t * Math.PI * 2 * wave.freq + phaseRef.current * wave.speed) * totalAmp
                    if (x === 0) {
                        ctx.moveTo(x, y)
                    } else {
                        ctx.lineTo(x, y)
                    }
                }
                ctx.stroke()
            }
            ctx.globalAlpha = 1

            animRef.current = requestAnimationFrame(draw)
        }

        animRef.current = requestAnimationFrame(draw)
        return () => cancelAnimationFrame(animRef.current)
    }, []) // Run once — reads amplitude via ref

    return <canvas ref={canvasRef} className="w-full h-16" />
}

/** Find the last visualization artifact or multi-viz message in the thread. */
function useLatestArtifact(thread: ThreadMessage[]): {
    query: ReturnType<typeof visualizationTypeToQuery>
    isFunnel: boolean
    key: string
} | null {
    return useMemo(() => {
        for (let i = thread.length - 1; i >= 0; i--) {
            const msg = thread[i]
            if (
                isArtifactMessage(msg) &&
                msg.content.content_type === ArtifactContentType.Visualization &&
                msg.status === 'completed'
            ) {
                const q = visualizationTypeToQuery(msg.content)
                if (q) {
                    return { query: q, isFunnel: isFunnelsQuery(msg.content.query), key: msg.id ?? `art-${i}` }
                }
            }
            if (isMultiVisualizationMessage(msg) && msg.visualizations.length > 0) {
                const viz = msg.visualizations[0]
                const q = visualizationTypeToQuery(viz)
                if (q) {
                    return { query: q, isFunnel: false, key: msg.id ?? `mviz-${i}` }
                }
            }
        }
        return null
    }, [thread])
}

/** Hedgehog orb — reused in both centered and corner positions. */
function HedgehogOrb({
    isAiSpeaking,
    isThinking,
    isMouthOpen,
    statusText,
    orbInteractable,
    orbPointerDown,
    imgClassName,
    onPointerDown,
    onPointerUp,
    onPointerCancel,
}: {
    isAiSpeaking: boolean
    isThinking: boolean
    isMouthOpen: boolean
    statusText: string
    orbInteractable: boolean
    orbPointerDown: boolean
    imgClassName: string
    onPointerDown?: (e: React.PointerEvent<HTMLDivElement>) => void
    onPointerUp?: (e: React.PointerEvent<HTMLDivElement>) => void
    onPointerCancel?: (e: React.PointerEvent<HTMLDivElement>) => void
}): JSX.Element {
    return (
        <div
            data-attr="max-voice-mode-orb"
            className={cn(
                'relative flex items-center justify-center transition-transform duration-150 ease-out',
                orbInteractable && 'cursor-grab active:cursor-grabbing touch-none select-none',
                orbPointerDown && orbInteractable && 'scale-[0.96]',
                !orbInteractable && 'pointer-events-none'
            )}
            role={orbInteractable ? 'button' : undefined}
            tabIndex={orbInteractable ? 0 : undefined}
            aria-label={orbInteractable ? 'Voice mode active' : undefined}
            onPointerDown={orbInteractable ? onPointerDown : undefined}
            onPointerUp={orbInteractable ? onPointerUp : undefined}
            onPointerCancel={orbInteractable ? onPointerCancel : undefined}
        >
            <div className="absolute inset-[-12%] rounded-full pointer-events-none VoiceMode__glow" />

            {/* Speech bubble */}
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 z-20 pointer-events-none">
                <div className="relative bg-bg-light border border-border rounded-full px-5 py-2 text-sm font-semibold text-primary whitespace-nowrap shadow-md">
                    {statusText}
                    <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rotate-45 bg-bg-light border-r border-b border-border" />
                </div>
            </div>

            {/* Hedgehog image */}
            <div className="relative z-[10] flex items-center justify-center pointer-events-none">
                {isAiSpeaking ? (
                    <img
                        src={voiceTalking}
                        alt="Speaking"
                        className={cn(imgClassName, 'object-contain pointer-events-none select-none')}
                        draggable={false}
                        key="voice-mode-ai-talking"
                    />
                ) : isThinking ? (
                    <img
                        src={voiceThinking}
                        alt=""
                        className={cn(imgClassName, 'object-contain pointer-events-none select-none')}
                        draggable={false}
                        key="voice-mode-thinking"
                    />
                ) : (
                    <img
                        src={isMouthOpen ? voiceTalking : voiceListening}
                        alt={isMouthOpen ? 'Speaking' : 'Idle'}
                        className={cn(imgClassName, 'object-contain pointer-events-none select-none')}
                        draggable={false}
                        key="voice-mode-listening"
                    />
                )}
            </div>
        </div>
    )
}

const QUERY_CONTEXT_VOICE = { limitContext: 'posthog_ai' } as const

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
        mouthOpenness,
    } = useValues(voiceLogic)
    const { stopRecording, startRecording, stopPlayback, exitVoiceMode, setOrbPointerDown } = useActions(voiceLogic)
    const orbPressActiveRef = useRef(false)
    const { threadLoading, threadGrouped } = useValues(maxThreadLogic)

    const latestArtifact = useLatestArtifact(threadGrouped)
    // Track the key so we re-trigger the entrance animation when the artifact changes
    const prevArtifactKeyRef = useRef<string | null>(null)
    const [animKey, setAnimKey] = useState(0)

    useEffect(() => {
        if (latestArtifact && latestArtifact.key !== prevArtifactKeyRef.current) {
            prevArtifactKeyRef.current = latestArtifact.key
            setAnimKey((k) => k + 1)
        }
    }, [latestArtifact])

    const hasArtifact = !!latestArtifact

    const isAiSpeaking = playbackActive
    const isThinking = threadLoading && !isAiSpeaking && !recording
    const orbInteractable = playbackActive || recording || (connecting && orbPointerDown)

    let statusText = 'Waiting…'
    if (connecting && !orbPointerDown) {
        statusText = 'Connecting…'
    } else if (ttsLoading) {
        statusText = 'Loading voice…'
    } else if (isThinking) {
        statusText = 'Thinking…'
    } else if (isAiSpeaking) {
        statusText = 'Speaking…'
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

    function handleMicToggle(): void {
        if (recording) {
            stopRecording()
        } else if (canResumeMic && activeTabId) {
            startRecording(activeTabId)
        }
    }

    const micToggleable = recording || canResumeMic

    const orbProps = {
        isAiSpeaking,
        isThinking,
        isMouthOpen,
        statusText,
        orbInteractable,
        orbPointerDown,
        onPointerDown: handleOrbPointerDown,
        onPointerUp: handleOrbPointerEnd,
        onPointerCancel: handleOrbPointerEnd,
    }

    return (
        <div className="relative flex flex-col flex-1 items-center justify-between overflow-hidden bg-bg-primary">
            {hasArtifact ? (
                <>
                    {/* Hedgehog in top-right corner with speech bubble */}
                    <div className="absolute top-14 right-4 z-30 VoiceMode__hedgehog-corner">
                        <div className="w-44 h-44">
                            <HedgehogOrb {...orbProps} imgClassName="w-40 h-40" />
                        </div>
                    </div>

                    {/* Artifact in the center */}
                    <div
                        key={animKey}
                        className="flex flex-col flex-1 items-center justify-center w-full px-6 VoiceMode__artifact-enter"
                    >
                        <div
                            className={cn(
                                'w-full max-w-3xl rounded-lg border border-border bg-bg-light shadow-lg overflow-hidden',
                                latestArtifact.isFunnel ? 'h-[580px]' : 'h-96'
                            )}
                        >
                            <Query query={latestArtifact.query!} readOnly embedded context={QUERY_CONTEXT_VOICE} />
                        </div>
                    </div>
                </>
            ) : (
                <>
                    {/* Centered hedgehog orb (default — no artifact) */}
                    <div className="flex flex-col flex-1 items-center justify-center gap-2">
                        <div className="w-68 h-68">
                            <HedgehogOrb {...orbProps} imgClassName="w-64 h-64" />
                        </div>
                    </div>
                </>
            )}

            {/* Sinusoid wave driven by voice amplitude */}
            <div className="w-full px-8 mb-8">
                <SinusoidWave amplitude={mouthOpenness} />
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
                    data-attr="max-voice-mode-mic-toggle"
                    type={recording ? 'primary' : 'secondary'}
                    status={recording ? 'default' : 'danger'}
                    size="medium"
                    icon={recording ? <IconMicrophone /> : <IconMicrophoneOff />}
                    onClick={handleMicToggle}
                    tooltip={recording ? 'Mute microphone' : 'Unmute microphone'}
                    disabledReason={!micToggleable ? 'Microphone unavailable' : undefined}
                />
            </div>
        </div>
    )
}
