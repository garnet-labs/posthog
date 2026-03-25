import { useActions, useValues } from 'kea'
import { useEffect } from 'react'

import { LemonButton, LemonTable, LemonTag, Spinner } from '@posthog/lemon-ui'

import { TZLabel } from 'lib/components/TZLabel'
import { urls } from 'scenes/urls'

import { Task, TaskRunStatus } from 'products/tasks/frontend/types'

import { hogbotTasksLogic } from './hogbotTasksLogic'

function TaskStatusBadge({ status }: { status: TaskRunStatus | undefined }): JSX.Element {
    const statusConfig: Record<TaskRunStatus, { label: string; type: 'success' | 'warning' | 'danger' | 'default' | 'highlight' | 'completion' | 'caution' | 'muted' }> = {
        [TaskRunStatus.NOT_STARTED]: { label: 'Not started', type: 'default' },
        [TaskRunStatus.QUEUED]: { label: 'Queued', type: 'highlight' },
        [TaskRunStatus.IN_PROGRESS]: { label: 'In progress', type: 'caution' },
        [TaskRunStatus.COMPLETED]: { label: 'Completed', type: 'success' },
        [TaskRunStatus.FAILED]: { label: 'Failed', type: 'danger' },
        [TaskRunStatus.CANCELLED]: { label: 'Cancelled', type: 'muted' },
    }

    const config = status ? statusConfig[status] : { label: 'Unknown', type: 'default' as const }

    return <LemonTag type={config.type}>{config.label}</LemonTag>
}

export function HogbotTasks(): JSX.Element {
    const { tasks, tasksLoading } = useValues(hogbotTasksLogic)
    const { loadTasks } = useActions(hogbotTasksLogic)

    useEffect(() => {
        loadTasks()
    }, [])

    if (tasksLoading) {
        return (
            <div className="flex items-center justify-center py-20">
                <Spinner className="text-2xl" />
            </div>
        )
    }

    return (
        <LemonTable
            dataSource={tasks}
            columns={[
                {
                    title: 'Task',
                    key: 'task',
                    render: (_, task: Task) => (
                        <div>
                            <LemonButton type="tertiary" size="small" to={urls.taskDetail(task.id)} noPadding>
                                <span className="font-mono text-xs text-muted mr-2">{task.slug}</span>
                                <span className="font-medium">{task.title}</span>
                            </LemonButton>
                        </div>
                    ),
                },
                {
                    title: 'Status',
                    key: 'status',
                    width: 140,
                    render: (_, task: Task) => <TaskStatusBadge status={task.latest_run?.status} />,
                },
                {
                    title: 'Created',
                    key: 'created_at',
                    width: 180,
                    render: (_, task: Task) => <TZLabel time={task.created_at} />,
                },
            ]}
            emptyState="No tasks yet. Hogbot will create tasks as it works on research."
            data-attr="hogbot-tasks-table"
        />
    )
}
