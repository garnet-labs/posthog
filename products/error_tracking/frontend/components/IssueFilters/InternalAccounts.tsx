import { useActions, useValues } from 'kea'
import { useEffect } from 'react'

import { IconBolt, IconChevronRight, IconGear } from '@posthog/icons'
import { LemonButton, LemonMenu, LemonMenuItems } from '@posthog/lemon-ui'

import { quickFiltersLogic, QuickFiltersModal, quickFiltersModalLogic } from 'lib/components/QuickFilters'
import { quickFiltersSectionLogic } from 'lib/components/QuickFilters/quickFiltersSectionLogic'
import { filterTestAccountsDefaultsLogic } from 'scenes/settings/environment/filterTestAccountDefaultsLogic'
import { teamLogic } from 'scenes/teamLogic'
import { urls } from 'scenes/urls'

import { ErrorTrackingIssue, ErrorTrackingIssueAssignee, QuickFilterContext } from '~/queries/schema/schema-general'
import { QuickFilter } from '~/types'

import { AssigneeDropdown } from '../Assignee/AssigneeDropdown'
import { assigneeSelectLogic } from '../Assignee/assigneeSelectLogic'
import { StatusIndicator } from '../Indicators'
import { issueQueryOptionsLogic } from '../IssueQueryOptions/issueQueryOptionsLogic'
import { issueFiltersLogic } from './issueFiltersLogic'

interface FilterSettingsMenuProps {
    quickFilterContext?: QuickFilterContext
    logicKey?: string
    showIssueFilters?: boolean
}

export const FilterSettingsMenu = (props: FilterSettingsMenuProps): JSX.Element => {
    const { showIssueFilters = true } = props
    // Conditionally render to avoid mounting issueQueryOptionsLogic
    // in contexts where it has no BindLogic (e.g. the issue detail scene)
    if (showIssueFilters) {
        return <FilterSettingsMenuWithIssueOptions {...props} />
    }
    return <FilterSettingsMenuCore {...props} issueFilterItems={[]} />
}

const FilterSettingsMenuWithIssueOptions = (props: FilterSettingsMenuProps): JSX.Element => {
    const { status, assignee } = useValues(issueQueryOptionsLogic)
    const { setStatus, setAssignee } = useActions(issueQueryOptionsLogic)

    const statusOptions: { value: ErrorTrackingIssue['status']; label: string }[] = [
        { value: 'active', label: 'Active' },
        { value: 'resolved', label: 'Resolved' },
        { value: 'suppressed', label: 'Suppressed' },
    ]

    const issueFilterItems: LemonMenuItems[number]['items'] = [
        {
            label: 'Status',
            sideIcon: <IconChevronRight className="size-3" />,
            items: statusOptions.map((opt) => ({
                label: <StatusIndicator status={opt.value} size="small" />,
                active: status === opt.value || (!status && opt.value === 'active'),
                onClick: () => setStatus(opt.value),
            })),
        },
        {
            label: 'Assignee',
            sideIcon: <IconChevronRight className="size-3" />,
            custom: true,
            items: [
                {
                    label: () => (
                        <AssigneeSubmenu assignee={assignee ?? null} onChange={(value) => setAssignee(value)} />
                    ),
                },
            ],
        },
    ]

    return <FilterSettingsMenuCore {...props} issueFilterItems={issueFilterItems} />
}

