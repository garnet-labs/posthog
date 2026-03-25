import { LogEntry } from 'products/tasks/frontend/lib/parse-logs'

export const MOCK_CHAT_LOG_ENTRIES: LogEntry[] = [
    {
        id: 'log-0',
        type: 'agent',
        timestamp: '2026-03-25T10:00:00Z',
        message:
            "Hello! I'm Hogbot, your AI research assistant. I can help you investigate your product data, run analyses, and proactively surface insights. What would you like me to look into?",
    },
    {
        id: 'log-1',
        type: 'user',
        timestamp: '2026-03-25T10:01:00Z',
        message: 'Can you analyze our funnel conversion rates for the last 30 days?',
    },
    {
        id: 'log-2',
        type: 'tool',
        timestamp: '2026-03-25T10:01:05Z',
        toolName: 'posthog_query_funnel',
        toolCallId: 'tc-1',
        toolStatus: 'completed',
        toolArgs: {
            date_from: '-30d',
            events: ['$pageview', '$signup', '$onboarding_complete', '$first_event'],
        },
        toolResult: {
            conversion_rate: 0.42,
            steps: [
                { name: 'Sign up → Onboarding', rate: 0.78 },
                { name: 'Onboarding → First event', rate: 0.54 },
            ],
        },
    },
    {
        id: 'log-3',
        type: 'console',
        timestamp: '2026-03-25T10:01:10Z',
        level: 'info',
        message: 'Funnel query completed. Analyzing step-by-step conversion rates.',
    },
    {
        id: 'log-4',
        type: 'tool',
        timestamp: '2026-03-25T10:01:12Z',
        toolName: 'posthog_query_trends',
        toolCallId: 'tc-2',
        toolStatus: 'completed',
        toolArgs: {
            date_from: '-60d',
            compare: true,
            events: ['$signup'],
        },
        toolResult: { current_period: 1230, previous_period: 1140, change: '+7.9%' },
    },
    {
        id: 'log-5',
        type: 'agent',
        timestamp: '2026-03-25T10:01:30Z',
        message:
            "I've analyzed your funnel conversion rates.\n\nYour signup-to-activation funnel has a **42% conversion rate** over the last 30 days, which is up 3% from the previous period.\n\nKey findings:\n- Step 1 → Step 2 (Sign up → Onboarding): 78% conversion\n- Step 2 → Step 3 (Onboarding → First event): 54% conversion\n- The biggest drop-off is between onboarding completion and sending the first event",
    },
    {
        id: 'log-6',
        type: 'tool',
        timestamp: '2026-03-25T10:04:50Z',
        toolName: 'posthog_query_retention',
        toolCallId: 'tc-3',
        toolStatus: 'completed',
        toolArgs: {
            date_from: '-14d',
            breakdown_by: 'platform',
        },
        toolResult: {
            mobile: { week1: 0.32, week2: 0.19, change: '-40.6%' },
            desktop: { week1: 0.45, week2: 0.44, change: '-2.2%' },
        },
    },
    {
        id: 'log-7',
        type: 'console',
        timestamp: '2026-03-25T10:04:55Z',
        level: 'warn',
        message: 'Anomaly detected: mobile retention dropped 40.6% week-over-week. Flagging for proactive notification.',
    },
    {
        id: 'log-8',
        type: 'agent',
        timestamp: '2026-03-25T10:05:00Z',
        message:
            "I noticed a significant drop in retention for users who signed up via the mobile app last week. The 7-day retention fell from 32% to 19%. You might want to investigate the mobile onboarding flow — I've started a research document on this.",
    },
    {
        id: 'log-9',
        type: 'user',
        timestamp: '2026-03-25T10:06:00Z',
        message: 'Good catch. Can you dig deeper into what changed for mobile users?',
    },
    {
        id: 'log-10',
        type: 'tool',
        timestamp: '2026-03-25T10:06:05Z',
        toolName: 'posthog_query_sessions',
        toolCallId: 'tc-4',
        toolStatus: 'running',
        toolArgs: {
            date_from: '-14d',
            filters: { platform: 'mobile' },
            breakdown_by: 'session_duration',
        },
    },
    {
        id: 'log-11',
        type: 'console',
        timestamp: '2026-03-25T10:06:08Z',
        level: 'info',
        message: 'Querying mobile session data to compare pre/post retention drop periods.',
    },
    {
        id: 'log-12',
        type: 'agent',
        timestamp: '2026-03-25T10:06:15Z',
        message:
            "On it. I'm comparing mobile user sessions before and after the drop. I'll update the research document with my findings and let you know when it's ready.",
    },
]
