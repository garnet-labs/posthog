export interface TooltipRow {
    element: HTMLElement
    expectValue(value: string): void
}

export interface TooltipAccessor {
    element: HTMLElement
    row(label: string): TooltipRow
    expectNoRow(label: string): void
}

function availableRowLabels(tooltip: HTMLElement): string[] {
    return Array.from(tooltip.querySelectorAll('tr'))
        .map((r) => r.textContent?.trim())
        .filter((t): t is string => !!t)
}

export function createTooltipAccessor(element: HTMLElement): TooltipAccessor {
    return {
        element,

        row(label: string): TooltipRow {
            const rows = element.querySelectorAll('tr')
            for (let i = 0; i < rows.length; i++) {
                const row = rows[i]
                if (row.textContent?.includes(label)) {
                    return {
                        element: row as HTMLElement,
                        expectValue(value: string) {
                            const cell = row.querySelector('.datum-counts-column')
                            if (!cell) {
                                throw new Error(`Row "${label}" has no counts cell`)
                            }
                            expect(cell.textContent).toContain(value)
                        },
                    }
                }
            }
            throw new Error(
                `No tooltip row containing "${label}". Rows: ${availableRowLabels(element)
                    .map((r) => `"${r}"`)
                    .join(', ')}`
            )
        },

        expectNoRow(label: string) {
            const rows = element.querySelectorAll('tr')
            for (let i = 0; i < rows.length; i++) {
                expect(rows[i].textContent).not.toContain(label)
            }
        },
    }
}
