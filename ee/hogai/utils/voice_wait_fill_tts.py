"""LLM-generated spoken lines for voice-mode wait-fill clips (interstitial tweets while tools run)."""

from __future__ import annotations

import re
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from posthog.models import Team, User

from ee.hogai.llm import MaxChatOpenAI

MAX_TWEETS = 5
MAX_LINE_CHARS = 900

WAIT_FILL_SYSTEM = """You write short spoken lines for voice TTS while the user waits for the AI to finish working.
Respond with JSON only. No markdown fences, no commentary outside JSON.
The JSON object must be exactly: {"lines": ["...", "..."]}
The "lines" array must have exactly the same length as the input "tweets" array (same order).
Each string in "lines" is ONE full spoken line for text-to-speech. It MUST include the corresponding tweet text verbatim as a substring — copy it character-for-character from the input, do not paraphrase or edit the tweet.
Wrap each tweet with a warm, casual transition that makes it feel like you're sharing something fun while the user waits. Think of the vibe: "while we wait, let me share this with you" or "this'll take a sec — in the meantime..." or "oh, while that's running, you'll love this one...". Vary the transitions so they don't repeat. Keep them short and natural — like a friend sharing a meme while something loads. No sign-offs like "hang tight" or "back soon" at the end.
No markdown, no emojis, no bullet points. English only."""


_FALLBACK_FIRST = [
    "While we wait, let me share this with you.",
    "This'll take a sec — in the meantime,",
    "Oh, while that's running —",
]

_FALLBACK_MIDDLE = [
    "Here's another one while we wait.",
    "Oh and also,",
]

_FALLBACK_LAST = [
    "One more while we're at it.",
    "And while we're still waiting,",
]


def _fallback_lines(tweets: list[str]) -> list[str]:
    """Deterministic copy when the model fails validation."""
    total = len(tweets)
    if total == 0:
        return []
    if total == 1:
        return [f"{_FALLBACK_FIRST[0]} {tweets[0]}"]
    out: list[str] = []
    for i, t in enumerate(tweets):
        if i == 0:
            out.append(f"{_FALLBACK_FIRST[i % len(_FALLBACK_FIRST)]} {t}")
        elif i == total - 1:
            out.append(f"{_FALLBACK_LAST[i % len(_FALLBACK_LAST)]} {t}")
        else:
            out.append(f"{_FALLBACK_MIDDLE[i % len(_FALLBACK_MIDDLE)]} {t}")
    return out


def _sanitize_line(s: str) -> str:
    x = re.sub(r"\s+", " ", (s or "").strip())
    if len(x) > MAX_LINE_CHARS:
        x = x[: MAX_LINE_CHARS - 1].rsplit(" ", 1)[0] + "…"
    return x


def _validate_lines(tweets: list[str], lines: list[Any]) -> list[str] | None:
    if not isinstance(lines, list) or len(lines) != len(tweets):
        return None
    out: list[str] = []
    for raw, tw in zip(lines, tweets, strict=True):
        if not isinstance(raw, str):
            return None
        line = _sanitize_line(raw)
        if not line or tw not in line:
            return None
        out.append(line)
    return out


def generate_wait_fill_tts_lines(*, user: User, team: Team, tweets: list[str]) -> list[str]:
    if not tweets:
        return []
    tweets = [t.strip() for t in tweets[:MAX_TWEETS] if t and t.strip()]
    if not tweets:
        return []

    payload = json.dumps({"tweets": tweets}, ensure_ascii=False)
    llm = MaxChatOpenAI(
        user=user,
        team=team,
        model="gpt-4.1-mini",
        temperature=0.55,
        max_tokens=450,
        billable=False,
        inject_context=False,
        streaming=False,
        disable_streaming=True,
        posthog_properties={"ai_product": "posthog_ai", "voice_wait_fill_tts": True},
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    messages = [
        SystemMessage(content=WAIT_FILL_SYSTEM),
        HumanMessage(
            content=f"Generate spoken lines for voice TTS. Input JSON:\n{payload}\n"
            f'Remember: each output line must contain the matching tweet string exactly as given in "tweets".'
        ),
    ]
    try:
        result = llm.invoke(messages)
        content = result.content
        if isinstance(content, list):
            text = "".join(str(block) for block in content)
        else:
            text = str(content or "")
        data = json.loads(text)
        lines_raw = data.get("lines")
        validated = _validate_lines(tweets, lines_raw)
        if validated:
            return validated
    except Exception:
        pass
    return _fallback_lines(tweets)
