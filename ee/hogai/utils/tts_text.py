"""
Normalize assistant text before ElevenLabs TTS.

ElevenLabs has no separate "prompt" for how to read abbreviations — the model only
receives `text`. We expand common abbreviations to spoken words/phrases so the voice
does not mangle acronyms or Latin shorthand.

See also: `apply_text_normalization` on the convert() call for number/date handling.
"""

from __future__ import annotations

import re
from typing import Final

# Longer tokens first (e.g. HTTPS before HTTP). Spoken forms favor clarity over brevity.
_TTS_SPEECH_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    # Latin / editorial
    ("e.g.", "for example"),
    ("i.e.", "that is"),
    ("etc.", "etcetera"),
    ("vs.", "versus"),
    ("approx.", "approximately"),
    ("ca.", "circa"),
    # DevOps phrases (before lone CI / CD tokens)
    ("CI/CD", "continuous integration and continuous delivery"),
    ("CI", "continuous integration"),
    # Networking & formats (full phrases where natural)
    ("HTTPS", "hypertext transfer protocol secure"),
    ("HTTP", "hypertext transfer protocol"),
    ("URL", "uniform resource locator"),
    ("URI", "uniform resource identifier"),
    ("API", "application programming interface"),
    ("REST", "representational state transfer"),
    ("GraphQL", "Graph Q L"),
    ("HogQL", "Hog Q L"),
    ("SQL", "sequel"),
    ("JSON", "J S O N"),
    ("YAML", "Y A M L"),
    ("XML", "X M L"),
    ("HTML", "H T M L"),
    ("CSS", "C S S"),
    ("DOM", "D O M"),
    ("JWT", "J W T"),
    ("OAuth", "open authorization"),
    ("SSO", "single sign on"),
    ("CDN", "C D N"),
    ("DNS", "D N S"),
    ("TCP", "T C P"),
    ("UDP", "U D P"),
    ("IP", "I P"),
    ("VPN", "V P N"),
    ("TLS", "T L S"),
    ("SSL", "S S L"),
    ("SMTP", "S M T P"),
    ("SDK", "S D K"),
    ("CLI", "C L I"),
    ("IDE", "I D E"),
    ("GUI", "G U I"),
    ("UI", "U I"),
    ("UX", "U X"),
    ("CPU", "C P U"),
    ("GPU", "G P U"),
    ("RAM", "R A M"),
    ("SSD", "S S D"),
    ("HDD", "H D D"),
    ("OSS", "open source software"),
    ("K8s", "Kubernetes"),
    ("KPI", "K P I"),
    ("ROI", "R O I"),
    ("SLA", "S L A"),
    ("STT", "speech to text"),
    ("TTS", "text to speech"),
    ("LLM", "large language model"),
    ("ML", "machine learning"),
    ("AI", "artificial intelligence"),
    ("NLP", "natural language processing"),
    ("CRUD", "create read update delete"),
    ("ORM", "O R M"),
)


def _pattern_for_token(token: str) -> re.Pattern[str]:
    """
    Word-start boundary; word-end only when token ends with '.' — \\b fails after the last
    period before a space (both are non-word chars), so we use a lookahead instead.
    """
    escaped = re.escape(token)
    if token.endswith("."):
        return re.compile(rf"\b{escaped}(?=\s|$|[,;:!?\)\]\}}]|['\"])", re.IGNORECASE)
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


def prepare_text_for_elevenlabs_tts(text: str) -> str:
    """
    Expand abbreviations to forms that read well aloud. Case-insensitive token match.
    """
    result = text
    for token, spoken in _TTS_SPEECH_REPLACEMENTS:
        result = _pattern_for_token(token).sub(spoken, result)
    return re.sub(r"[ \t]+", " ", result).strip()
