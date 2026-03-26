import { useActions, useValues } from 'kea'

import { LemonButton, LemonTable, LemonTableColumns, LemonTag, LemonTagType, Link } from '@posthog/lemon-ui'

import { sourceWizardLogic } from 'scenes/data-warehouse/new/sourceWizardLogic'
import { dataWarehouseSettingsLogic } from 'scenes/data-warehouse/settings/dataWarehouseSettingsLogic'
import { buildTableQueryUrl } from 'scenes/data-warehouse/utils'

import { SceneSection } from '~/layout/scenes/components/SceneSection'
import { ExternalDataSourceSchema } from '~/types'

export function getPreviewQueryUrl(
    tableName: string,
    accessMethod: 'warehouse' | 'direct' | undefined,
    sourceId?: string | null
): string {
    return buildTableQueryUrl(tableName, accessMethod === 'direct' ? (sourceId ?? undefined) : undefined)
}

export const SyncProgressStep = (): JSX.Element => {
    const { sourceId, isWrapped } = useValues(sourceWizardLogic)
    const { cancelWizard } = useActions(sourceWizardLogic)
    const { dataWarehouseSources, dataWarehouseSourcesLoading } = useValues(dataWarehouseSettingsLogic)
    const source = dataWarehouseSources?.results.find((n) => n.id === sourceId)
    const schemas = source?.schemas ?? []
    const sourceAccessMethod = source?.access_method
    const isDirectQuerySource = sourceAccessMethod === 'direct'

    const getSyncStatus = (schema: ExternalDataSourceSchema): { status: string; tagType: LemonTagType } => {
        if (isDirectQuerySource) {
            return schema.should_sync
                ? { status: 'Enabled', tagType: 'success' }
                : { status: 'Hidden', tagType: 'default' }
        }

        if (!schema.should_sync) {
            return {
                status: 'Not synced',
                tagType: 'default',
            }
        }

        if (schema.status === 'Running') {
            return {
                status: 'Syncing...',
                tagType: 'primary',
            }
        }

        if (schema.status === 'Completed') {
            return {
                status: 'Completed',
                tagType: 'success',
            }
        }

        return {
            status: 'Error',
            tagType: 'danger',
        }
    }

    const columns: LemonTableColumns<ExternalDataSourceSchema> = [
        {
            title: 'Table',
            key: 'table',
            render: function RenderTable(_, schema) {
                if (!schema.table) {
                    return schema.label ?? schema.name
                }

                return (
                    <Link
                        to={getPreviewQueryUrl(schema.table.name, sourceAccessMethod, sourceId)}
                        onClick={() => cancelWizard()}
                    >
                        {schema.label ?? schema.name}
                    </Link>
                )
            },
        },
        {
            title: 'Status',
            key: 'status',
            render: function RenderStatus(_, schema) {
                const { status, tagType } = getSyncStatus(schema)

                return <LemonTag type={tagType}>{status}</LemonTag>
            },
        },
    ]

    if (!isWrapped) {
        columns.push({
            key: 'actions',
            width: 0,
            render: function RenderStatus(_, schema) {
                if (schema.table && (isDirectQuerySource || schema.status === 'Completed')) {
                    return (
                        <LemonButton
                            className="my-1"
                            type="primary"
                            onClick={cancelWizard}
                            to={getPreviewQueryUrl(schema.table.name, sourceAccessMethod, sourceId)}
                        >
                            Query
                        </LemonButton>
                    )
                }

                return ''
            },
        })
    }

    return (
        <SceneSection
            title={
                isDirectQuerySource
                    ? "You're all set! Your enabled tables are now available in the SQL editor."
                    : "You're all set! We'll import the data in the background, and after it's done, you will be able to query it in PostHog."
            }
        >
            <LemonTable
                emptyState="No schemas selected"
                dataSource={schemas}
                loading={dataWarehouseSourcesLoading}
                disableTableWhileLoading={false}
                columns={columns}
            />
        </SceneSection>
    )
}
