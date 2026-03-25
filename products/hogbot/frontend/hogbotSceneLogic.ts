import { actions, kea, key, path, props, reducers } from 'kea'

import { tabAwareUrlToAction } from 'lib/logic/scenes/tabAwareUrlToAction'
import { urls } from 'scenes/urls'

import type { hogbotSceneLogicType } from './hogbotSceneLogicType'
import { HogbotSceneLogicProps, HogbotTab } from './types'

export const hogbotSceneLogic = kea<hogbotSceneLogicType>([
    path(['products', 'hogbot', 'frontend', 'hogbotSceneLogic']),
    props({} as HogbotSceneLogicProps),
    key((props) => props.tabId),
    actions({
        setActiveTab: (activeTab: HogbotTab) => ({ activeTab }),
    }),
    reducers({
        activeTab: [
            'chat' as HogbotTab,
            {
                setActiveTab: (_, { activeTab }) => activeTab,
            },
        ],
    }),
    tabAwareUrlToAction(({ actions }) => ({
        [urls.hogbotChat()]: () => {
            actions.setActiveTab('chat')
        },
        [urls.hogbotResearch()]: () => {
            actions.setActiveTab('research')
        },
        [urls.hogbotTasks()]: () => {
            actions.setActiveTab('tasks')
        },
    })),
])
