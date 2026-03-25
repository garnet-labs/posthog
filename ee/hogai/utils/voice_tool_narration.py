import re
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from posthog.models import Team, User

from ee.hogai.llm import MaxChatOpenAI

MAX_OUTPUT_CHARS = 280
_ASSISTANT_TRUNC = 3500
_ARG_JSON_TRUNC = 6000


def _truncate_json_friendly(obj: Any, max_str: int, max_depth: int, depth: int = 0) -> Any:
    if depth > max_depth:
        return "…"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= max_str else obj[:max_str] + "…"
    if isinstance(obj, list):
        return [_truncate_json_friendly(x, max_str, max_depth, depth + 1) for x in obj[:24]]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= 48:
                break
            out[str(k)] = _truncate_json_friendly(v, max_str, max_depth, depth + 1)
        return out
    return str(obj)[:max_str]


def _build_user_message(
    tool_names: list[str],
    assistant_content: str | None,
    tool_args_by_name: dict[str, Any] | None,
    ui_payload: dict[str, Any] | None,
    recent_narrations: list[str],
) -> str:
    payload: dict[str, Any] = {
        "tools": tool_names,
    }
    if assistant_content:
        payload["assistant_said"] = assistant_content[:_ASSISTANT_TRUNC]
    if tool_args_by_name is not None:
        trimmed = _truncate_json_friendly(tool_args_by_name, 400, 4)
        raw = json.dumps(trimmed, ensure_ascii=False, default=str)
        payload["tool_arguments"] = raw[:_ARG_JSON_TRUNC]
    if ui_payload:
        trimmed = _truncate_json_friendly(ui_payload, 400, 3)
        raw = json.dumps(trimmed, ensure_ascii=False, default=str)
        payload["ui_context"] = raw[:_ARG_JSON_TRUNC]
    if recent_narrations:
        payload["avoid_repeating_these_spoken_lines"] = [r[:220] for r in recent_narrations[-10:]]

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sanitize_llm_output(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^[`\"'“”]+|[`\"'“”]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    if len(s) > MAX_OUTPUT_CHARS:
        s = s[: MAX_OUTPUT_CHARS - 1].rsplit(" ", 1)[0] + "…"
    return s


TOOL_NARRATION_SYSTEM = f"""You write one short line for text-to-speech when the PostHog AI assistant is about to run tools.
Output exactly one sentence in first person ("I'm ..."), natural spoken English, conversational.
Briefly explain why these tools are being used, using only the JSON context below. Paraphrase intent in plain language — do not read out raw JSON, SQL, column lists, or UUIDs.
If "avoid_repeating_these_spoken_lines" is present, do not reuse the same openings or rhythm as those lines; vary structure and wording.
Maximum {MAX_OUTPUT_CHARS} characters. No markdown, no bullets, no emojis, no quotation marks wrapping the whole line."""


def generate_tool_call_narration_sentence(
    *,
    user: User,
    team: Team,
    tool_names: list[str],
    assistant_content: str | None,
    tool_args_by_name: dict[str, Any] | None,
    ui_payload: dict[str, Any] | None,
    recent_narrations: list[str],
) -> str:
    user_text = _build_user_message(
        tool_names=tool_names,
        assistant_content=assistant_content,
        tool_args_by_name=tool_args_by_name,
        ui_payload=ui_payload,
        recent_narrations=recent_narrations,
    )
    llm = MaxChatOpenAI(
        user=user,
        team=team,
        model="gpt-4.1-mini",
        temperature=0.65,
        max_tokens=120,
        billable=False,
        inject_context=False,
        streaming=False,
        disable_streaming=True,
        posthog_properties={"ai_product": "posthog_ai", "voice_tool_narration": True},
    )
    messages = [
        SystemMessage(content=TOOL_NARRATION_SYSTEM),
        HumanMessage(content=user_text),
    ]
    result = llm.invoke(messages)
    content = result.content
    if isinstance(content, list):
        text = "".join(str(block) for block in content)
    else:
        text = str(content or "")
    sentence = _sanitize_llm_output(text)
    if not sentence:
        raise ValueError("Empty narration from model")
    return sentence
