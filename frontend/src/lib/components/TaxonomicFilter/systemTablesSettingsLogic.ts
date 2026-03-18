import { actions, kea, path, reducers } from 'kea'

import type { systemTablesSettingsLogicType } from './systemTablesSettingsLogicType'

export const systemTablesSettingsLogic = kea<systemTablesSettingsLogicType>([
    path(['lib', 'components', 'TaxonomicFilter', 'systemTablesSettingsLogic']),
    actions({
        toggleSystemTablesEnabled: true,
    }),
    reducers({
        systemTablesEnabled: [
            false,
            { persist: true },
            {
                toggleSystemTablesEnabled: (state: boolean) => !state,
            },
        ],
    }),
])
