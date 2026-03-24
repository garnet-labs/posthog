import { getPreviewQueryUrl } from './SyncProgressStep'

describe('SyncProgressStep', () => {
    it('includes the direct connection id in SQL editor preview URLs', () => {
        expect(getPreviewQueryUrl('orders', 'direct', 'source-123')).toContain('#c=source-123')
    })

    it('quotes dotted table names as a single HogQL identifier', () => {
        const previewUrl = new URL(getPreviewQueryUrl('demo.orders', 'direct', 'source-123'), 'https://app.posthog.com')

        expect(previewUrl.searchParams.get('open_query')).toEqual('SELECT * FROM demo.orders LIMIT 100')
    })

    it('does not include a connection id for warehouse preview URLs', () => {
        expect(getPreviewQueryUrl('orders', 'warehouse', 'source-123')).not.toContain('#c=')
    })
})
