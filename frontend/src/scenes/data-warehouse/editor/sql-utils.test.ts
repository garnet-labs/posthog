import { buildQueryForColumnClick } from './sql-utils'

describe('sql-utils', () => {
    it('keeps dotted table names unquoted when building a new column query', () => {
        expect(buildQueryForColumnClick(null, 'demo.orders', 'id')).toEqual('SELECT id FROM demo.orders LIMIT 100')
    })

    it('keeps dotted table names unquoted when toggling columns in an existing query', () => {
        expect(buildQueryForColumnClick('SELECT * FROM demo.orders LIMIT 100', 'demo.orders', 'id')).toEqual(
            'SELECT id FROM demo.orders LIMIT 100'
        )
    })

    it('quotes dotted field paths by segment instead of as a single identifier', () => {
        expect(buildQueryForColumnClick(null, 'demo.orders', 'orders.item count')).toEqual(
            'SELECT orders."item count" FROM demo.orders LIMIT 100'
        )
    })

    it('matches dotted field paths even when an existing query already quotes a segment', () => {
        expect(
            buildQueryForColumnClick(
                'SELECT orders."item count" FROM demo.orders LIMIT 100',
                'demo.orders',
                'orders.item count'
            )
        ).toEqual('SELECT * FROM demo.orders LIMIT 100')
    })
})
