"""PostHog LLM Analytics instrumentation for the PR approval agent.

Captures $ai_generation and $ai_trace events so stamphog runs
are visible in the LLM Analytics dashboard.
"""

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from posthoganalytics import Posthog

_INTERNAL_PROJECT_API_KEY = "sTMFPsFhdP1Ssg"
_INTERNAL_HOST = "https://us.i.posthog.com"
DISTINCT_ID = "stamphog-ci-bot"


def create_client() -> Posthog | None:
    """Create a PostHog client for LLM analytics.

    Uses the internal PostHog project key by default so no extra secrets
    are needed.  Set OPT_OUT_CAPTURE=1 to disable.
    """
    if os.environ.get("OPT_OUT_CAPTURE", "").lower() in ("true", "yes", "1"):
        return None
    api_key = os.environ.get("STAMPHOG_POSTHOG_API_KEY", _INTERNAL_PROJECT_API_KEY)
    host = os.environ.get("STAMPHOG_POSTHOG_HOST", _INTERNAL_HOST)
    return Posthog(api_key, host=host)


@dataclass
class TraceRecorder:
    """Records LLM analytics events for a single pipeline run.

    Collects $ai_generation events from reviewer calls and emits
    a $ai_trace event when the pipeline completes.
    """

    client: Posthog | None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _start_time: float = field(default_factory=time.monotonic)
    _generations: list[dict[str, Any]] = field(default_factory=list)
    _pr_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def set_pr_metadata(
        self,
        pr_number: int,
        repo: str,
        author: str,
        title: str,
        tier: str,
        t1_subclass: str,
        lines_total: int,
        files_changed: int,
    ) -> None:
        self._pr_metadata = {
            "stamphog_pr_number": pr_number,
            "stamphog_repo": repo,
            "stamphog_author": author,
            "stamphog_title": title[:200],
            "stamphog_tier": tier,
            "stamphog_t1_subclass": t1_subclass,
            "stamphog_lines_total": lines_total,
            "stamphog_files_changed": files_changed,
        }

    def record_generation(
        self,
        *,
        model: str,
        input_messages: list[dict[str, str]],
        output_text: str,
        usage: dict[str, Any] | None = None,
        model_usage: dict[str, Any] | None = None,
        duration_ms: int = 0,
        total_cost_usd: float | None = None,
        num_turns: int = 0,
        stop_reason: str | None = None,
    ) -> None:
        """Record a single LLM generation (reviewer call)."""
        if not self.enabled:
            return

        input_tokens = 0
        output_tokens = 0
        cache_read_tokens = 0
        cache_creation_tokens = 0

        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read_tokens = usage.get("cache_read_input_tokens", 0)
            cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)

        generation = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": duration_ms,
            "total_cost_usd": total_cost_usd,
        }
        self._generations.append(generation)

        properties: dict[str, Any] = {
            "$ai_trace_id": self.trace_id,
            "$ai_model": model,
            "$ai_provider": "anthropic",
            "$ai_input": input_messages,
            "$ai_input_tokens": input_tokens,
            "$ai_output_choices": [{"role": "assistant", "content": output_text[:5000]}],
            "$ai_output_tokens": output_tokens,
            "$ai_latency": duration_ms / 1000.0,
            "$ai_is_error": False,
            "$ai_stream": True,
            **self._pr_metadata,
            "stamphog_num_turns": num_turns,
            "stamphog_stop_reason": stop_reason or "",
        }

        if total_cost_usd is not None:
            properties["$ai_total_cost_usd"] = total_cost_usd

        if cache_read_tokens:
            properties["$ai_cache_read_input_tokens"] = cache_read_tokens
        if cache_creation_tokens:
            properties["$ai_cache_creation_input_tokens"] = cache_creation_tokens

        if model_usage:
            for model_name, model_stats in model_usage.items():
                properties[f"stamphog_model_{model_name}_input_tokens"] = model_stats.get("input_tokens", 0)
                properties[f"stamphog_model_{model_name}_output_tokens"] = model_stats.get("output_tokens", 0)

        try:
            self.client.capture(
                event="$ai_generation",
                distinct_id=DISTINCT_ID,
                properties=properties,
            )
        except Exception:
            pass

    def record_trace(
        self,
        *,
        verdict: str,
        gate_verdict: str,
        gate_results: list[dict[str, Any]],
        reviewer_output: dict[str, Any] | None = None,
    ) -> None:
        """Record the overall pipeline trace."""
        if not self.enabled:
            return

        total_latency = time.monotonic() - self._start_time
        total_input_tokens = sum(g["input_tokens"] for g in self._generations)
        total_output_tokens = sum(g["output_tokens"] for g in self._generations)
        total_cost = sum(g["total_cost_usd"] for g in self._generations if g["total_cost_usd"] is not None)

        properties: dict[str, Any] = {
            "$ai_trace_id": self.trace_id,
            "$ai_latency": total_latency,
            "$ai_input_tokens": total_input_tokens,
            "$ai_output_tokens": total_output_tokens,
            "$ai_input_state": {
                "gate_verdict": gate_verdict,
                "gates": gate_results,
                **self._pr_metadata,
            },
            "$ai_output_state": {
                "final_verdict": verdict,
                "reviewer": reviewer_output,
            },
            **self._pr_metadata,
            "stamphog_final_verdict": verdict,
            "stamphog_gate_verdict": gate_verdict,
            "stamphog_generation_count": len(self._generations),
        }

        if total_cost > 0:
            properties["$ai_total_cost_usd"] = total_cost

        try:
            self.client.capture(
                event="$ai_trace",
                distinct_id=DISTINCT_ID,
                properties=properties,
            )
        except Exception:
            pass

    def flush(self) -> None:
        """Ensure all events are sent before the process exits."""
        if self.enabled:
            try:
                self.client.flush()
            except Exception:
                pass
