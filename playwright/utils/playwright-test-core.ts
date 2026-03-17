import fs from 'fs'
import path from 'path'

import { Page, test as base } from '@playwright/test'

import { AppContext } from '~/types'

import { Identifier, Navigation } from './navigation'

export const LOGIN_USERNAME = process.env.LOGIN_USERNAME || 'test@posthog.com'
export const LOGIN_PASSWORD = process.env.LOGIN_PASSWORD || '12345678'

export type WindowWithPostHog = typeof globalThis & {
    POSTHOG_APP_CONTEXT: AppContext
}

declare module '@playwright/test' {
    interface Page {
        setAppContext<K extends keyof AppContext>(key: K, value: AppContext[K]): Promise<void>
        goToMenuItem(name: string): Promise<void>
    }
}

/**
 * Core Playwright test base with page extensions but NO automatic login
 * Use this as the foundation for both legacy tests and new workspace-based tests
 */
export const test = base.extend<{ page: Page }>({
    page: async ({ page }, use) => {
        // Add custom methods to the page object
        page.setAppContext = async function <K extends keyof AppContext>(key: K, value: AppContext[K]): Promise<void> {
            await page.evaluate(
                ([key, value]) => {
                    const appContext = (window as WindowWithPostHog).POSTHOG_APP_CONTEXT
                    // @ts-expect-error - Type safety is handled by the generic constraint
                    appContext[key] = value
                },
                [key, value]
            )
        }
        page.goToMenuItem = async function (name: Identifier): Promise<void> {
            await new Navigation(page).openMenuItem(name)
        }

        // Mock billing API by default to prevent billing warning banners from appearing in snapshots
        await page.route('**/api/billing/', async (route) => {
            const filePath = path.join(__dirname, '../mocks/billing/billing.json')
            const billingContent = fs.readFileSync(filePath, 'utf-8')
            await route.fulfill({
                status: 200,
                body: billingContent,
            })
        })

        // Pass the extended page to the test
        // eslint-disable-next-line react-hooks/rules-of-hooks
        await use(page)
    },
})

export { expect } from '@playwright/test'
