import { DateTime } from 'luxon'

import { CyclotronInvocationQueueParametersSendPushNotificationSchema } from '~/schema/cyclotron'

import { registerAsyncFunction } from '../async-function-registry'
import { pickBy } from 'lodash'

registerAsyncFunction('sendPushNotification', {
    execute: (args, _context, result) => {
        const [url, fetchOptions] = args as [string | undefined, Record<string, any> | undefined]
        const method = fetchOptions?.method || 'POST'
        const headers = fetchOptions?.headers || {
            'Content-Type': 'application/json',
        }
        const body: string | undefined = fetchOptions?.body
            ? typeof fetchOptions.body === 'string'
                ? fetchOptions.body
                : JSON.stringify(fetchOptions.body)
            : fetchOptions?.body
        const timeoutMs = fetchOptions?.timeoutMs ?? undefined
        result.invocation.queueParameters =
            CyclotronInvocationQueueParametersSendPushNotificationSchema.parse({
                type: 'sendPushNotification',
                url,
                method,
                body,
                headers: pickBy(headers, (v) => typeof v == 'string'),
                timeoutMs,
            })
    },

    mock: (args, logs) => {
        logs.push({
            level: 'info',
            timestamp: DateTime.now(),
            message: `Async function 'sendPushNotification' was mocked with arguments:`,
        })
        logs.push({
            level: 'info',
            timestamp: DateTime.now(),
            message: `sendPushNotification('${args[0]}', ${JSON.stringify(args[1], null, 2)})`,
        })

        return {
            status: 200,
            body: {},
        }
    },
})
