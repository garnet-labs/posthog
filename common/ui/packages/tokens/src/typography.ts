/**
 * PostHog Design System — Typography Tokens
 */

import { fontFamilyValue } from './css'

export const fontSize = {
    xss: ['10px', { lineHeight: '12px' }],
    xs: ['12px', { lineHeight: '16px' }],
    sm: ['14px', { lineHeight: '14px' }],
    base: ['16px', { lineHeight: '24px' }],
    lg: ['18px', { lineHeight: '28px' }],
    xl: ['20px', { lineHeight: '28px' }],
    '2xl': ['24px', { lineHeight: '32px' }],
} as const

export const fontFamily = {
    sans: ['-apple-system', 'BlinkMacSystemFont', 'Inter', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'sans-serif'],
    mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
} as const

export type FontSize = typeof fontSize
export type FontFamily = typeof fontFamily

/** Generate Tailwind v4 @theme font-size vars (--text-* + --text-*--line-height) */
export function generateFontSizeCSS(): string {
    return Object.entries(fontSize)
        .map(([k, [size, { lineHeight }]]) => `  --text-${k}: ${size};\n  --text-${k}--line-height: ${lineHeight};`)
        .join('\n')
}

/** Generate Tailwind v4 @theme font-family vars (--font-*) */
export function generateFontFamilyCSS(): string {
    return Object.entries(fontFamily)
        .map(([k, fonts]) => `  --font-${k}: ${fontFamilyValue(fonts)};`)
        .join('\n')
}
