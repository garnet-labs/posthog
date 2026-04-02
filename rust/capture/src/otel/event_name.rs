use serde_json::Value;

/// Configuration for a single supported AI SDK. Adding a new SDK means adding
/// one entry here — both the namespace prefix (for broad span acceptance) and
/// the optional classifier (for specific event type mapping) live together, so
/// they can't get out of sync.
struct SupportedSdk {
    /// Accept any span whose attribute key starts with this prefix.
    prefix: &'static str,
    /// If set, a span with exactly this attribute key is mapped to a specific
    /// PostHog event type rather than the generic `$ai_span`.
    classifier: Option<Classifier>,
}

struct Classifier {
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

/// The complete list of supported AI SDKs. This is the single source of truth
/// for both span acceptance (via `prefix`) and event type classification (via
/// `classifier`). To add a new SDK: add one entry here.
///
/// Note: Traceloop's classifier key (`llm.request.type`) does not share the
/// `traceloop.` prefix — both are needed to catch all Traceloop spans.
const SUPPORTED_SDKS: &[SupportedSdk] = &[
    SupportedSdk {
        prefix: "gen_ai.",
        classifier: Some(Classifier {
            attr_key: "gen_ai.operation.name",
            classify: classify_gen_ai_operation,
        }),
    },
    SupportedSdk {
        prefix: "ai.",
        classifier: Some(Classifier {
            attr_key: "ai.operationId",
            classify: classify_vercel_ai_operation,
        }),
    },
    SupportedSdk {
        prefix: "traceloop.",
        classifier: Some(Classifier {
            attr_key: "llm.request.type",
            classify: classify_traceloop_request_type,
        }),
    },
    SupportedSdk {
        prefix: "pydantic_ai.",
        classifier: None,
    },
];

/// Lightweight pre-filter on raw protobuf attributes to avoid converting
/// irrelevant spans into JSON. Mirrors the logic in `get_event_name` so every
/// span that passes this gate produces a `Some` result there.
pub fn has_ai_attributes_raw(attrs: &[opentelemetry_proto::tonic::common::v1::KeyValue]) -> bool {
    attrs.iter().any(|kv| {
        SUPPORTED_SDKS.iter().any(|sdk| {
            kv.key.starts_with(sdk.prefix)
                || sdk
                    .classifier
                    .as_ref()
                    .is_some_and(|c| c.attr_key == kv.key)
        })
    })
}

pub fn get_event_name(attrs: &serde_json::Map<String, Value>) -> Option<&'static str> {
    for sdk in SUPPORTED_SDKS {
        if let Some(c) = &sdk.classifier {
            if let Some(value) = attrs.get(c.attr_key).and_then(|v| v.as_str()) {
                return Some((c.classify)(value));
            }
        }
    }

    if attrs
        .keys()
        .any(|key| SUPPORTED_SDKS.iter().any(|sdk| key.starts_with(sdk.prefix)))
    {
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
    fn test_supported_sdk_prefix_defaults_to_ai_span() {
        assert_eq!(
            get_event_name(&attrs_with("gen_ai.request.model", "gpt-4")),
            Some("$ai_span")
        );
        assert_eq!(
            get_event_name(&attrs_with("pydantic_ai.agent_name", "my-agent")),
            Some("$ai_span")
        );
        assert_eq!(
            get_event_name(&attrs_with("traceloop.workflow.name", "my-workflow")),
            Some("$ai_span")
        );
    }

    #[test]
    fn test_unsupported_sdk_returns_none() {
        // logfire is not a supported SDK — spans with only logfire attributes are dropped
        assert_eq!(
            get_event_name(&attrs_with("logfire.msg", "running 1 tool")),
            None
        );
    }

    #[test]
    fn test_irrelevant_span_returns_none() {
        // HTTP instrumentation spans have no AI attributes
        assert_eq!(
            get_event_name(&attrs_with("http.request.method", "POST")),
            None
        );
        // Empty span (no attributes at all)
        assert_eq!(get_event_name(&serde_json::Map::new()), None);
        // Unknown AI-adjacent framework — not in supported SDK list, so dropped
        assert_eq!(
            get_event_name(&attrs_with("langchain.chain.name", "my-chain")),
            None
        );
    }
}
