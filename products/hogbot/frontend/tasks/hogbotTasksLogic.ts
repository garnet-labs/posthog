import { kea, path } from 'kea'
import { loaders } from 'kea-loaders'

// import api from 'lib/api'
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
                    // TODO: Replace with API call when backend is ready
                    // const response = await api.get(`api/projects/@current/tasks/?origin_product=hogbot`)
                    // return response.results
                    return MOCK_HOGBOT_TASKS
                },
            },
        ],
    }),
])
