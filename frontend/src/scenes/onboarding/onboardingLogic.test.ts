import { initKeaTests } from '~/test/init'

import { onboardingLogic } from './onboardingLogic'

describe('onboardingLogic', () => {
    describe('smart prefetching', () => {
        it('does not crash when step changes and next step is unknown', async () => {
            initKeaTests()

            const logic = onboardingLogic()
            logic.mount()

            expect(() => {
                logic.actions.setStepKey('NON_EXISTENT_STEP_KEY' as any)
            }).not.toThrow()

            logic.unmount()
        })
    })
})

