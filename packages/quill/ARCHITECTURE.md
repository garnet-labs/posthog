# UI Architecture

> Architecture reference for re-implementing the UI design system inside `posthog/posthog`.

---

## 1. Monorepo overview

```text
ui/
├── packages/
│   ├── tokens/          @posthog/quill-tokens       — Source-of-truth design tokens (JS) + CSS generation
│   ├── primitives/      @posthog/quill-primitives    — Base UI components (React + Tailwind v4 + Base-UI)
│   ├── components/      @posthog/quill-components    — Composed primitives with easy-to-use APIs (what apps import)
│   ├── blocks/          @posthog/quill-blocks        — Product-level patterns (FeatureFlag, Experiment, etc.)
│   └── mcp-renderer/    @posthog/quill-mcp-renderer  — MCP iframe HTML renderer
├── apps/
│   ├── web/             — Vite dev/showcase app
│   └── storybook/       — Storybook documentation
├── pnpm-workspace.yaml  — packages: ['packages/*', 'apps/*']
└── package.json         — Root scripts (pnpm -r build, etc.)
```

---

## 2. Dependency graph

```text
@posthog/quill-tokens           (no dependencies — pure JS/TS)
        │
        ├──▶ @posthog/quill-primitives
        │       ├── @base-ui/react       (unstyled headless components)
        │       ├── class-variance-authority (CVA — variant class maps)
        │       ├── clsx + tailwind-merge (class merging)
        │       ├── lucide-react         (icons)
        │       └── vaul                 (drawer primitive)
        │
        ├──▶ @posthog/quill-components      (imports primitives + tokens)
        │       └── @posthog/quill-primitives
        │
        ├──▶ @posthog/quill-blocks          (imports components + primitives + tokens)
        │       └── @posthog/quill-components
        │
        └──▶ @posthog/quill-mcp-renderer

Apps (web, storybook) depend on components + tokens at workspace:*
```

---

## 3. Token system — how CSS is generated from JS

### 3.1 Source-of-truth files (all in `packages/tokens/src/`)

| File               | Exports                               | What it defines                                                   |
| ------------------ | ------------------------------------- | ----------------------------------------------------------------- |
| `colors.ts`        | `semanticColors`, `resolveTheme()`    | 20+ semantic color pairs as `[light, dark]` tuples (OKLch/HSL)    |
| `spacing.ts`       | `spacing`                             | Spacing scale: `{ 0: '0px', 1: '4px', 2: '8px', ... 16: '64px'}`  |
| `typography.ts`    | `fontSize`, `fontFamily`              | 6 font sizes with line-heights, 2 font families (sans, mono)      |
| `shadow.ts`        | `shadow`                              | 3 shadow levels: sm, md, lg                                       |
| `border-radius.ts` | `borderRadius`                        | Static radius values (sm through full)                            |
| `css.ts`           | `cssVars()`, `cssVarsFlat()`, helpers | Utility functions that convert JS objects → CSS custom properties |

Each token file also exports a `generate*CSS()` function that produces the CSS lines for its category.

### 3.2 Color token structure

```ts
// packages/tokens/src/colors.ts
export const semanticColors = {
  background: ['oklch(0.97 0.006 106)', 'hsl(240 8% 8%)'], // [light, dark]
  foreground: ['oklch(0.13 0.028 262)', 'oklch(0.967 0.003 265)'],
  primary: ['hsl(19 100% 48%)', 'hsl(43 94% 57%)'],
  'primary-foreground': ['oklch(1 0 0)', 'oklch(0.13 0.028 262)'],
  destructive: ['oklch(0.577 0.245 27)', 'oklch(0.704 0.191 22)'],
  success: ['oklch(0.627 0.194 149)', 'oklch(0.792 0.209 152)'],
  warning: ['oklch(0.554 0.135 66)', 'oklch(0.852 0.199 92)'],
  info: ['oklch(0.546 0.245 263)', 'oklch(0.707 0.165 255)'],
  border: ['oklch(0.923 0.003 49)', 'hsl(230 8% 20%)'],
  ring: ['hsl(228 100% 56%)', 'oklch(0.707 0.165 255)'],
  // ... ~20 total pairs
} as const
```

### 3.3 Generation script

**`packages/tokens/scripts/generate-css.ts`** runs via `pnpm --filter @posthog/quill-tokens build` (after vite build).

It calls two generator functions:

1. **`generateColorSystemCSS()`** → produces `color-system.css`
2. **`generateStylesCSS(config)`** → produces `styles.css`

#### `generateColorSystemCSS()` output

Sets CSS custom properties on `:root` (light) and `.dark` (dark override):