const FilterSettingsMenuCore = ({
    quickFilterContext,
    logicKey,
    issueFilterItems,
}: FilterSettingsMenuProps & {
    issueFilterItems: LemonMenuItems[number]['items']
}): JSX.Element => {
    const { filterTestAccounts } = useValues(issueFiltersLogic)
    const { setFilterTestAccounts } = useActions(issueFiltersLogic)
    const { currentTeam } = useValues(teamLogic)
    const hasFilters = (currentTeam?.test_account_filters || []).length > 0
    const { setLocalDefault } = useActions(filterTestAccountsDefaultsLogic)

    const { quickFilters } = useValues(
        quickFiltersLogic({ context: quickFilterContext || QuickFilterContext.ErrorTrackingIssueFilters })
    )
    const { selectedQuickFilters } = useValues(
        quickFiltersSectionLogic({
            context: quickFilterContext || QuickFilterContext.ErrorTrackingIssueFilters,
            logicKey,
        })
    )
    const { setQuickFilterValue, clearQuickFilter } = useActions(
        quickFiltersSectionLogic({
            context: quickFilterContext || QuickFilterContext.ErrorTrackingIssueFilters,
            logicKey,
        })
    )

    const checked = hasFilters ? filterTestAccounts : false

    const toggle = (): void => {
        if (hasFilters) {
            setFilterTestAccounts(!filterTestAccounts)
            setLocalDefault(!filterTestAccounts)
        }
    }

    const quickFilterItems: LemonMenuItems[number]['items'] = quickFilterContext
        ? quickFilters.map((filter: QuickFilter) => {
              const selectedFilter = selectedQuickFilters[filter.property_name]
              const selectedOptionId = selectedFilter?.optionId || null

              if (filter.options.length === 1) {
                  const opt = filter.options[0]
                  const isActive = selectedOptionId === opt.id
                  return {
                      label: filter.name,
                      active: isActive,
                      onClick: () =>
                          isActive
                              ? clearQuickFilter(filter.property_name)
                              : setQuickFilterValue(filter.property_name, opt),
                  }
              }

              return {
                  label: filter.name,
                  sideIcon: <IconChevronRight className="size-3" />,
                  items: filter.options.map((opt) => ({
                      label: opt.label,
                      active: selectedOptionId === opt.id,
                      onClick: () => setQuickFilterValue(filter.property_name, opt),
                  })),
              }
          })
        : []

    const sectionTitle = (label: string, onClick: () => void): React.ReactNode => (
        <h5 className="mx-2 my-1 flex items-center justify-between">
            {label}
            <LemonButton size="xsmall" icon={<IconGear />} onClick={onClick} noPadding />
        </h5>
    )

    const items: LemonMenuItems = [
        ...(issueFilterItems.length > 0 ? [{ title: 'Issue', items: issueFilterItems }] : []),
        ...(quickFilterItems.length > 0
            ? [
                  {
                      title: quickFilterContext
                          ? sectionTitle('Quick filters', () => {
                                quickFiltersModalLogic({ context: quickFilterContext }).actions.openModal()
                            })
                          : 'Quick filters',
                      items: quickFilterItems,
                  },
              ]
            : []),
        {
            title: sectionTitle('Internal users', () => {
                window.open(urls.settings('project-product-analytics', 'internal-user-filtering'), '_blank')
            }),
            items: [
                {
                    label: 'Filter out internal users',
                    active: checked,
                    onClick: toggle,
                    disabledReason: !hasFilters ? "You haven't set any internal and test filters" : undefined,
                },
            ],
        },
    ]

    return (
        <>
            <LemonMenu items={items} trigger="hover">
                <LemonButton type="tertiary" size="small" icon={<IconBolt />} />
            </LemonMenu>
            {quickFilterContext && <QuickFiltersModal context={quickFilterContext} />}
        </>
    )
}

const AssigneeSubmenu = ({
    assignee,
    onChange,
}: {
    assignee: ErrorTrackingIssueAssignee | null
    onChange: (assignee: ErrorTrackingIssueAssignee | null) => void
}): JSX.Element => {
    const { ensureAssigneeTypesLoaded, setSearch } = useActions(assigneeSelectLogic)

    useEffect(() => {
        ensureAssigneeTypesLoaded()
    }, [ensureAssigneeTypesLoaded])

    return (
        <AssigneeDropdown
            assignee={assignee}
            onChange={(value) => {
                setSearch('')
                onChange(value)
            }}
        />
    )
}
