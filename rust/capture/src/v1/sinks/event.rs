use crate::v1::analytics::types::{EventResult, WrappedEvent};
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

    /// Event-owned metadata as key-value pairs. The Sink converts these to
    /// backend-specific headers and may merge in additional Sink/Context headers.
    fn headers(&self) -> Vec<(String, String)>;

    /// Partition/routing key for the backend. Needs Context for token, IP, etc.
    fn partition_key(&self, ctx: &Context) -> String;

    /// Serialize into the payload string for the backend.
    fn serialize(&self, ctx: &Context) -> Result<String, String>;
}

impl Event for WrappedEvent {
    fn uuid_key(&self) -> &str {
        &self.event.uuid
    }

    fn should_publish(&self) -> bool {
        self.result == EventResult::Ok && self.destination != Destination::Drop
    }

    fn destination(&self) -> &Destination {
        &self.destination
    }

    fn headers(&self) -> Vec<(String, String)> {
        let mut h = Vec::new();
        if self.skip_person_processing {
            h.push(("skip_person_processing".into(), "true".into()));
        }
        h
    }

    fn partition_key(&self, ctx: &Context) -> String {
        if self.event.options.cookieless_mode == Some(true) {
            let ip = if ctx.capture_internal {
                "127.0.0.1".to_string()
            } else {
                ctx.client_ip.to_string()
            };
            format!("{}:{}", ctx.api_token, ip)
        } else {
            format!("{}:{}", ctx.api_token, self.event.distinct_id)
        }
    }

    fn serialize(&self, _ctx: &Context) -> Result<String, String> {
        // TODO: builds IngestionEvent from self + Context, applies $-prefix
        // remapping, IP redaction, property merging. Tackled separately.
        unimplemented!("WrappedEvent::serialize")
    }
}
