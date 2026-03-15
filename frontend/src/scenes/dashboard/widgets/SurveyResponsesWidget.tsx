import { useCallback, useEffect, useState } from 'react'

import { IconComment } from '@posthog/icons'
import { LemonSkeleton } from '@posthog/lemon-ui'

import api from 'lib/api'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { LemonDialog } from 'lib/lemon-ui/LemonDialog'
import { LemonTag } from 'lib/lemon-ui/LemonTag'
import { lemonToast } from 'lib/lemon-ui/LemonToast/LemonToast'

import { EventType } from '~/types'

interface SurveyResponsesWidgetProps {
    tileId: number
    config: Record<string, any>
    refreshKey?: number
    effectiveDateFrom?: string
    effectiveDateTo?: string
}

interface SurveyQuestion {
    id: string
    question: string
    response?: any
}

type SurveyStatus = 'draft' | 'running' | 'complete'

interface SurveyData {
    name: string
    start_date: string | null
    end_date: string | null
}

function getSurveyStatus(survey: SurveyData): SurveyStatus {
    if (!survey.start_date) {
        return 'draft'
    }
    if (!survey.end_date) {
        return 'running'
    }
    return 'complete'
}

function getStatusTagType(status: SurveyStatus): 'success' | 'default' | 'completion' {
    switch (status) {
        case 'running':
            return 'success'
        case 'complete':
            return 'completion'
        case 'draft':
        default:
            return 'default'
    }
}

function getStatusLabel(status: SurveyStatus): string {
    switch (status) {
        case 'running':
            return 'Running'
        case 'complete':
            return 'Complete'
        case 'draft':
        default:
            return 'Draft'
    }
}

