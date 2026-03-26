import type { HogQLParser } from '@posthog/hogql-parser'

import { buildQueryForColumnClick, normalizeIdentifier, parseQueryTablesAndColumns } from './sql-utils'

function makeAst(overrides: Record<string, unknown> = {}): string {
    return JSON.stringify({
        node: 'SelectQuery',
        select: [{ node: 'Field', chain: ['*'] }],
        select_from: {
            node: 'JoinExpr',
            table: { node: 'Field', chain: ['events'] },
            next_join: null,
        },
        limit: { node: 'Constant', value: 100 },
        offset: null,
        ...overrides,
    })
}

function makeParser(returnValue: string): HogQLParser {
    return {
        parseSelect: jest.fn().mockReturnValue(returnValue),
        parseExpr: jest.fn(),
        parseOrderExpr: jest.fn(),
        parseProgram: jest.fn(),
        parseFullTemplateString: jest.fn(),
        parseStringLiteralText: jest.fn(),
    }
}

describe('sql-utils', () => {
    describe('normalizeIdentifier', () => {
        test.each([
            ['plain identifier is lowercased', 'Events', 'events'],
            ['backtick-quoted identifier is stripped and lowercased', '`MyTable`', 'mytable'],
            ['double-quoted identifier is stripped and lowercased', '"MyColumn"', 'mycolumn'],
            ['single-quoted identifier is stripped and lowercased', "'MyField'", 'myfield'],
            ['already lowercase plain identifier is unchanged', 'events', 'events'],
            ['identifier with underscores is lowercased', 'My_Table', 'my_table'],
        ])('%s', (_name, input, expected) => {
            expect(normalizeIdentifier(input)).toEqual(expected)
        })
    })

    describe('buildQueryForColumnClick', () => {
        it('returns fallback query when parser is null', () => {
            const result = buildQueryForColumnClick(null, 'SELECT * FROM events LIMIT 100', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })

        it('returns fallback query when currentQuery is null', () => {
            const parser = makeParser(makeAst())
            const result = buildQueryForColumnClick(parser, null, 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })

        it('replaces star with clicked column when select is star-only', () => {
            const parser = makeParser(makeAst())
            const result = buildQueryForColumnClick(parser, 'SELECT * FROM events LIMIT 100', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })

        it('removes column that is already in the select list (toggle off)', () => {
            const parser = makeParser(
                makeAst({
                    select: [
                        { node: 'Field', chain: ['id'] },
                        { node: 'Field', chain: ['name'] },
                    ],
                })
            )
            const result = buildQueryForColumnClick(parser, 'SELECT id, name FROM events LIMIT 100', 'events', 'id')
            expect(result).toEqual('SELECT name FROM events LIMIT 100')
        })

        it('appends new column to existing columns', () => {
            const parser = makeParser(makeAst({ select: [{ node: 'Field', chain: ['id'] }] }))
            const result = buildQueryForColumnClick(parser, 'SELECT id FROM events LIMIT 100', 'events', 'name')
            expect(result).toEqual('SELECT id, name FROM events LIMIT 100')
        })

        it('falls back to star when removing the only remaining column', () => {
            const parser = makeParser(makeAst({ select: [{ node: 'Field', chain: ['id'] }] }))
            const result = buildQueryForColumnClick(parser, 'SELECT id FROM events LIMIT 100', 'events', 'id')
            expect(result).toEqual('SELECT "*" FROM events LIMIT 100')
        })

        it('returns fallback query when table in query differs from clicked table', () => {
            const parser = makeParser(
                makeAst({
                    select_from: {
                        node: 'JoinExpr',
                        table: { node: 'Field', chain: ['persons'] },
                        next_join: null,
                    },
                })
            )
            const result = buildQueryForColumnClick(parser, 'SELECT * FROM persons LIMIT 100', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })

        it('preserves LIMIT from the existing query', () => {
            const parser = makeParser(makeAst({ limit: { node: 'Constant', value: 50 } }))
            const result = buildQueryForColumnClick(parser, 'SELECT * FROM events LIMIT 50', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 50')
        })

        it('preserves LIMIT and OFFSET from the existing query', () => {
            const parser = makeParser(
                makeAst({
                    limit: { node: 'Constant', value: 100 },
                    offset: { node: 'Constant', value: 20 },
                })
            )
            const result = buildQueryForColumnClick(parser, 'SELECT * FROM events LIMIT 100 OFFSET 20', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100 OFFSET 20')
        })

        it('handles a JOIN query and matches against the first table', () => {
            const parser = makeParser(
                makeAst({
                    select_from: {
                        node: 'JoinExpr',
                        table: { node: 'Field', chain: ['events'] },
                        next_join: {
                            node: 'JoinExpr',
                            table: { node: 'Field', chain: ['persons'] },
                            next_join: null,
                        },
                    },
                })
            )
            const result = buildQueryForColumnClick(
                parser,
                'SELECT * FROM events JOIN persons ON events.id = persons.id LIMIT 100',
                'events',
                'id'
            )
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })

        it('returns fallback query for invalid SQL', () => {
            const parser = makeParser(JSON.stringify({ error: true, node: 'SyntaxError' }))
            const result = buildQueryForColumnClick(parser, 'NOT VALID SQL', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })

        it('uses default LIMIT 100 when query has no LIMIT', () => {
            const parser = makeParser(makeAst({ limit: null }))
            const result = buildQueryForColumnClick(parser, 'SELECT * FROM events', 'events', 'id')
            expect(result).toEqual('SELECT id FROM events LIMIT 100')
        })
    })

    describe('parseQueryTablesAndColumns', () => {
        it('returns empty object for null queryInput', () => {
            const parser = makeParser(makeAst())
            expect(parseQueryTablesAndColumns(parser, null)).toEqual({})
        })

        it('returns empty object for null parser', () => {
            expect(parseQueryTablesAndColumns(null, 'SELECT * FROM events')).toEqual({})
        })

        it('returns star column for SELECT * FROM events', () => {
            const parser = makeParser(makeAst())
            const result = parseQueryTablesAndColumns(parser, 'SELECT * FROM events')
            expect(result).toEqual({ events: { '*': true } })
        })

        it('maps bare columns to their table', () => {
            const parser = makeParser(
                makeAst({
                    select: [
                        { node: 'Field', chain: ['id'] },
                        { node: 'Field', chain: ['name'] },
                    ],
                    select_from: {
                        node: 'JoinExpr',
                        table: { node: 'Field', chain: ['users'] },
                        next_join: null,
                    },
                })
            )
            const result = parseQueryTablesAndColumns(parser, 'SELECT id, name FROM users')
            expect(result).toEqual({ users: { id: true, name: true } })
        })

        it('assigns table-qualified column to the correct table', () => {
            const parser = makeParser(
                makeAst({
                    select: [{ node: 'Field', chain: ['users', 'id'] }],
                    select_from: {
                        node: 'JoinExpr',
                        table: { node: 'Field', chain: ['users'] },
                        next_join: null,
                    },
                })
            )
            const result = parseQueryTablesAndColumns(parser, 'SELECT users.id FROM users')
            expect(result).toEqual({ users: { id: true } })
        })

        it('returns empty object for invalid SQL', () => {
            const parser = makeParser('')
            parser.parseSelect = jest.fn().mockImplementation(() => {
                throw new Error('parse error')
            })
            const result = parseQueryTablesAndColumns(parser, 'NOT VALID SQL')
            expect(result).toEqual({})
        })

        it('handles star with JOIN — both tables get star', () => {
            const parser = makeParser(
                makeAst({
                    select_from: {
                        node: 'JoinExpr',
                        table: { node: 'Field', chain: ['events'] },
                        next_join: {
                            node: 'JoinExpr',
                            table: { node: 'Field', chain: ['persons'] },
                            next_join: null,
                        },
                    },
                })
            )
            const result = parseQueryTablesAndColumns(
                parser,
                'SELECT * FROM events JOIN persons ON events.id = persons.id'
            )
            expect(result).toEqual({
                events: { '*': true },
                persons: { '*': true },
            })
        })

        it('handles mixed star and named columns', () => {
            const parser = makeParser(
                makeAst({
                    select: [
                        { node: 'Field', chain: ['*'] },
                        { node: 'Field', chain: ['id'] },
                    ],
                })
            )
            const result = parseQueryTablesAndColumns(parser, 'SELECT *, id FROM events')
            expect(result).toEqual({ events: { '*': true, id: true } })
        })
    })
})
