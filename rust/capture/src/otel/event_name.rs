use serde_json::Value;

/// A classifier checks a single span attribute and maps its value to a PostHog
/// event name. Classifiers are tried in order; the first match wins.
struct EventClassifier {
    attr_key: &'static str,
    classify: fn(&str) -> &'static str,
}

fn classify_gen_ai_operation(op: &str) -> &'static str {
    match op {
        "chat" => "$ai_generation",
        "embeddings" => "$ai_embedding",
        _ => "$ai_span",
    }
}

fn classify_traceloop_request_type(request_type: &str) -> &'static str {
    match request_type {
        "chat" | "completion" => "$ai_generation",
        "embedding" | "embeddings" => "$ai_embedding",
        _ => "$ai_span",
    }
}

fn classify_vercel_ai_operation(op_id: &str) -> &'static str {
    match op_id {
        s if s.ends_with(".doGenerate") || s.ends_with(".doStream") => "$ai_generation",
        s if s == "ai.embed.doEmbed" || s == "ai.embedMany.doEmbed" => "$ai_embedding",
        _ => "$ai_span",
    }
}

const EVENT_CLASSIFIERS: &[EventClassifier] = &[
    EventClassifier {
        attr_key: "gen_ai.operation.name",
        classify: classify_gen_ai_operation,
    },
    EventClassifier {
        attr_key: "llm.request.type",
        classify: classify_traceloop_request_type,
    },
    EventClassifier {
        attr_key: "ai.operationId",
        classify: classify_vercel_ai_operation,
    },
];

const AI_ATTRIBUTE_PREFIXES: &[&str] = &["gen_ai.", "pydantic_ai.", "traceloop."];

/// Attribute keys that indicate an AI-related span when no classifier matches.
/// These are intentionally broad — a false positive (non-AI span ingested as
/// `$ai_span`) is harmless, while a false negative (real AI span dropped) loses
/// data. Keys already handled by `EVENT_CLASSIFIERS` are omitted since the
/// classifier loop runs first.
const AI_MARKER_KEYS: &[&str] = &[
    "ai.telemetry.functionId",
    "agent_name",
    "final_result",
    "logfire.json_schema",
    "logfire.msg",
    "model_name",
    "model_request_parameters",
    "tool_arguments",
    "tool_response",
];

fn has_ai_markers(attrs: &serde_json::Map<String, Value>) -> bool {
    attrs.keys().any(|key| {
        AI_ATTRIBUTE_PREFIXES
            .iter()
            .any(|prefix| key.starts_with(prefix))
            || AI_MARKER_KEYS.contains(&key.as_str())
    })
}

/// Lightweight check on raw protobuf attributes to avoid converting irrelevant
/// spans into JSON. Derives classifier keys from `EVENT_CLASSIFIERS` so the
/// two stay in sync automatically.
pub fn has_ai_attributes_raw(attrs: &[opentelemetry_proto::tonic::common::v1::KeyValue]) -> bool {
    attrs.iter().any(|kv| {
        AI_ATTRIBUTE_PREFIXES
            .iter()
            .any(|prefix| kv.key.starts_with(prefix))
            || AI_MARKER_KEYS.contains(&kv.key.as_str())
            || EVENT_CLASSIFIERS.iter().any(|c| c.attr_key == kv.key)
    })
}

pub fn get_event_name(attrs: &serde_json::Map<String, Value>) -> Option<&'static str> {
    for c in EVENT_CLASSIFIERS {
        if let Some(value) = attrs.get(c.attr_key).and_then(|v| v.as_str()) {
            return Some((c.classify)(value));
        }
    }

    if has_ai_markers(attrs) {
        Some("$ai_span")
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn attrs_with(key: &str, value: &str) -> serde_json::Map<String, Value> {
        let mut map = serde_json::Map::new();
        map.insert(key.to_string(), Value::String(value.to_string()));
        map
    }

    #[test]
    fn test_from_gen_ai_operation_name() {
        assert_eq!(
            get_event_name(&attrs_with("gen_ai.operation.name", "chat")),
            Some("$ai_generation")
        );
        assert_eq!(
            get_event_name(&attrs_with("gen_ai.operation.name", "embeddings")),
            Some("$ai_embedding")
        );
        assert_eq!(
            get_event_name(&attrs_with("gen_ai.operation.name", "unknown")),
            Some("$ai_span")
        );
        assert_eq!(get_event_name(&serde_json::Map::new()), None);
    }

    #[test]
    fn test_from_vercel_ai_operation_id() {
        for (op_id, expected) in [
            ("ai.generateText.doGenerate", "$ai_generation"),
            ("ai.streamText.doStream", "$ai_generation"),
            ("ai.generateObject.doGenerate", "$ai_generation"),
            ("ai.streamObject.doStream", "$ai_generation"),
            ("ai.embed.doEmbed", "$ai_embedding"),
            ("ai.embedMany.doEmbed", "$ai_embedding"),
            ("ai.toolCall", "$ai_span"),
            ("ai.generateText", "$ai_span"),
            ("ai.streamText", "$ai_span"),
        ] {
            assert_eq!(
                get_event_name(&attrs_with("ai.operationId", op_id)),
                Some(expected),
                "ai.operationId={op_id}"
            );
        }
    }

    #[test]
    fn test_from_traceloop_request_type() {
        for (request_type, expected) in [
            ("chat", "$ai_generation"),
            ("completion", "$ai_generation"),
            ("embedding", "$ai_embedding"),
            ("embeddings", "$ai_embedding"),
            ("rerank", "$ai_span"),
            ("unknown", "$ai_span"),
        ] {
            assert_eq!(
                get_event_name(&attrs_with("llm.request.type", request_type)),
                Some(expected),
                "llm.request.type={request_type}"
            );
        }
    }

    #[test]
    fn test_gen_ai_operation_name_takes_precedence() {
        let mut attrs = serde_json::Map::new();
        attrs.insert(
            "gen_ai.operation.name".to_string(),
            Value::String("chat".to_string()),
        );
        attrs.insert(
            "ai.operationId".to_string(),
            Value::String("ai.toolCall".to_string()),
        );
        assert_eq!(get_event_name(&attrs), Some("$ai_generation"));
    }

    #[test]
    fn test_relevant_ai_markers_default_to_ai_span() {
        assert_eq!(
            get_event_name(&attrs_with("gen_ai.request.model", "gpt-4")),
            Some("$ai_span")
        );
        assert_eq!(
            get_event_name(&attrs_with("logfire.msg", "running 1 tool")),
            Some("$ai_span")
        );
    }

    #[test]
    fn test_irrelevant_span_returns_none() {
        assert_eq!(
            get_event_name(&attrs_with("http.request.method", "POST")),
            None
        );
    }
}