```css
:root {
  color-scheme: light;
}
.dark {
  color-scheme: dark;
}

:root {
  --radius: 0.625rem;
  --background: oklch(0.97 0.006 106);
  --foreground: oklch(0.13 0.028 262);
  --primary: hsl(19 100% 48%);
  /* ... all semantic colors ... */
}

.dark {
  --radius: 0.625rem;
  --background: hsl(240 8% 8%);
  --foreground: oklch(0.967 0.003 265);
  --primary: hsl(43 94% 57%);
  /* ... dark overrides ... */
}
```

#### `generateStylesCSS(config)` output

Produces a Tailwind v4 stylesheet. Has two modes controlled by config:

**Library mode** (`importColorSystem: false, includeBaseLayer: false`):

```css
@import 'tailwindcss';

@custom-variant dark (&:is(.dark, .dark *));

@theme inline {
  --animate-skeleton: skeleton 2s -1s infinite linear;

  /* Colors — maps Tailwind's --color-* to our CSS vars */
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  /* ... all color mappings ... */

  /* Spacing */
  --spacing-0: 0px;
  --spacing-1: 4px;
  /* ... */

  /* Font sizes, families, shadows, radius ... */
}
```

**App mode** (`importColorSystem: true, includeBaseLayer: true`):

```css
@import 'tailwindcss';
@import './color-system.css'; /* ← adds actual color values */

@source "../../../packages/primitives/src/**/*.{ts,tsx}"; /* ← scans component classes */

@custom-variant dark (&:is(.dark, .dark *));

@theme inline {
  /* same as library mode */
}

@layer base {
  /* ← adds base resets */
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

### 3.4 Distribution targets

The script writes files to multiple locations:

| Target                     | Gets `color-system.css`? | Gets `styles.css`? | Mode    |
| -------------------------- | ------------------------ | ------------------ | ------- |
| `tokens/dist/`             | Yes                      | No                 | —       |
| `packages/primitives/src/` | No                       | Yes                | Library |
| `packages/components/src/` | No                       | Yes                | Library |
| `packages/blocks/src/`     | No                       | Yes                | Library |
| `apps/web/src/`            | Yes                      | Yes                | App     |
| `apps/storybook/src/`      | Yes                      | Yes                | App     |

**Key insight:** Libraries never ship color values. They only ship the `--color-*: var(--*)` mappings so Tailwind can generate the right utility classes. The consuming app provides the actual color values via `color-system.css`.

---

## 4. Package exports (npm entry points)

### @posthog/quill-tokens

```json
{
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" },
    "./color-system.css": "./dist/color-system.css"
  }
}
```

**JS exports:** `semanticColors`, `resolveTheme()`, `generateColorSystemCSS()`, `generateStylesCSS()`, `spacing`, `fontSize`, `fontFamily`, `borderRadius`, `shadow`, CSS utility functions.

### @posthog/quill-primitives

```json
{
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" },
    "./styles.css": "./dist/styles.css"
  }
}
```

**JS exports:** 40+ React components (Button, Dialog, Sheet, Card, Menu, Select, etc.) plus `useMediaQuery` hook.

### @posthog/quill-components

```json
{
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" },
    "./styles.css": "./dist/styles.css"
  }
}
```

**JS exports:** Re-exports all primitives, plus composed components with easy-to-use APIs. This is the primary import for apps — consumers import from `@posthog/quill-components` rather than reaching into primitives directly.

### @posthog/quill-blocks

```json
{
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" }
  }
}
```

### @posthog/quill-mcp-renderer

```json
{
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" }
  }
}
```

---

## 5. How primitives use tokens

Components use **Tailwind v4 utility classes** that reference the semantic token CSS variables. They never import CSS values directly.

Example from `button.tsx`:

```tsx
import { cva } from 'class-variance-authority'
import { cn } from '~/lib/utils'

const buttonVariants = cva(
  '... rounded-sm border font-medium text-base ... focus-visible:ring-2 focus-visible:ring-ring ...',
  {
    variants: {
      variant: {
        default: 'border-primary bg-primary text-primary-foreground shadow-primary/24 ...',
        destructive: 'border-destructive bg-destructive text-white ...',
        outline: 'border-input bg-popover text-foreground ...',
        ghost: 'border-transparent text-foreground data-pressed:bg-accent ...',
        // ...
      },
      size: {
        default: 'h-9 px-[calc(--spacing(3)-1px)] sm:h-8',
        sm: 'h-8 gap-1.5 px-[calc(--spacing(2.5)-1px)] sm:h-7',
        // ...
      },
    },
  }
)
```

The classes like `bg-primary`, `text-foreground`, `border-input` work because:

1. `styles.css` maps `--color-primary: var(--primary)` in the `@theme` block
2. Tailwind v4 resolves `bg-primary` → `background-color: var(--color-primary)` → `var(--primary)`
3. The actual color value comes from `color-system.css` (provided by the app)

### Component primitives

Built on **@base-ui/react** (unstyled headless components from the Base-UI library). The pattern is:

- Base-UI provides behavior, accessibility, and state management
- CVA defines the Tailwind class variants
- `cn()` (clsx + tailwind-merge) combines classes

---

## 6. How consuming apps wire everything together

### Internal app (e.g., apps/web)

```tsx
// main.tsx
import './styles.css' // Generated file — imports tailwindcss + color-system.css + @theme + @layer base

