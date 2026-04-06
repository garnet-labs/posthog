use crate::v1::context::Context;
use crate::v1::sinks::Destination;

/// Transport-agnostic trait declaring an event's identity, routing intent,
/// metadata, and serialization. The [`Sink`](super::sink::Sink) implementation
/// resolves `destination()` to a concrete backend target using its own config.
pub trait Event: Send + Sync {
    /// UUID of the originating event -- correlation key for mapping results back.
    fn uuid_key(&self) -> &str;

    /// Whether this event should be published. Events returning false are
    /// silently skipped by the Sink -- no `SinkResult` is returned for them.
    fn should_publish(&self) -> bool;

    /// Semantic routing destination. The Sink resolves this to a concrete
    /// backend target (e.g. Kafka topic) using its own config.
    fn destination(&self) -> &Destination;

    /// Event-owned metadata as key-value pairs. The Sink passes these through
    /// `build_headers` to merge with Context-level headers before converting
    /// to transport-specific format.
    fn headers(&self) -> Vec<(String, String)>;

    /// Partition/routing key for the backend. Needs Context for token, IP, etc.
    fn partition_key(&self, ctx: &Context) -> String;

    /// Serialize into the payload string for the backend.
    fn serialize(&self, ctx: &Context) -> Result<String, String>;
}

/// Build the context-level headers that are identical for every event in a
/// batch: token, server timestamp, and (optionally) historical_migration.
/// Called once per batch; event-level headers are merged separately.
pub fn build_context_headers(ctx: &Context) -> Vec<(String, String)> {
    let mut headers = Vec::with_capacity(3);
    headers.push(("token".into(), ctx.api_token.clone()));
    headers.push(("now".into(), ctx.server_received_at.to_rfc3339()));
    if ctx.historical_migration {
        headers.push(("historical_migration".into(), "true".into()));
    }
    headers
}

/// Merge event-level headers with Context-level headers into a complete,
/// transport-agnostic set. The Sink converts the result to its own format
/// (e.g. Kafka OwnedHeaders).
pub fn build_headers(ctx: &Context, event_headers: Vec<(String, String)>) -> Vec<(String, String)> {
    let mut headers = event_headers;
    headers.extend(build_context_headers(ctx));
    headers
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::v1::test_utils;

    fn header_val(headers: &[(String, String)], key: &str) -> Option<String> {
        headers
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.clone())
    }

    #[test]
    fn context_headers_include_token_and_now() {
        let ctx = test_utils::test_context();
        let headers = build_context_headers(&ctx);
        assert_eq!(header_val(&headers, "token"), Some(ctx.api_token.clone()));
        assert!(header_val(&headers, "now").is_some());
    }

    #[test]
    fn context_headers_include_historical_migration_when_set() {
        let mut ctx = test_utils::test_context();
        ctx.historical_migration = true;
        let headers = build_context_headers(&ctx);
        assert_eq!(
            header_val(&headers, "historical_migration"),
            Some("true".into())
        );
    }

    #[test]
    fn context_headers_omit_historical_migration_when_false() {
        let mut ctx = test_utils::test_context();
        ctx.historical_migration = false;
        let headers = build_context_headers(&ctx);
        assert!(header_val(&headers, "historical_migration").is_none());
    }

    #[test]
    fn build_headers_preserves_event_headers_first() {
        let ctx = test_utils::test_context();
        let event_headers = vec![("custom_key".into(), "custom_val".into())];
        let merged = build_headers(&ctx, event_headers);

        assert_eq!(merged[0].0, "custom_key");
        assert_eq!(merged[0].1, "custom_val");
        assert_eq!(header_val(&merged, "token"), Some(ctx.api_token.clone()));
    }

    #[test]
    fn build_headers_with_empty_event_headers() {
        let ctx = test_utils::test_context();
        let merged = build_headers(&ctx, vec![]);
        assert!(header_val(&merged, "token").is_some());
        assert!(header_val(&merged, "now").is_some());
    }
}
