/**
 * PostHog Design System — Color Tokens (shadcn-aligned)
 *
 * Each value is [light, dark]. Index 0 = light, index 1 = dark.
 * All values traced from vars.scss primitives.
 */

export const colors = {
    background: ['oklch(0.97 0.006 106)', 'hsl(240 8% 8%)'],
    foreground: ['oklch(0.13 0.028 262)', 'oklch(0.967 0.003 265)'],

    card: ['oklch(1 0 0)', 'hsl(235 8% 15%)'],
    'card-foreground': ['oklch(0.13 0.028 262)', 'oklch(0.967 0.003 265)'],

    popover: ['oklch(1 0 0)', 'hsl(235 8% 15%)'],
    'popover-foreground': ['oklch(0.13 0.028 262)', 'oklch(0.967 0.003 265)'],

    primary: ['hsl(19 100% 48%)', 'hsl(43 94% 57%)'],
    'primary-foreground': ['oklch(1 0 0)', 'oklch(0.13 0.028 262)'],

    secondary: ['oklch(0.923 0.003 49)', 'hsl(230 8% 20%)'],
    'secondary-foreground': ['oklch(0.13 0.028 262)', 'oklch(0.967 0.003 265)'],

    muted: ['oklch(0.97 0.006 106)', 'hsl(240 8% 10%)'],
    'muted-foreground': ['oklch(0.446 0.03 257)', 'oklch(0.709 0.01 56)'],

    accent: ['oklch(0.923 0.003 49)', 'hsl(230 8% 20%)'],
    'accent-foreground': ['oklch(0.13 0.028 262)', 'oklch(0.967 0.003 265)'],

    destructive: ['oklch(0.577 0.245 27)', 'oklch(0.704 0.191 22)'],
    'destructive-foreground': ['oklch(1 0 0)', 'oklch(0.13 0.028 262)'],

    success: ['oklch(0.627 0.194 149)', 'oklch(0.792 0.209 152)'],
    'success-foreground': ['oklch(1 0 0)', 'oklch(0.13 0.028 262)'],

    warning: ['oklch(0.554 0.135 66)', 'oklch(0.852 0.199 92)'],
    'warning-foreground': ['oklch(0.13 0.028 262)', 'oklch(0.13 0.028 262)'],

    info: ['oklch(0.546 0.245 263)', 'oklch(0.707 0.165 255)'],
    'info-foreground': ['oklch(1 0 0)', 'oklch(0.13 0.028 262)'],

    border: ['oklch(0.923 0.003 49)', 'hsl(230 8% 20%)'],
    input: ['oklch(0.923 0.003 49)', 'hsl(230 8% 20%)'],
    ring: ['hsl(228 100% 56%)', 'oklch(0.707 0.165 255)'],
} as const

// ── Types ──────────────────────────────────────────────

export type ColorKey = keyof typeof colors
export type ColorTuple = readonly [light: string, dark: string]

// ── Helpers ────────────────────────────────────────────

/** Flat object for one theme */
export function resolveTheme(mode: 'light' | 'dark'): Record<ColorKey, string> {
    const i = mode === 'light' ? 0 : 1
    return Object.fromEntries(Object.entries(colors).map(([k, v]) => [k, v[i]])) as Record<ColorKey, string>
}

/** CSS custom properties for both themes */
export function generateCSSVars(): string {
    const block = (selector: string, i: number): string => {
        const vars = Object.entries(colors)
            .map(([k, v]) => `  --${k}: ${v[i]};`)
            .join('\n')
        return `${selector} {\n${vars}\n}`
    }

    return [block(':root', 0), block('.dark', 1)].join('\n\n')
}

/** Tailwind theme extension using CSS vars */
export function tailwindTheme(): Record<string, string> {
    return Object.fromEntries(Object.keys(colors).map((k) => [k, `var(--${k})`]))
}
