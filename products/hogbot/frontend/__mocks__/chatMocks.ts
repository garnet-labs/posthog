import { HogbotMessage, MessageRole, MessageType } from '../types'

export const MOCK_CHAT_MESSAGES: HogbotMessage[] = [
    {
        id: 'msg-1',
        role: MessageRole.AGENT,
        type: MessageType.TEXT,
        content: "Hello! I'm Hogbot, your AI research assistant. I can help you investigate your product data, run analyses, and proactively surface insights. What would you like me to look into?",
        created_at: '2026-03-25T10:00:00Z',
    },
    {
        id: 'msg-2',
        role: MessageRole.USER,
        type: MessageType.TEXT,
        content: 'Can you analyze our funnel conversion rates for the last 30 days?',
        created_at: '2026-03-25T10:01:00Z',
    },
    {
        id: 'msg-3',
        role: MessageRole.AGENT,
        type: MessageType.TEXT,
        content: "I'll look into your funnel conversion rates now.\n\nBased on the data, your signup-to-activation funnel has a **42% conversion rate** over the last 30 days, which is up 3% from the previous period.\n\nKey findings:\n- Step 1 → Step 2 (Sign up → Onboarding): 78% conversion\n- Step 2 → Step 3 (Onboarding → First event): 54% conversion\n- The biggest drop-off is between onboarding completion and sending the first event",
        created_at: '2026-03-25T10:01:30Z',
    },
    {
        id: 'msg-4',
        role: MessageRole.AGENT,
        type: MessageType.PROACTIVE,
        content: "I noticed a significant drop in retention for users who signed up via the mobile app last week. The 7-day retention fell from 32% to 19%. You might want to investigate the mobile onboarding flow — I've started a research document on this.",
        created_at: '2026-03-25T10:05:00Z',
    },
    {
        id: 'msg-5',
        role: MessageRole.USER,
        type: MessageType.TEXT,
        content: 'Good catch. Can you dig deeper into what changed for mobile users?',
        created_at: '2026-03-25T10:06:00Z',
    },
    {
        id: 'msg-6',
        role: MessageRole.AGENT,
        type: MessageType.TEXT,
        content: "On it. I'm comparing mobile user sessions before and after the drop. I'll update the research document with my findings and let you know when it's ready.",
        created_at: '2026-03-25T10:06:15Z',
    },
]
