import { BindLogic, useValues } from 'kea'

import { LemonTab, LemonTabs } from 'lib/lemon-ui/LemonTabs'
import { SceneExport } from 'scenes/sceneTypes'
import { urls } from 'scenes/urls'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'

import { HogbotChat } from './chat/HogbotChat'
import { HogbotStatusIndicator } from './components/HogbotStatusIndicator'
import { hogbotSceneLogic } from './hogbotSceneLogic'
import { HogbotResearch } from './research/HogbotResearch'
import { HogbotTasks } from './tasks/HogbotTasks'

export const scene: SceneExport = {
    component: HogbotScene,
    logic: hogbotSceneLogic,
}

export function HogbotScene({ tabId }: { tabId?: string }): JSX.Element {
    const { activeTab } = useValues(hogbotSceneLogic({ tabId: tabId || '' }))

    const tabs: LemonTab<string>[] = [
        {
            key: 'chat',
            label: 'Chat',
            content: <HogbotChat />,
            link: urls.hogbotChat(),
        },
        {
            key: 'research',
            label: 'Research',
            content: <HogbotResearch />,
            link: urls.hogbotResearch(),
        },
        {
            key: 'tasks',
            label: 'Tasks',
            content: <HogbotTasks />,
            link: urls.hogbotTasks(),
        },
    ]

    return (
        <BindLogic logic={hogbotSceneLogic} props={{ tabId: tabId || '' }}>
            <SceneContent>
                <SceneTitleSection
                    name="Hogbot"
                    description="AI agent sandbox with research and chat capabilities."
                    resourceType={{ type: 'default_icon_type' }}
                    actions={<HogbotStatusIndicator />}
                />
                <LemonTabs activeKey={activeTab} data-attr="hogbot-tabs" tabs={tabs} sceneInset />
            </SceneContent>
        </BindLogic>
    )
}
