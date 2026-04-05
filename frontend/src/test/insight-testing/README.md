# Insight testing

A test wrapper for rendering insight components (or any component that depends on insight infrastructure) with mocked data and a chart inspection API.

## Quick start

```tsx
import { renderInsightPage, waitForChart, buildTrendsQuery } from './index'

renderInsightPage({
  query: buildTrendsQuery({
    series: [{ kind: NodeKind.EventsNode, event: '$pageview', name: '$pageview' }],
  }),
})

const chart = await waitForChart()
expect(chart.series('$pageview').data).toEqual([45, 82, 134, 210, 95])
```

## `renderInsightPage(props?)`

Renders a full `InsightViz` component with mocked API responses.
Handles all setup automatically — Kea context, common logics, and API mocks.

| Prop            | Type                | Description                                              |
| --------------- | ------------------- | -------------------------------------------------------- |
| `query`         | `TrendsQuery`       | Query to render (defaults to a `$pageview` trends query) |
| `showFilters`   | `boolean`           | Show filter controls (defaults to `true`)                |
| `mocks`         | `SetupMocksOptions` | Override event/property definitions and property values  |
| `mockResponses` | `MockResponse[]`    | Custom query response matchers                           |

## `renderWithInsights(props)`

Renders any component with insight mocks and Kea logics ready.
Use this when testing a component that contains insights internally
(e.g. a page that embeds `InsightViz`) rather than testing `InsightViz` directly.

```tsx
import { renderWithInsights } from './index'

renderWithInsights({
  component: <JourneyBuilder steps={steps} />,
  mockResponses: [{ match: (q) => q.kind === 'TrendsQuery', response: myTrendsData }],
})
```

| Prop            | Type                 | Description                                             |
| --------------- | -------------------- | ------------------------------------------------------- |
| `component`     | `React.ReactElement` | The component to render                                 |
| `mocks`         | `SetupMocksOptions`  | Override event/property definitions and property values |
| `mockResponses` | `MockResponse[]`     | Custom query response matchers                          |

## Chart API

`waitForChart()` waits for a new chart to render since the last call, then returns it.
Back-to-back calls after interactions always return fresh data.

`getChart(index?)` returns the most recently rendered chart (or a specific one by index)
without waiting.

### Chart

| API                    | Description                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| `series(nameOrIndex)`  | Get a series by label or index                                                              |
| `seriesCount`          | Number of datasets                                                                          |
| `seriesNames`          | Array of series labels                                                                      |
| `value(series, point)` | Single data point — series by name/index, point by index or label (`value('Spike', 'Thu')`) |
| `labels`               | X-axis label array                                                                          |
| `label(index)`         | Single label by index                                                                       |
| `type`                 | Chart type (`'line'`, `'bar'`, etc.)                                                        |
| `axes`                 | Axis accessors (`axes.x`, `axes.y`, or any custom axis)                                     |
| `config`               | Raw `ChartConfig` escape hatch                                                              |

### Series

| API               | Description                            |
| ----------------- | -------------------------------------- |
| `label`           | Series name                            |
| `data`            | Number array                           |
| `at(index)`       | Single data point with bounds checking |
| `hidden`          | Whether the series is hidden           |
| `borderColor`     | Line/border color                      |
| `backgroundColor` | Fill color                             |

### Axis

| API                | Description                                 |
| ------------------ | ------------------------------------------- |
| `display`          | Whether the axis is visible                 |
| `type`             | Scale type (`'linear'`, `'category'`, etc.) |
| `stacked`          | Whether stacking is enabled                 |
| `position`         | Axis position (`'left'`, `'bottom'`, etc.)  |
| `tickLabel(value)` | Runs the tick formatter callback            |

## Interactions

Filter controls render by default (`showFilters` defaults to `true`):

```tsx
import { series, breakdown, interval, display, compare } from './index'

await series.select('Napped') // pick an event from the series dropdown
await breakdown.set('hedgehog') // add a breakdown property
await interval.set('week') // change the time interval
await display.set('Bar chart') // change chart display type
await compare.enable() // enable compare to previous period
```

After any interaction, call `await waitForChart()` to get the updated chart.

## Test data

Canned data lives in `test-data.ts`. The mock query handler automatically resolves
queries to the right data based on event name and breakdown property.

| Series                             | Data                                                 |
| ---------------------------------- | ---------------------------------------------------- |
| `$pageview`                        | `[45, 82, 134, 210, 95]` over Mon–Fri                |
| `Napped`                           | `[1, 3, 5, 8, 2]` over Mon–Fri                       |
| `Napped` + breakdown by `hedgehog` | 5 series (Spike, Bramble, Thistle, Conker, Prickles) |

## Hog-charts renderer

The harness captures charts from both the legacy Chart.js renderer and the
new hog-charts renderer (`lib/hog-charts`). `chart.renderer` is either
`'chartjs'` or `'hog-charts'`; assertions against series names, data, labels,
and axes work identically across both.

Because `scenes/trends/Trends.tsx` still routes trends visualizations through
`ActionsLineGraph` (Chart.js), test files that want to exercise the hog-charts
path must add a per-file module mock that swaps `ActionsLineGraph` for
`TrendsLineChartD3`:

```tsx
jest.mock('scenes/trends/viz/ActionsLineGraph', () => {
  const { TrendsLineChartD3 } = require('./TrendsLineChartD3')
  return { ActionsLineGraph: (props) => <TrendsLineChartD3 {...props} /> }
})
```

With the mock in place, `renderInsightPage` routes through the real hog-charts
bridge. The underlying `LineChart` component is itself swapped for a capture
shim via `jest.config.ts` → `hog-charts-mock.tsx`, so no canvas code runs.

### Tooltip testing

Hog-charts tooltips are tested by imperatively driving the hover index:

```tsx
const chart = await waitForChart()
chart.hover(2) // move hover to index 2
const tooltip = await waitForTooltip(chart)
expect(within(tooltip).getByText('134')).toBeInTheDocument()

chart.pin() // pin the tooltip to show the close button
chart.unpin() // unpin
```

`chart.hover`, `chart.pin`, `chart.unpin` are only available on hog-charts
entries and throw on Chart.js entries. The fabricated `TooltipContext` passed
to the bridge render prop is minimal: real position math, `ResizeObserver`,
and `findNearestIndex` are intentionally bypassed — those concerns are
covered by `lib/hog-charts/core/hooks/useChartInteraction.test.ts` and
Playwright end-to-end tests.

**What this harness validates:** the TrendsTooltip bridge mapping, series
formatting, pin/unpin UI, and end-to-end kea data flow into the bridge.

**What it does not validate:** mouse-coordinate-to-index resolution, canvas
drawing, or scroll-to-dismiss pinned tooltip behavior.
