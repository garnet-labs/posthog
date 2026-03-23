import { BindLogic, useActions, useValues } from 'kea'
import posthog from 'posthog-js'

import { LemonBanner, LemonButton, LemonTab, LemonTabs, Link } from '@posthog/lemon-ui'

import api from 'lib/api'
import { useFeatureFlag } from 'lib/hooks/useFeatureFlag'
import { useOnMountEffect } from 'lib/hooks/useOnMountEffect'
import { IconFeedback } from 'lib/lemon-ui/icons'
import { preflightLogic } from 'scenes/PreflightCheck/preflightLogic'
import { sceneConfigurations } from 'scenes/scenes'
import { Scene, SceneExport } from 'scenes/sceneTypes'
import { Settings } from 'scenes/settings/Settings'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneStickyBar } from '~/layout/scenes/components/SceneStickyBar'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'
import { insightVizDataNodeKey } from '~/queries/nodes/InsightViz/InsightViz'
import { CyclotronJobFiltersType } from '~/types'

import { ErrorTrackingIssueFilteringTool } from '../../components/IssueFilteringTool'
import { issueFiltersLogic } from '../../components/IssueFilters/issueFiltersLogic'
import { issueQueryOptionsLogic } from '../../components/IssueQueryOptions/issueQueryOptionsLogic'
import { exceptionIngestionLogic } from '../../components/SetupPrompt/exceptionIngestionLogic'
import { ErrorTrackingSetupPrompt } from '../../components/SetupPrompt/SetupPrompt'
import { StyleVariables } from '../../components/StyleVariables'
import { issuesDataNodeLogic } from '../../logics/issuesDataNodeLogic'
import { ERROR_TRACKING_LOGIC_KEY } from '../../utils'
import {
    ERROR_TRACKING_SCENE_LOGIC_KEY,
    ErrorTrackingSceneActiveTab,
    errorTrackingSceneLogic,
} from './errorTrackingSceneLogic'
import { ErrorTrackingInsights } from './tabs/insights/ErrorTrackingInsights'
import { IssuesFilters } from './tabs/issues/IssuesFilters'
import { insightProps, IssuesList, ListReloadButton } from './tabs/issues/IssuesList'

const ERROR_TRACKING_ALERT_FILTER_GROUPS: CyclotronJobFiltersType[] = [
    { events: [{ id: '$error_tracking_issue_created', type: 'events' }] },
    { events: [{ id: '$error_tracking_issue_reopened', type: 'events' }] },
    { events: [{ id: '$error_tracking_issue_spiking', type: 'events' }] },
]

export const scene: SceneExport = {
    component: ErrorTrackingScene,
    logic: errorTrackingSceneLogic,
}

export function ErrorTrackingScene(): JSX.Element {
    const { hasSentExceptionEvent, hasSentExceptionEventLoading } = useValues(exceptionIngestionLogic)
    const { activeTab, query } = useValues(errorTrackingSceneLogic)
    const { setActiveTab } = useActions(errorTrackingSceneLogic)
    const hasInsights = useFeatureFlag('ERROR_TRACKING_INSIGHTS')

    useOnMountEffect(() => {
        const utmSource = new URLSearchParams(window.location.search).get('utm_source')
        api.hogFunctions
            .list({
                types: ['internal_destination'],
                filter_groups: ERROR_TRACKING_ALERT_FILTER_GROUPS,
            })
            .then((res) => {
                posthog.capture('error_tracking_issues_list_viewed', {
                    active_tab: activeTab,
                    alert_destination_count: res.results.length,
                    ...(utmSource ? { utm_source: utmSource } : {}),
                })
            })
    })

    const tabs: LemonTab<ErrorTrackingSceneActiveTab>[] = [
        {
            key: 'issues',
            label: 'Issues',

            content: (
                <BindLogic
                    logic={issuesDataNodeLogic}
                    props={{
                        key: insightVizDataNodeKey(insightProps),
                        query: query.source,
                    }}
                >
                    <>
                        <ErrorTrackingIssueFilteringTool />
                        {hasSentExceptionEventLoading || hasSentExceptionEvent ? null : <IngestionStatusCheck />}
                    </>
                    <SceneStickyBar showBorderBottom={false} className="py-3">
                        <IssuesFilters reload={<ListReloadButton />} />
                    </SceneStickyBar>
                    <div className="px-4">
                        <IssuesList />
                    </div>
                </BindLogic>
            ),
        },
        ...(hasInsights
            ? [
                  {
                      key: 'insights' as const,
                      label: 'Insights',
                      content: <ErrorTrackingInsights />,
                  },
              ]
            : []),
        {
            key: 'configuration',
            label: 'Configuration',
            content: (
                <div className="p-4">
                    <Settings
                        logicKey={ERROR_TRACKING_LOGIC_KEY}
                        sectionId="environment-error-tracking"
                        settingId="error-tracking-exception-autocapture"
                        handleLocally
                    />
                </div>
            ),
        },
    ]

    return (
        <StyleVariables>
            <BindLogic logic={issueFiltersLogic} props={{ logicKey: ERROR_TRACKING_SCENE_LOGIC_KEY }}>
                <BindLogic logic={issueQueryOptionsLogic} props={{ logicKey: ERROR_TRACKING_SCENE_LOGIC_KEY }}>
                    <ErrorTrackingSetupPrompt>
                        <SceneContent>
                            <Header />
                            <LemonTabs
                                activeKey={activeTab}
                                onChange={(key) => setActiveTab(key)}
                                tabs={tabs}
                                className="-mt-4 -mx-4 [&>ul]:pl-4 [&>ul]:mb-0"
                            />
                        </SceneContent>
                    </ErrorTrackingSetupPrompt>
                </BindLogic>
            </BindLogic>
        </StyleVariables>
    )
}

const Header = (): JSX.Element => {
    const { isDev } = useValues(preflightLogic)

    const onClick = (): void => {
        setInterval(() => {
            throw new Error('Kaboom !')
        }, 100)
    }

    return (
        <>
            <SceneTitleSection
                name={sceneConfigurations[Scene.ErrorTracking].name}
                description={null}
                resourceType={{
                    type: sceneConfigurations[Scene.ErrorTracking].iconType || 'default_icon_type',
                }}
                actions={
                    <>
                        {isDev ? (
                            <>
                                <LemonButton
                                    size="small"
                                    onClick={() => {
                                        posthog.captureException(new Error('Kaboom !'))
                                    }}
                                >
                                    Send an exception
                                </LemonButton>
                                <LemonButton size="small" onClick={onClick}>
                                    Start exception loop
                                </LemonButton>
                            </>
                        ) : null}
                        <LemonButton
                            size="small"
                            type="secondary"
                            icon={<IconFeedback />}
                            onClick={() => posthog.displaySurvey('019cbd35-c91c-0000-9997-9259dc4cc2ef')}
                        >
                            Feedback
                        </LemonButton>
                        <LemonButton
                            size="small"
                            to="https://posthog.com/docs/error-tracking"
                            type="secondary"
                            targetBlank
                        >
                            Documentation
                        </LemonButton>
                    </>
                }
            />
        </>
    )
}

const IngestionStatusCheck = (): JSX.Element | null => {
    return (
        <LemonBanner type="warning" className="my-2 px-4 pt-4">
            <p>
                <strong>No Exception events have been detected!</strong>
            </p>
            <p>
                To use the Error tracking product, please{' '}
                <Link to="https://posthog.com/docs/error-tracking/installation">
                    enable exception capture within the PostHog SDK
                </Link>{' '}
                (otherwise it'll be a little empty!)
            </p>
        </LemonBanner>
    )
}
