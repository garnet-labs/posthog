import '@testing-library/jest-dom'

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { BindLogic, Provider } from 'kea'

import { groupsModel } from '~/models/groupsModel'
import { propertyDefinitionsModel } from '~/models/propertyDefinitionsModel'
import { initKeaTests } from '~/test/init'
import {
    FilterLogicalOperator,
    PropertyDefinitionType,
    PropertyFilterType,
    PropertyOperator,
    UniversalFiltersGroup,
} from '~/types'

import { issueQueryOptionsLogic } from '../IssueQueryOptions/issueQueryOptionsLogic'
import { FilterGroup } from './FilterGroup'
import { issueFiltersLogic } from './issueFiltersLogic'

jest.mock('lib/components/AutoSizer', () => ({
    AutoSizer: ({ renderProp }: { renderProp: (size: { height: number; width: number }) => React.ReactNode }) =>
        renderProp({ height: 400, width: 400 }),
}))

const LOGIC_KEY = 'test-issue-filters'

describe('IssueFilters', () => {
    beforeEach(() => {
        initKeaTests()
        groupsModel.mount()
        propertyDefinitionsModel.mount()
    })

    afterEach(() => {
        cleanup()
    })

    function renderFilterGroup({
        filterGroup,
        showIssueFilters = true,
    }: {
        filterGroup?: UniversalFiltersGroup
        showIssueFilters?: boolean
    } = {}): void {
        const logic = issueFiltersLogic({ logicKey: LOGIC_KEY })
        logic.mount()

        if (filterGroup) {
            logic.actions.setFilterGroup(filterGroup)
        }

        const optionsLogic = issueQueryOptionsLogic({ logicKey: LOGIC_KEY })
        optionsLogic.mount()

        render(
            <Provider>
                <BindLogic logic={issueFiltersLogic} props={{ logicKey: LOGIC_KEY }}>
                    <BindLogic logic={issueQueryOptionsLogic} props={{ logicKey: LOGIC_KEY }}>
                        <FilterGroup logicKey={LOGIC_KEY} showIssueFilters={showIssueFilters} />
                    </BindLogic>
                </BindLogic>
            </Provider>
        )
    }

    it('renders with empty filter group', () => {
        renderFilterGroup()
        expect(screen.getByTestId('taxonomic-filter-searchfield')).toBeInTheDocument()
    })

    it('renders with an ErrorTrackingIssue property filter without crashing', async () => {
        const filterGroup: UniversalFiltersGroup = {
            type: FilterLogicalOperator.And,
            values: [
                {
                    type: FilterLogicalOperator.And,
                    values: [
                        {
                            type: PropertyFilterType.ErrorTrackingIssue,
                            key: 'status',
                            operator: PropertyOperator.Exact,
                            value: ['active'],
                        },
                    ],
                },
            ],
        }

        renderFilterGroup({ filterGroup })

        // The filter chip should render without throwing
        expect(screen.getByTestId('taxonomic-filter-searchfield')).toBeInTheDocument()

        // Flush the setTimeout that checkOrLoadPropertyDefinition schedules
        jest.runAllTimers()

        // Wait for the async flow to complete (loadPropertyDefinitions -> fetchAllPendingDefinitions)
        await waitFor(() => {
            const definition = propertyDefinitionsModel.values.getPropertyDefinition(
                'status',
                PropertyDefinitionType.Resource
            )
            // The property definition should be resolved, not null/missing
            expect(definition).not.toBeNull()
            expect(definition?.name).toBe('status')
        })
    })

    it('renders with an event property filter', () => {
        const filterGroup: UniversalFiltersGroup = {
            type: FilterLogicalOperator.And,
            values: [
                {
                    type: FilterLogicalOperator.And,
                    values: [
                        {
                            type: PropertyFilterType.Event,
                            key: '$browser',
                            operator: PropertyOperator.Exact,
                            value: ['Chrome'],
                        },
                    ],
                },
            ],
        }

        renderFilterGroup({ filterGroup })
        expect(screen.getByTestId('taxonomic-filter-searchfield')).toBeInTheDocument()
    })

    describe('issueFiltersLogic', () => {
        it('initializes with default values', () => {
            const logic = issueFiltersLogic({ logicKey: LOGIC_KEY })
            logic.mount()

            expect(logic.values.dateRange).toEqual({ date_from: '-7d', date_to: null })
            expect(logic.values.filterGroup).toEqual({
                type: FilterLogicalOperator.And,
                values: [{ type: FilterLogicalOperator.And, values: [] }],
            })
            expect(logic.values.filterTestAccounts).toBe(false)
            expect(logic.values.searchQuery).toBe('')
        })

        it('updates filter group', () => {
            const logic = issueFiltersLogic({ logicKey: LOGIC_KEY })
            logic.mount()

            const newFilterGroup: UniversalFiltersGroup = {
                type: FilterLogicalOperator.And,
                values: [
                    {
                        type: FilterLogicalOperator.And,
                        values: [
                            {
                                type: PropertyFilterType.ErrorTrackingIssue,
                                key: 'status',
                                operator: PropertyOperator.Exact,
                                value: ['active'],
                            },
                        ],
                    },
                ],
            }

            logic.actions.setFilterGroup(newFilterGroup)
            expect(logic.values.filterGroup).toEqual(newFilterGroup)
        })

        it('resets to default when empty filter group is set', () => {
            const logic = issueFiltersLogic({ logicKey: LOGIC_KEY })
            logic.mount()

            const emptyGroup = { type: FilterLogicalOperator.And, values: [] } as UniversalFiltersGroup
            logic.actions.setFilterGroup(emptyGroup)

            expect(logic.values.filterGroup).toEqual({
                type: FilterLogicalOperator.And,
                values: [{ type: FilterLogicalOperator.And, values: [] }],
            })
        })
    })
})
