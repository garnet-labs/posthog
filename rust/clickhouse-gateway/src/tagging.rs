use serde_json::{json, Value};

/// Gateway version embedded in every log_comment for traceability.
const GATEWAY_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Construct a ClickHouse `log_comment` JSON string from the caller-supplied
/// `query_tags` and gateway-specific fields.
///
/// The resulting JSON is passed as a query parameter to ClickHouse and ends up
/// in `system.query_log.log_comment`, making it easy to attribute queries back
/// to their originating team, request, and gateway version.
///
/// Gateway fields (`gateway_request_id`, `gateway_version`) are always added
/// and take precedence over any caller-supplied tags with the same keys.
pub fn build_log_comment(query_tags: &Option<Value>, gateway_request_id: &str) -> String {
    let mut comment = match query_tags {
        Some(tags) if tags.is_object() => tags.clone(),
        _ => json!({}),
    };

    // Inject gateway-specific fields. These overwrite any caller-supplied
    // duplicates intentionally — the gateway is the source of truth for
    // these values.
    if let Some(obj) = comment.as_object_mut() {
        obj.insert(
            "gateway_request_id".to_string(),
            Value::String(gateway_request_id.to_string()),
        );
        obj.insert(
            "gateway_version".to_string(),
            Value::String(GATEWAY_VERSION.to_string()),
        );
    }

    comment.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_log_comment_no_tags() {
        let result = build_log_comment(&None, "req-001");
        let parsed: Value = serde_json::from_str(&result).unwrap();

        assert_eq!(parsed["gateway_request_id"], "req-001");
        assert_eq!(parsed["gateway_version"], GATEWAY_VERSION);
    }

    #[test]
    fn test_build_log_comment_with_tags() {
        let tags = Some(json!({
            "team_id": 42,
            "query_id": "abc-123",
            "source": "insights"
        }));
        let result = build_log_comment(&tags, "req-002");
        let parsed: Value = serde_json::from_str(&result).unwrap();

        assert_eq!(parsed["team_id"], 42);
        assert_eq!(parsed["query_id"], "abc-123");
        assert_eq!(parsed["source"], "insights");
        assert_eq!(parsed["gateway_request_id"], "req-002");
        assert_eq!(parsed["gateway_version"], GATEWAY_VERSION);
    }

    #[test]
    fn test_build_log_comment_gateway_fields_override_tags() {
        let tags = Some(json!({
            "gateway_request_id": "caller-supplied-id",
            "gateway_version": "0.0.0"
        }));
        let result = build_log_comment(&tags, "actual-req-id");
        let parsed: Value = serde_json::from_str(&result).unwrap();

        // Gateway fields always win.
        assert_eq!(parsed["gateway_request_id"], "actual-req-id");
        assert_eq!(parsed["gateway_version"], GATEWAY_VERSION);
    }

    #[test]
    fn test_build_log_comment_non_object_tags_ignored() {
        let tags = Some(json!("not an object"));
        let result = build_log_comment(&tags, "req-003");
        let parsed: Value = serde_json::from_str(&result).unwrap();

        assert_eq!(parsed["gateway_request_id"], "req-003");
        assert_eq!(parsed["gateway_version"], GATEWAY_VERSION);
        // Should only have gateway fields.
        assert_eq!(parsed.as_object().unwrap().len(), 2);
    }

    #[test]
    fn test_build_log_comment_empty_tags() {
        let tags = Some(json!({}));
        let result = build_log_comment(&tags, "req-004");
        let parsed: Value = serde_json::from_str(&result).unwrap();

        assert_eq!(parsed.as_object().unwrap().len(), 2);
        assert_eq!(parsed["gateway_request_id"], "req-004");
    }
}
