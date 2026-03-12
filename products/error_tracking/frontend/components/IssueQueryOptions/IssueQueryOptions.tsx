import { useActions, useValues } from 'kea'

import { IconRefresh } from '@posthog/icons'
import { LemonButton, LemonMenu, LemonSelect, Spinner } from '@posthog/lemon-ui'

import { issuesDataNodeLogic } from '../../logics/issuesDataNodeLogic'
import { ORDER_BY_OPTIONS, issueQueryOptionsLogic } from './issueQueryOptionsLogic'

export const IssueQueryOptions = (): JSX.Element => {
    return (
        <span className="flex items-center gap-2">
            <IssueReloadButton />
            <IssueSortOptions />
        </span>
    )
}

export const IssueSortOptions = (): JSX.Element => {
    const { orderBy, orderDirection } = useValues(issueQueryOptionsLogic)
    const { setOrderBy, setOrderDirection } = useActions(issueQueryOptionsLogic)

    return (
        <div className="flex items-center gap-1">
            <span>Sort by:</span>

            <LemonMenu
                items={[
                    {
                        label: ORDER_BY_OPTIONS['last_seen'],
                        onClick: () => setOrderBy('last_seen'),
                    },
                    {
                        label: ORDER_BY_OPTIONS['first_seen'],
                        onClick: () => setOrderBy('first_seen'),
                    },
                    {
                        label: ORDER_BY_OPTIONS['occurrences'],
                        onClick: () => setOrderBy('occurrences'),
                    },
                    {
                        label: ORDER_BY_OPTIONS['users'],
                        onClick: () => setOrderBy('users'),
                    },
                    {
                        label: ORDER_BY_OPTIONS['sessions'],
                        onClick: () => setOrderBy('sessions'),
                    },
                ]}
            >
                <LemonButton size="small" type="secondary">
                    {ORDER_BY_OPTIONS[orderBy]}
                </LemonButton>
            </LemonMenu>

            <LemonSelect
                onChange={setOrderDirection}
                value={orderDirection}
                options={[
                    {
                        value: 'DESC',
                        label: 'Descending',
                    },
                    {
                        value: 'ASC',
                        label: 'Ascending',
                    },
                ]}
                size="small"
            />
        </div>
    )
}

export const IssueReloadButton = (): JSX.Element => {
    const { responseLoading } = useValues(issuesDataNodeLogic)
    const { reloadData, cancelQuery } = useActions(issuesDataNodeLogic)

    return (
        <LemonButton
            type="tertiary"
            size="small"
            onClick={() => {
                if (responseLoading) {
                    cancelQuery()
                } else {
                    reloadData()
                }
            }}
            icon={responseLoading ? <Spinner textColored /> : <IconRefresh />}
            tooltip={responseLoading ? 'Cancel' : 'Reload'}
        />
    )
}
