import { useValues } from 'kea'

import { LemonSkeleton } from '@posthog/lemon-ui'

import { BatchExportRuns } from 'scenes/data-pipelines/batch-exports/BatchExportRuns'

import { hogFunctionBackfillsLogic, HogFunctionBackfillsLogicProps } from '../backfills/hogFunctionBackfillsLogic'

export function HogFunctionRuns({ id }: HogFunctionBackfillsLogicProps): JSX.Element {
    const { configuration, isReady } = useValues(hogFunctionBackfillsLogic({ id }))

    if (!isReady) {
        return (
            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <LemonSkeleton className="w-20 h-8" fade />
                    <LemonSkeleton className="w-32 h-10" fade />
                </div>
                <LemonSkeleton className="w-full h-96" fade />
            </div>
        )
    }

    return <BatchExportRuns id={configuration.batch_export_id!} context="hog_function" />
}
