"""Fast speculative acknowledgment for voice mode — contextual filler before the main agent responds."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from posthog.models import Team, User

from ee.hogai.llm import MaxChatAnthropic

SPECULATIVE_ACK_SYSTEM = (
    "You are a friendly voice assistant. The user just said something and you need to "
    "reply with a short, conversational acknowledgment before you do the real work. "
    "Start with a brief natural greeting or reaction — like how a colleague would respond "
    "in conversation — then say what you're about to do. Keep it under 20 words total. "
    "Don't answer the question itself. Vary your openings. "
    "Examples: "
    "'Sure thing! Let me pull up your retention data.' / "
    "'Oh yeah, let me check those conversion rates for you.' / "
    "'Got it — I'll take a look at the signup flow.' / "
    "'Absolutely, let me dig into that.' / "
    "'Okay! Give me a sec to look at those numbers.' "
    "No markdown, no emojis. Speak naturally like a real person."
)

FALLBACK = "Sure! Let me look into that for you."


def generate_speculative_ack(*, user: User, team: Team, prompt: str) -> str:
    """Call Haiku with no tools to get a fast contextual acknowledgment (~300-600ms)."""
    prompt = prompt.strip()[:500]
    if not prompt:
        return FALLBACK

    llm = MaxChatAnthropic(
        user=user,
        team=team,
        model="claude-haiku-4-5",
        temperature=0.5,
        max_tokens=60,
        billable=False,
        inject_context=False,
        streaming=False,
    )
    messages = [
        SystemMessage(content=SPECULATIVE_ACK_SYSTEM),
        HumanMessage(content=prompt),
    ]
    try:
        result = llm.invoke(messages)
        content = result.content
        if isinstance(content, list):
            text = "".join(str(block) for block in content)
        else:
            text = str(content or "")
        text = re.sub(r"\s+", " ", text.strip())
        if not text or len(text) > 200:
            return FALLBACK
        return text
    except Exception:
        return FALLBACK
