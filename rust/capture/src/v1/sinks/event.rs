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

/// Merge event-level headers with Context-level headers into a complete,
/// transport-agnostic set. The Sink converts the result to its own format
/// (e.g. Kafka OwnedHeaders).
pub fn build_headers(ctx: &Context, event_headers: Vec<(String, String)>) -> Vec<(String, String)> {
    let mut headers = event_headers;
    headers.push(("token".into(), ctx.api_token.clone()));
    headers.push(("now".into(), ctx.server_received_at.to_rfc3339()));
    if ctx.historical_migration {
        headers.push(("historical_migration".into(), "true".into()));
    }
    headers
}
