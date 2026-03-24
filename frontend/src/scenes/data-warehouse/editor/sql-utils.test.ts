import { buildQueryForColumnClick } from './sql-utils'

describe('sql-utils', () => {
    it('keeps dotted table names quoted when building a new column query', () => {
        expect(buildQueryForColumnClick(null, 'demo.orders', 'id')).toEqual('SELECT id FROM "demo.orders" LIMIT 100')
    })

    it('keeps dotted table names quoted when toggling columns in an existing query', () => {
        expect(buildQueryForColumnClick('SELECT * FROM "demo.orders" LIMIT 100', 'demo.orders', 'id')).toEqual(
            'SELECT id FROM "demo.orders" LIMIT 100'
        )
    })
})