function SurveyResponsesWidget({
    config,
    refreshKey,
    effectiveDateFrom,
    effectiveDateTo,
}: SurveyResponsesWidgetProps): JSX.Element {
    const [responses, setResponses] = useState<EventType[]>([])
    const [surveyName, setSurveyName] = useState<string | null>(null)
    const [surveyData, setSurveyData] = useState<SurveyData | null>(null)
    const [loading, setLoading] = useState(true)
    const [actionLoading, setActionLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const surveyId = config.survey_id
    const showControls = config.show_controls !== false

    const fetchSurvey = useCallback(() => {
        if (!surveyId) {
            return
        }

        api.get(`api/projects/@current/surveys/${surveyId}`)
            .then((survey: any) => {
                setSurveyName(survey.name)
                setSurveyData({
                    name: survey.name,
                    start_date: survey.start_date ?? null,
                    end_date: survey.end_date ?? null,
                })
            })
            .catch(() => {
                // Survey data is non-critical, silently ignore
            })
    }, [surveyId])

    // Fetch survey definition only when surveyId changes (not on refreshKey or date changes)
    useEffect(() => {
        fetchSurvey()
    }, [fetchSurvey])

    const fetchResponses = useCallback(() => {
        if (!surveyId) {
            setError('No survey configured. Edit this widget to select a survey.')
            setLoading(false)
            return
        }

        setLoading(true)
        setError(null)

        api.events
            .list(
                {
                    event: 'survey sent',
                    properties: JSON.stringify([
                        { key: '$survey_id', value: surveyId, operator: 'exact', type: 'event' },
                    ]),
                    ...(effectiveDateFrom ? { after: effectiveDateFrom } : {}),
                    ...(effectiveDateTo ? { before: effectiveDateTo } : {}),
                },
                20
            )
            .then((data) => {
                setResponses(data.results || [])
                setLoading(false)
            })
            .catch(() => {
                setError('Failed to load survey responses')
                setLoading(false)
            })
    }, [surveyId, effectiveDateFrom, effectiveDateTo])

    useEffect(() => {
        fetchResponses()
    }, [fetchResponses, refreshKey])

    const handleLaunch = (): void => {
        LemonDialog.open({
            title: 'Launch survey?',
            description: `Are you sure you want to launch "${surveyName || 'this survey'}"? It will start collecting responses immediately.`,
            primaryButton: {
                children: 'Launch',
                onClick: () => {
                    setActionLoading(true)
                    api.update(`api/projects/@current/surveys/${surveyId}`, {
                        start_date: new Date().toISOString(),
                    })
                        .then(() => {
                            lemonToast.success('Survey launched')
                            fetchSurvey()
                        })
                        .catch(() => {
                            lemonToast.error('Failed to launch survey')
                        })
                        .finally(() => {
                            setActionLoading(false)
                        })
                },
            },
            secondaryButton: {
                children: 'Cancel',
            },
        })
    }

    const handlePause = (): void => {
        setActionLoading(true)
        api.update(`api/projects/@current/surveys/${surveyId}`, {
            end_date: new Date().toISOString(),
        })
            .then(() => {
                lemonToast.success('Survey paused')
                fetchSurvey()
            })
            .catch(() => {
                lemonToast.error('Failed to pause survey')
            })
            .finally(() => {
                setActionLoading(false)
            })
    }

    const handleResume = (): void => {
        setActionLoading(true)
        api.update(`api/projects/@current/surveys/${surveyId}`, {
            end_date: null,
        })
            .then(() => {
                lemonToast.success('Survey resumed')
                fetchSurvey()
            })
            .catch(() => {
                lemonToast.error('Failed to resume survey')
            })
            .finally(() => {
                setActionLoading(false)
            })
    }

    const surveyStatus = surveyData ? getSurveyStatus(surveyData) : null

    const actionsBar =
        showControls && surveyData && surveyStatus ? (
            <div className="px-3 py-2 border-b border-border-light flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                    <LemonTag type={getStatusTagType(surveyStatus)} size="small">
                        {getStatusLabel(surveyStatus)}
                    </LemonTag>
                    <span className="text-xs text-muted">
                        {responses.length} response{responses.length !== 1 ? 's' : ''}
                    </span>
                </div>
                <div className="shrink-0">
                    {surveyStatus === 'draft' && (
                        <LemonButton type="primary" size="xsmall" onClick={handleLaunch} loading={actionLoading}>
                            Launch
                        </LemonButton>
                    )}
                    {surveyStatus === 'running' && (
                        <LemonButton type="secondary" size="xsmall" onClick={handlePause} loading={actionLoading}>
                            Pause
                        </LemonButton>
                    )}
                    {surveyStatus === 'complete' && (
                        <LemonButton type="secondary" size="xsmall" onClick={handleResume} loading={actionLoading}>
                            Resume
                        </LemonButton>
                    )}
                </div>
            </div>
        ) : null

    if (loading) {
        return (
            <div className="h-full overflow-auto">
                {actionsBar}
                <div className="p-3 space-y-3">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <div key={i} className="space-y-1">
                            <LemonSkeleton className="h-3 w-1/3" />
                            <LemonSkeleton className="h-4 w-full" />
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="h-full overflow-auto">
                {actionsBar}
                <div className="p-4 flex flex-col items-center justify-center h-full text-muted gap-2">
                    <IconComment className="text-3xl mb-1" />
                    <span className="text-center">{error}</span>
                    <LemonButton type="secondary" size="small" onClick={fetchResponses}>
                        Retry
                    </LemonButton>
                </div>
            </div>
        )
    }

    if (responses.length === 0) {
        const hasDateFilter = Boolean(effectiveDateFrom || effectiveDateTo)
        return (
            <div className="h-full overflow-auto">
                {actionsBar}
                <div className="p-4 flex flex-col items-center justify-center h-full text-muted">
                    <IconComment className="text-3xl mb-2" />
                    <span>
                        {hasDateFilter
                            ? 'No responses in this time range'
                            : `No responses yet${surveyName ? ` for ${surveyName}` : ''}`}
                    </span>
                </div>
            </div>
        )
    }

    return (
        <div className="h-full overflow-auto">
            {actionsBar}
            {!showControls && (
                <div className="px-3 py-2 border-b border-border-light bg-surface-secondary">
                    <span className="text-xs font-medium text-muted">
                        Showing {responses.length} response{responses.length !== 1 ? 's' : ''}
                    </span>
                    {surveyName && <span className="text-xs text-muted ml-1">&middot; {surveyName}</span>}
                </div>
            )}
            {responses.map((response) => {
                const props = response.properties || {}

                // Extract questions and responses from event properties
                // Questions are in $survey_questions with {id, question, response}
                // Responses are also in $survey_response_{question_uuid}
                const surveyQuestions: SurveyQuestion[] = props.$survey_questions || []
                const questionResponses: { question: string; value: string }[] = []

                if (surveyQuestions.length > 0) {
                    // Use $survey_questions which has the questions with their UUIDs
                    for (const q of surveyQuestions) {
                        const responseKey = `$survey_response_${q.id}`
                        const val = props[responseKey] ?? q.response
                        if (val != null && val !== '') {
                            const displayVal = Array.isArray(val) ? val.join(', ') : String(val)
                            questionResponses.push({ question: q.question, value: displayVal })
                        }
                    }
                } else {
                    // Fallback: legacy format with $survey_response, $survey_response_1, etc.
                    if (props.$survey_response != null) {
                        questionResponses.push({ question: '', value: String(props.$survey_response) })
                    }
                    for (let i = 1; i <= 10; i++) {
                        const key = `$survey_response_${i}`
                        if (props[key] != null) {
                            questionResponses.push({ question: '', value: String(props[key]) })
                        }
                    }
                }

                return (
                    <div
                        key={response.id}
                        className="mx-2 my-2 p-2.5 rounded-lg border border-border-light hover:border-border"
                    >
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-medium">
                                {response.person?.properties?.email ||
                                    response.person?.properties?.name ||
                                    response.distinct_id ||
                                    'Anonymous'}
                            </span>
                            <TZLabel time={response.timestamp} className="text-xs text-muted" />
                        </div>
                        {questionResponses.length > 0 ? (
                            <div className="space-y-2">
                                {questionResponses.map((qr, i) => (
                                    <div key={i}>
                                        {qr.question && <div className="text-xs text-muted mb-0.5">{qr.question}</div>}
                                        <div className="text-sm">{qr.value}</div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="text-sm text-muted italic">No response data</div>
                        )}
                    </div>
                )
            })}
        </div>
    )
}

export default SurveyResponsesWidget
