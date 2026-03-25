import { SandboxFile } from '../types'

export const MOCK_SANDBOX_FILES: SandboxFile[] = [
    {
        path: '/research/mobile-retention-drop.md',
        filename: 'mobile-retention-drop.md',
        size: 1240,
        modified_at: '2026-03-25T10:30:00Z',
    },
    {
        path: '/research/funnel-conversion-analysis.md',
        filename: 'funnel-conversion-analysis.md',
        size: 890,
        modified_at: '2026-03-25T10:01:30Z',
    },
    {
        path: '/research/weekly-insights-summary.md',
        filename: 'weekly-insights-summary.md',
        size: 720,
        modified_at: '2026-03-24T08:00:00Z',
    },
]

export const MOCK_FILE_CONTENTS: Record<string, string> = {
    '/research/mobile-retention-drop.md': `# Mobile retention drop investigation

## Summary

7-day retention for mobile users dropped from 32% to 19% in the week of March 17-23, 2026.

## Root cause analysis

### Timeline
- **March 16**: Mobile SDK v2.4.1 released
- **March 17**: Retention begins declining
- **March 19**: First user reports of "blank screen after onboarding"

### Key findings

1. **SDK update correlation**: The drop coincides exactly with the v2.4.1 SDK release
2. **Affected flow**: The onboarding completion event fires, but the subsequent \`app_home_viewed\` event is missing for 61% of mobile users
3. **Platform breakdown**: iOS affected (23% → 11% retention), Android less impacted (38% → 29%)

## Recommendations

- Roll back mobile SDK to v2.4.0 or hotfix the onboarding navigation bug
- Add monitoring alert for onboarding completion → home view drop-off rate
- Consider a re-engagement campaign for affected users`,

    '/research/funnel-conversion-analysis.md': `# Funnel conversion rate analysis - March 2026

## Overview

Analysis of the primary signup-to-activation funnel for the 30-day period ending March 25, 2026.

## Metrics

| Step | Conversion | Change vs. prior period |
|------|-----------|------------------------|
| Sign up → Onboarding | 78% | +2% |
| Onboarding → First event | 54% | -1% |
| First event → Retained (7d) | 42% | +3% |

## Observations

- Overall funnel health is improving, driven by better sign-up-to-onboarding conversion
- The onboarding → first event step remains the weakest link
- Users who complete onboarding within 5 minutes have 2.3x higher retention`,

    '/research/weekly-insights-summary.md': `# Weekly insights summary

## Week of March 17-23, 2026

### Highlights

- **Active users**: 12,450 (+5% WoW)
- **New signups**: 1,230 (+8% WoW)
- **Feature adoption**: Dashboard sharing feature used by 34% of teams (up from 28%)

### Anomalies detected

1. Mobile retention drop (see dedicated research document)
2. Unusual spike in API errors on March 20 (resolved — was a dependency timeout)
3. Feature flag evaluation latency increased 15ms on average

### Recommendations

- Prioritize mobile SDK fix
- Review API dependency timeout settings
- Investigate feature flag evaluation performance`,
}
