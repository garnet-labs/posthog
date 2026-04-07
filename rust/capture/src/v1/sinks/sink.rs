use async_trait::async_trait;

use crate::v1::context::Context;
use crate::v1::sinks::event::Event;
use crate::v1::sinks::types::SinkResult;
use crate::v1::sinks::SinkName;

/// Backend-agnostic publishing interface.
#[async_trait]
pub trait Sink: Send + Sync {
    /// Publish a single event to a specific sink. Returns None if the
    /// event was filtered (should_publish false / Destination::Drop).
    async fn publish(
        &self,
        sink: SinkName,
        ctx: &Context,
        event: &(dyn Event + Send + Sync),
    ) -> Option<Box<dyn SinkResult>>;

    /// Publish a batch of events to a specific sink. Returns one result
    /// per published event -- skipped events produce no result.
    async fn publish_batch(
        &self,
        sink: SinkName,
        ctx: &Context,
        events: &[&(dyn Event + Send + Sync)],
    ) -> Vec<Box<dyn SinkResult>>;

    /// Which sinks are available for writing.
    fn sinks(&self) -> Vec<SinkName>;

    /// Flush the underlying producer(s) for graceful shutdown.
    async fn flush(&self) -> anyhow::Result<()>;
}
