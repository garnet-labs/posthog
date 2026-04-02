import { useValues } from 'kea'

import { FEATURE_FLAGS } from 'lib/constants'
import { featureFlagLogic } from 'lib/logic/featureFlagLogic'
import { LemonField } from 'lib/lemon-ui/LemonField'
import { LemonSelect } from 'lib/lemon-ui/LemonSelect'

export default function SignupCompanySizeSelect({ className }: { className?: string }): JSX.Element | null {
    const { featureFlags } = useValues(featureFlagLogic)

    if (!featureFlags[FEATURE_FLAGS.SIGNUP_COMPANY_SIZE_ENABLED]) {
        return null
    }

    return (
        <LemonField name="company_size" label="What's the size of your company?" className={className}>
            <LemonSelect
                fullWidth
                data-attr="signup-company-size"
                options={[
                    {
                        label: 'Only me',
                        value: '1',
                    },
                    {
                        label: '2-10',
                        value: '2-10',
                    },
                    {
                        label: '11-50',
                        value: '11-50',
                    },
                    {
                        label: '51-200',
                        value: '51-200',
                    },
                    {
                        label: '201-1,000',
                        value: '201-1000',
                    },
                    {
                        label: '1,001-5,000',
                        value: '1001-5000',
                    },
                    {
                        label: '5,001+',
                        value: '5001+',
                    },
                ]}
            />
        </LemonField>
    )
}
