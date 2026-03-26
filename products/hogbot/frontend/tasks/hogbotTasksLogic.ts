import { kea, path } from 'kea'
import { loaders } from 'kea-loaders'

import { Task } from 'products/tasks/frontend/types'

import { MOCK_HOGBOT_TASKS } from '../__mocks__/tasksMocks'
import type { hogbotTasksLogicType } from './hogbotTasksLogicType'

export const hogbotTasksLogic = kea<hogbotTasksLogicType>([
    path(['products', 'hogbot', 'frontend', 'tasks', 'hogbotTasksLogic']),
    loaders({
        tasks: [
            [] as Task[],
            {
                loadTasks: async (): Promise<Task[]> => {
                    return MOCK_HOGBOT_TASKS
                },
            },
        ],
    }),
])
