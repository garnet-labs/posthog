import { resetContext } from 'kea'
import { expectLogic, testUtilsPlugin } from 'kea-test-utils'

import { initKeaTests } from '~/test/init'

import { workflowLogic } from './workflowLogic'

describe('workflowLogic schedule state', () => {
    let logic: ReturnType<typeof workflowLogic.build>

    beforeEach(() => {
        initKeaTests()
        resetContext({ plugins: [testUtilsPlugin] })
        logic = workflowLogic({ id: 'new', tabId: 'default' })
        logic.mount()
    })

    afterEach(() => {
        logic.unmount()
    })

    describe('pendingSchedule reducer', () => {
        it('starts as false', () => {
            expectLogic(logic).toMatchValues({ pendingSchedule: false })
        })

        it('setPendingSchedule sets the pending schedule', () => {
            const schedule = { rrule: 'FREQ=WEEKLY', starts_at: '2026-04-01T09:00:00Z', timezone: 'UTC' }
            expectLogic(logic, () => logic.actions.setPendingSchedule(schedule)).toMatchValues({
                pendingSchedule: schedule,
            })
        })

        it('setPendingSchedule with null clears the schedule', () => {
            logic.actions.setPendingSchedule({ rrule: 'FREQ=WEEKLY', starts_at: '2026-04-01T09:00:00Z' })
            expectLogic(logic, () => logic.actions.setPendingSchedule(null)).toMatchValues({
                pendingSchedule: null,
            })
        })

        it('setSchedules resets pendingSchedule to false', () => {
            logic.actions.setPendingSchedule({ rrule: 'FREQ=WEEKLY', starts_at: '2026-04-01T09:00:00Z' })
            expectLogic(logic, () => logic.actions.setSchedules([])).toMatchValues({
                pendingSchedule: false,
            })
        })
    })

    describe('currentSchedule selector', () => {
        it('returns null when no schedules', () => {
            expectLogic(logic).toMatchValues({ currentSchedule: null })
        })

        it('returns the first schedule', () => {
            const schedule = { id: '1', rrule: 'FREQ=WEEKLY', starts_at: '2026-04-01T09:00:00Z', timezone: 'UTC' }
            expectLogic(logic, () => logic.actions.setSchedules([schedule])).toMatchValues({
                currentSchedule: schedule,
            })
        })
    })

    describe('hasUnsavedChanges selector', () => {
        it('is false initially', () => {
            expectLogic(logic).toMatchValues({ hasUnsavedChanges: false })
        })

        it('is true when pendingSchedule is set', () => {
            expectLogic(logic, () =>
                logic.actions.setPendingSchedule({ rrule: 'FREQ=WEEKLY', starts_at: '2026-04-01T09:00:00Z' })
            ).toMatchValues({ hasUnsavedChanges: true })
        })

        it('is true when pendingSchedule is null (delete)', () => {
            expectLogic(logic, () => logic.actions.setPendingSchedule(null)).toMatchValues({
                hasUnsavedChanges: true,
            })
        })

        it('returns to false after setSchedules', () => {
            logic.actions.setPendingSchedule({ rrule: 'FREQ=WEEKLY', starts_at: '2026-04-01T09:00:00Z' })
            expectLogic(logic, () => logic.actions.setSchedules([])).toMatchValues({
                hasUnsavedChanges: false,
            })
        })
    })
})
