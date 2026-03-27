import { InsightEditorFilter } from '~/types'

export type ConditionalEditorFilter = InsightEditorFilter & { show?: boolean }

export function filterFalsy(a: (InsightEditorFilter | false | null | undefined)[]): InsightEditorFilter[] {
    return a.filter((e): e is InsightEditorFilter => !!e)
}

export function visibleFilters(filters: ConditionalEditorFilter[]): InsightEditorFilter[] {
    return filters.filter((f) => f.show !== false).map(({ show: _, ...rest }) => rest)
}
