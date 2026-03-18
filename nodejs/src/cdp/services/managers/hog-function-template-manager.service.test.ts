import { DBHogFunctionTemplate } from '~/cdp/types'
import { defaultConfig } from '~/config/config'
import { forSnapshot } from '~/tests/helpers/snapshots'
import { resetTestDatabase } from '~/tests/helpers/sql'
import { PostgresRouter } from '~/utils/db/postgres'

import { insertHogFunctionTemplate } from '../../_tests/fixtures'
import { HogFunctionTemplateManagerService } from './hog-function-template-manager.service'

describe('HogFunctionTemplateManager', () => {
    let postgres: PostgresRouter
    let manager: HogFunctionTemplateManagerService
    let hogFunctionsTemplates: DBHogFunctionTemplate[]

    beforeEach(async () => {
        await resetTestDatabase()
        postgres = new PostgresRouter(defaultConfig)
        manager = new HogFunctionTemplateManagerService(postgres)

        hogFunctionsTemplates = []

        hogFunctionsTemplates.push(
            await insertHogFunctionTemplate(postgres, {
                id: 'template-testing-1',
                name: 'Test Hog Function team 1',
                inputs_schema: [
                    {
                        key: 'url',
                        type: 'string',
                        required: true,
                    },
                ],
                code: 'fetch(inputs.url)',
            })
        )
    })

    afterEach(async () => {
        await postgres.end()
    })

    it('returns the hog functions templates', async () => {
        const items = await manager.getHogFunctionTemplate('template-testing-1')

        expect(forSnapshot(items)).toMatchInlineSnapshot(`
            {
              "bytecode": [
                "_H",
                1,
                32,
                "url",
                32,
                "inputs",
                1,
                2,
                2,
                "fetch",
                1,
                35,
              ],
              "free": true,
              "id": "<REPLACED-UUID-0>",
              "inputs_schema": [
                {
                  "key": "url",
                  "required": true,
                  "type": "string",
                },
              ],
              "name": "Test Hog Function team 1",
              "sha": "sha",
              "template_id": "template-testing-1",
              "type": "destination",
            }
        `)
    })
})