// App.tsx
import { Button, Dialog } from '@posthog/quill-components'
```

The app's `styles.css` (generated) includes:

- `@import "tailwindcss"` — Tailwind v4 engine
- `@import "./color-system.css"` — actual color values for light/dark
- `@source` directives — tells Tailwind to scan primitives source for used classes
- `@theme inline` — token-to-CSS-variable mappings
- `@layer base` — global resets

### External app (via npm)

An external consumer would:

```tsx
// 1. Import the color system (provides CSS variable values)
import '@posthog/quill-tokens/color-system.css'

// 2. Import component styles (provides Tailwind utility classes used by components)
import '@posthog/quill-components/styles.css'

// 3. Use components
import { Button } from '@posthog/quill-components'
```

The external app also needs Tailwind v4 configured, and must add a `.dark` class to the root element for dark mode (the `@custom-variant dark` directive maps dark variants to `.dark` ancestry).

### For posthog/posthog specifically

Since PostHog already has its own Tailwind setup, integration would involve:

1. Import `@posthog/quill-tokens/color-system.css` to get semantic CSS variables
2. Either import `@posthog/quill-components/styles.css` or regenerate equivalent styles using `generateStylesCSS()` with custom `@source` paths
3. Ensure `.dark` class toggling on a parent element
4. Import and use components from `@posthog/quill-components`

---

## 7. Build pipeline

```text
pnpm build (root)
  └── pnpm -r build (runs in dependency order)

      1. @posthog/quill-tokens
         ├── vite build        → dist/index.js, dist/index.cjs, dist/index.d.ts
         └── tsx generate-css  → dist/color-system.css
                                  + writes styles.css & color-system.css to all targets

      2. @posthog/quill-primitives
         └── vite build        → dist/index.js, dist/index.cjs, dist/index.d.ts, dist/styles.css
             (Tailwind v4 plugin processes src/styles.css during build)

      3. @posthog/quill-components
         └── vite build        → dist/index.js, dist/index.cjs, dist/index.d.ts, dist/styles.css
             (re-exports primitives + adds composed components)

      4. @posthog/quill-blocks
         └── vite build        → dist/index.js, dist/index.cjs, dist/index.d.ts

      5. @posthog/quill-mcp-renderer
         └── vite build        → dist/index.js, dist/index.cjs, dist/index.d.ts
```

### Vite config (primitives example)

```ts
export default defineConfig({
  plugins: [react(), tailwindcss(), dts({ rollupTypes: true })],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      formats: ['es', 'cjs'],
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime', '@posthog/quill-tokens'],
    },
    cssCodeSplit: false, // Bundle all CSS into one file
  },
})
```

Key: `@posthog/quill-tokens` is externalized — primitives reference token CSS vars at runtime, not at build time.

---

## 8. Dark mode mechanism

- **Class-based:** `.dark` class on an ancestor element
- **Tailwind v4 custom variant:** `@custom-variant dark (&:is(.dark, .dark *));`
- **Color-scheme:** `:root { color-scheme: light; }` / `.dark { color-scheme: dark; }`
- **Components use:** `dark:bg-*` variant classes that activate under `.dark` ancestry
- **App responsibility:** Toggle `.dark` class on `<html>` or a wrapper element

---

## 9. Key patterns to preserve when re-implementing

1. **Tokens are JS-first** — colors, spacing, typography defined as typed JS objects, CSS is derived
2. **Library vs App CSS split** — libraries ship only `@theme` mappings (no color values), apps provide the actual values
3. **`@source` directive** — Tailwind v4 needs to scan component source files to know which utility classes to generate
4. **CVA for variants** — all component variants defined via `class-variance-authority`
5. **Base-UI for behavior** — components use `@base-ui/react` for accessibility and state, not custom implementations
6. **`cn()` utility** — `clsx` + `tailwind-merge` for class composition without conflicts
7. **CSS variables as the contract** — `--primary`, `--background`, etc. are the interface between tokens and components
