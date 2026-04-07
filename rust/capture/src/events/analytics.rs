//! Analytics event processing
//!
//! This module handles processing of regular analytics events (pageviews, custom events,
//! exceptions, etc.) as opposed to recordings (session replay).

use std::collections::HashMap;
use std::sync::Arc;

use chrono::DateTime;
use common_types::{CapturedEvent, RawEvent};
use limiters::token_dropper::TokenDropper;
use serde_json;
use tracing::{error, instrument, Span};

use crate::{
    api::CaptureError,
    debug_or_info, error_tracking_sampler,
    event_restrictions::{EventContext as RestrictionEventContext, EventRestrictionService},
    prometheus::{report_clock_skew, report_dropped_events},
    router, sinks,
    utils::uuid_v7,
    v0_request::{DataType, ProcessedEvent, ProcessedEventMetadata, ProcessingContext},
};

/// Property keys that the heatmap extraction pipeline reads from the event.
/// When a non-$$heatmap event carries heatmap data, we produce a second message
/// to the heatmaps topic containing only these properties.
const HEATMAP_PROPERTY_KEYS: &[&str] = &[
    "$heatmap_data",
    "$viewport_height",
    "$viewport_width",
    "$session_id",
    "$prev_pageview_pathname",
    "$prev_pageview_max_scroll",
    "$current_url",
];

/// Returns true if this event carries data that the heatmap extraction pipeline would process.
fn has_heatmap_data(event: &RawEvent) -> bool {
    event.properties.contains_key("$heatmap_data")
        || (event.properties.contains_key("$prev_pageview_pathname")
            && event.properties.contains_key("$current_url"))
}

/// Create a stripped-down $$heatmap event from a non-$$heatmap event that contains heatmap data.
/// The redirect carries only the properties the heatmap pipeline needs, and gets a new UUID
/// to avoid deduplication with the original event.
fn create_heatmap_redirect(
    event: &RawEvent,
    historical_cfg: router::HistoricalConfig,
    context: &ProcessingContext,
) -> Result<ProcessedEvent, CaptureError> {
    let mut properties = HashMap::new();

    for key in HEATMAP_PROPERTY_KEYS {
        if let Some(value) = event.properties.get(*key) {
            properties.insert(key.to_string(), value.clone());
        }
    }

    // Preserve distinct_id and $cookieless_mode — needed for routing key generation
    if let Some(value) = event.properties.get("distinct_id") {
        properties.insert("distinct_id".to_string(), value.clone());
    }
    if let Some(value) = event.properties.get("$cookieless_mode") {
        properties.insert("$cookieless_mode".to_string(), value.clone());
    }

    let heatmap_event = RawEvent {
        token: event.token.clone(),
        distinct_id: event.distinct_id.clone(),
        uuid: Some(uuid_v7()),
        event: "$$heatmap".to_string(),
        properties,
        timestamp: event.timestamp.clone(),
        offset: event.offset,
        set: None,
        set_once: None,
    };

    let mut processed = process_single_event(&heatmap_event, historical_cfg, context)?;
    processed.metadata.process_heatmap = true;
    Ok(processed)
}

/// Strip heatmap-only properties from a ProcessedEvent's serialized data field
/// and mark it so the pipeline knows heatmap data was already redirected.
fn strip_heatmap_data(event: &mut ProcessedEvent) {
    if let Ok(mut raw_event) = serde_json::from_str::<RawEvent>(&event.event.data) {
        if raw_event.properties.remove("$heatmap_data").is_some() {
            if let Ok(data) = serde_json::to_string(&raw_event) {
                event.event.data = data;
            }
        }
    }
    event.metadata.process_heatmap = true;
}

/// Process a single analytics event from RawEvent to ProcessedEvent
#[instrument(skip_all, fields(event_name, request_id))]
pub fn process_single_event(
    event: &RawEvent,
    historical_cfg: router::HistoricalConfig,
    context: &ProcessingContext,
) -> Result<ProcessedEvent, CaptureError> {
    if event.event.is_empty() {
        return Err(CaptureError::MissingEventName);
    }
    Span::current().record("event_name", &event.event);
    Span::current().record("is_mirror_deploy", context.is_mirror_deploy);
    Span::current().record("request_id", &context.request_id);

    let data_type = match (event.event.as_str(), context.historical_migration) {
        ("$$client_ingestion_warning", _) => DataType::ClientIngestionWarning,
        ("$exception", _) if error_tracking_sampler::should_route_to_node() => {
            metrics::counter!("capture_exception_events_routed_to_node").increment(1);
            DataType::ExceptionErrorTracking
        }
        ("$exception", _) => DataType::ExceptionMain,
        ("$$heatmap", _) => DataType::HeatmapMain,
        (_, true) => DataType::AnalyticsHistorical,
        (_, false) => DataType::AnalyticsMain,
    };

    // Redact the IP address of internally-generated events when tagged as such
    let resolved_ip = if event.properties.contains_key("capture_internal") {
        "127.0.0.1".to_string()
    } else {
        context.client_ip.clone()
    };

    let data = serde_json::to_string(&event).map_err(|e| {
        error!("failed to encode data field: {e:#}");
        CaptureError::NonRetryableSinkError
    })?;

    // Compute the actual event timestamp using our timestamp parsing logic
    let sent_at_utc = context.sent_at.map(|sa| {
        DateTime::from_timestamp(sa.unix_timestamp(), sa.nanosecond()).unwrap_or_default()
    });
    let ignore_sent_at = event
        .properties
        .get("$ignore_sent_at")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    // Parse the event timestamp
    let parsed_timestamp = common_types::timestamp::parse_event_timestamp(
        event.timestamp.as_deref(),
        event.offset,
        sent_at_utc,
        ignore_sent_at,
        context.now,
    );
    if let Some(skew) = parsed_timestamp.clock_skew {
        report_clock_skew(skew);
    }

    let event_name = event.event.clone();

    let mut metadata = ProcessedEventMetadata {
        data_type,
        session_id: None,
        computed_timestamp: Some(parsed_timestamp.timestamp),
        event_name: event_name.clone(),
        force_overflow: false,
        skip_person_processing: false,
        redirect_to_dlq: false,
        redirect_to_topic: None,
        process_heatmap: false,
    };

    if historical_cfg.should_reroute(metadata.data_type, parsed_timestamp.timestamp) {
        metrics::counter!(
            "capture_events_rerouted_historical",
            &[("reason", "timestamp")]
        )
        .increment(1);
        metadata.data_type = DataType::AnalyticsHistorical;
    }

    let event = CapturedEvent {
        uuid: event.uuid.unwrap_or_else(uuid_v7),
        distinct_id: event
            .extract_distinct_id()
            .ok_or(CaptureError::MissingDistinctId)?,
        session_id: metadata.session_id.clone(),
        ip: resolved_ip,
        data,
        now: context
            .now
            .to_rfc3339_opts(chrono::SecondsFormat::AutoSi, true),
        sent_at: context.sent_at,
        token: context.token.clone(),
        event: event_name,
        timestamp: parsed_timestamp.timestamp,
        is_cookieless_mode: event
            .extract_is_cookieless_mode()
            .ok_or(CaptureError::InvalidCookielessMode)?,
        historical_migration: metadata.data_type == DataType::AnalyticsHistorical,
    };

    Ok(ProcessedEvent { metadata, event })
}

/// Process a batch of analytics events
#[instrument(skip_all, fields(events = events.len(), request_id))]
pub async fn process_events<'a>(
    sink: Arc<dyn sinks::Event + Send + Sync>,
    dropper: Arc<TokenDropper>,
    restriction_service: Option<EventRestrictionService>,
    historical_cfg: router::HistoricalConfig,
    events: &'a [RawEvent],
    context: &'a ProcessingContext,
) -> Result<(), CaptureError> {
    let chatty_debug_enabled = context.chatty_debug_enabled;

    Span::current().record("request_id", &context.request_id);
    Span::current().record("is_mirror_deploy", context.is_mirror_deploy);

    // Identify which raw events need heatmap redirects before `events` is shadowed.
    let needs_heatmap_redirect: Vec<bool> = events
        .iter()
        .map(|e| e.event != "$$heatmap" && has_heatmap_data(e))
        .collect();

    let mut heatmap_redirects: Vec<ProcessedEvent> = Vec::new();
    for (e, needs_redirect) in events.iter().zip(needs_heatmap_redirect.iter()) {
        if *needs_redirect {
            match create_heatmap_redirect(e, historical_cfg.clone(), context) {
                Ok(processed) => {
                    metrics::counter!("capture_heatmap_redirects_created").increment(1);
                    heatmap_redirects.push(processed);
                }
                Err(err) => {
                    error!("failed to create heatmap redirect: {err:#}");
                }
            }
        }
    }

    let mut events: Vec<ProcessedEvent> = events
        .iter()
        .map(|e| process_single_event(e, historical_cfg.clone(), context))
        .collect::<Result<Vec<ProcessedEvent>, CaptureError>>()?;

    // Strip heatmap data from originals that got redirects
    for (event, needs_redirect) in events.iter_mut().zip(needs_heatmap_redirect.iter()) {
        if *needs_redirect {
            strip_heatmap_data(event);
        }
    }

    events.extend(heatmap_redirects);

    debug_or_info!(chatty_debug_enabled, context=?context, event_count=?events.len(), "created ProcessedEvents batch");

    events.retain(|e| {
        if dropper.should_drop(&e.event.token, &e.event.distinct_id) {
            report_dropped_events("token_dropper", 1);
            false
        } else {
            true
        }
    });

    debug_or_info!(chatty_debug_enabled, context=?context, event_count=?events.len(), "filtered by token_dropper");

    // Apply event restrictions if service is configured
    if let Some(ref service) = restriction_service {
        let mut filtered_events = Vec::with_capacity(events.len());
        let now_ts = context.now.timestamp();

        for e in events {
            let uuid_str = e.event.uuid.to_string();
            let event_ctx = RestrictionEventContext {
                distinct_id: Some(&e.event.distinct_id),
                session_id: e.event.session_id.as_deref(),
                event_name: Some(&e.event.event),
                event_uuid: Some(&uuid_str),
                now_ts,
            };

            let applied = service.get_restrictions(&e.event.token, &event_ctx).await;

            if applied.should_drop() {
                report_dropped_events("event_restriction_drop", 1);
                continue;
            }

            let mut event = e;
            event.metadata.force_overflow |= applied.force_overflow();
            event.metadata.skip_person_processing |= applied.skip_person_processing();
            event.metadata.redirect_to_dlq |= applied.redirect_to_dlq();
            if let Some(topic) = applied.redirect_to_topic() {
                event.metadata.redirect_to_topic = Some(topic.to_string());
            }

            filtered_events.push(event);
        }

        events = filtered_events;
        debug_or_info!(chatty_debug_enabled, context=?context, event_count=?events.len(), "filtered by event_restrictions");
    }

    if events.is_empty() {
        return Ok(());
    }

    if events.len() == 1 {
        sink.send(events[0].clone()).await?;
    } else {
        sink.send_batch(events).await?;
    }

    debug_or_info!(chatty_debug_enabled, context=?context, "sent analytics events");

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::v0_request::ProcessingContext;
    use chrono::{DateTime, TimeZone, Utc};
    use common_types::RawEvent;
    use serde_json::json;
    use std::collections::HashMap;
    use time::OffsetDateTime;

    fn create_test_context(
        now: DateTime<Utc>,
        sent_at: Option<OffsetDateTime>,
    ) -> ProcessingContext {
        ProcessingContext {
            lib_version: None,
            user_agent: None,
            sent_at,
            token: "test_token".to_string(),
            now,
            client_ip: "127.0.0.1".to_string(),
            request_id: "test_request".to_string(),
            path: "/e/".to_string(),
            is_mirror_deploy: false,
            historical_migration: false,
            chatty_debug_enabled: false,
        }
    }

    fn create_test_event(
        timestamp: Option<String>,
        offset: Option<i64>,
        ignore_sent_at: Option<bool>,
    ) -> RawEvent {
        create_test_event_with_name("test_event", timestamp, offset, ignore_sent_at)
    }

    fn create_test_event_with_name(
        event_name: &str,
        timestamp: Option<String>,
        offset: Option<i64>,
        ignore_sent_at: Option<bool>,
    ) -> RawEvent {
        let mut properties = HashMap::new();
        if let Some(ignore) = ignore_sent_at {
            properties.insert("$ignore_sent_at".to_string(), json!(ignore));
        }
        properties.insert("distinct_id".to_string(), json!("test_user"));

        RawEvent {
            uuid: Some(uuid_v7()),
            distinct_id: None,
            event: event_name.to_string(),
            properties,
            timestamp,
            offset,
            set: Some(HashMap::new()),
            set_once: Some(HashMap::new()),
            token: Some("test_token".to_string()),
        }
    }

    #[test]
    fn test_process_single_event_with_invalid_sent_at() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let context = create_test_context(now, None);
        let event = create_test_event(Some("2023-01-01T11:00:00Z".to_string()), None, None);
        let historical_cfg = router::HistoricalConfig::new(false, 1);
        let result = process_single_event(&event, historical_cfg, &context);

        assert!(result.is_ok());
        let processed = result.unwrap();
        let expected = DateTime::parse_from_rfc3339("2023-01-01T11:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        assert_eq!(processed.metadata.computed_timestamp, Some(expected));
    }

    #[test]
    fn test_process_single_event_with_valid_sent_at() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let sent_at = OffsetDateTime::parse(
            "2023-01-01T12:00:05Z",
            &time::format_description::well_known::Rfc3339,
        )
        .unwrap();
        let context = create_test_context(now, Some(sent_at));

        let event = create_test_event(Some("2023-01-01T11:59:55Z".to_string()), None, None);

        let historical_cfg = router::HistoricalConfig::new(false, 1);
        let result = process_single_event(&event, historical_cfg, &context);

        assert!(result.is_ok());
        let processed = result.unwrap();
        let expected = Utc.with_ymd_and_hms(2023, 1, 1, 11, 59, 50).unwrap();
        assert_eq!(processed.metadata.computed_timestamp, Some(expected));
    }

    #[test]
    fn test_process_single_event_ignore_sent_at() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let sent_at = OffsetDateTime::parse(
            "2023-01-01T12:00:05Z",
            &time::format_description::well_known::Rfc3339,
        )
        .unwrap();
        let context = create_test_context(now, Some(sent_at));

        let event = create_test_event(Some("2023-01-01T11:00:00Z".to_string()), None, Some(true));

        let historical_cfg = router::HistoricalConfig::new(false, 1);
        let result = process_single_event(&event, historical_cfg, &context);

        assert!(result.is_ok());
        let processed = result.unwrap();

        let expected = DateTime::parse_from_rfc3339("2023-01-01T11:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        assert_eq!(processed.metadata.computed_timestamp, Some(expected));
    }

    #[test]
    fn test_process_single_event_with_historical_migration_false() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let mut context = create_test_context(now, None);
        context.historical_migration = false;

        let event = create_test_event(Some("2023-01-01T11:00:00Z".to_string()), None, None);

        let historical_cfg = router::HistoricalConfig::new(false, 1);
        let result = process_single_event(&event, historical_cfg, &context);

        assert!(result.is_ok());
        let processed = result.unwrap();

        assert!(!processed.event.historical_migration);
        assert_eq!(processed.metadata.data_type, DataType::AnalyticsMain);
    }

    #[test]
    fn test_process_single_event_with_historical_migration_true() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let mut context = create_test_context(now, None);
        context.historical_migration = true;

        let event = create_test_event(Some("2023-01-01T11:00:00Z".to_string()), None, None);

        let historical_cfg = router::HistoricalConfig::new(false, 1);
        let result = process_single_event(&event, historical_cfg, &context);

        assert!(result.is_ok());
        let processed = result.unwrap();

        assert!(processed.event.historical_migration);
        assert_eq!(processed.metadata.data_type, DataType::AnalyticsHistorical);
    }

    // Mock sink for testing process_events with restrictions
    use crate::config::CaptureMode;
    use crate::event_restrictions::{
        EventRestrictionService, Restriction, RestrictionFilters, RestrictionManager,
        RestrictionScope, RestrictionType,
    };
    use crate::sinks;
    use async_trait::async_trait;
    use std::sync::Mutex;
    use std::time::Duration;

    struct MockSink {
        events: Arc<Mutex<Vec<ProcessedEvent>>>,
    }

    impl MockSink {
        fn new() -> Self {
            Self {
                events: Arc::new(Mutex::new(Vec::new())),
            }
        }

        fn get_events(&self) -> Vec<ProcessedEvent> {
            self.events.lock().unwrap().clone()
        }
    }

    #[async_trait]
    impl sinks::Event for MockSink {
        async fn send(&self, event: ProcessedEvent) -> Result<(), crate::api::CaptureError> {
            self.events.lock().unwrap().push(event);
            Ok(())
        }

        async fn send_batch(
            &self,
            events: Vec<ProcessedEvent>,
        ) -> Result<(), crate::api::CaptureError> {
            self.events.lock().unwrap().extend(events);
            Ok(())
        }
    }

    #[tokio::test]
    async fn test_process_events_drop_event_restriction() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // Create restriction service with DropEvent
        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![Restriction {
                restriction_type: RestrictionType::DropEvent,
                scope: RestrictionScope::AllEvents,
                args: None,
            }],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        // Event should be dropped
        assert_eq!(sink.get_events().len(), 0);
    }

    #[tokio::test]
    async fn test_process_events_force_overflow_restriction() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // Create restriction service with ForceOverflow
        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![Restriction {
                restriction_type: RestrictionType::ForceOverflow,
                scope: RestrictionScope::AllEvents,
                args: None,
            }],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert!(captured[0].metadata.force_overflow);
    }

    #[tokio::test]
    async fn test_process_events_skip_person_processing_restriction() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // Create restriction service with SkipPersonProcessing
        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![Restriction {
                restriction_type: RestrictionType::SkipPersonProcessing,
                scope: RestrictionScope::AllEvents,
                args: None,
            }],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert!(captured[0].metadata.skip_person_processing);
    }

    #[tokio::test]
    async fn test_process_events_redirect_to_dlq_restriction() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // Create restriction service with RedirectToDlq
        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![Restriction {
                restriction_type: RestrictionType::RedirectToDlq,
                scope: RestrictionScope::AllEvents,
                args: None,
            }],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert!(captured[0].metadata.redirect_to_dlq);
    }

    #[tokio::test]
    async fn test_process_events_multiple_restrictions() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // Create restriction service with multiple restrictions
        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![
                Restriction {
                    restriction_type: RestrictionType::ForceOverflow,
                    scope: RestrictionScope::AllEvents,
                    args: None,
                },
                Restriction {
                    restriction_type: RestrictionType::SkipPersonProcessing,
                    scope: RestrictionScope::AllEvents,
                    args: None,
                },
            ],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert!(captured[0].metadata.force_overflow);
        assert!(captured[0].metadata.skip_person_processing);
    }

    #[tokio::test]
    async fn test_process_events_no_restriction_service() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // No restriction service
        let result = process_events(
            sink.clone(),
            dropper,
            None,
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert!(!captured[0].metadata.force_overflow);
        assert!(!captured[0].metadata.skip_person_processing);
        assert!(!captured[0].metadata.redirect_to_dlq);
        assert!(captured[0].metadata.redirect_to_topic.is_none());
    }

    #[tokio::test]
    async fn test_process_events_filtered_restriction() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        // Create restriction that only applies to different event name
        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        let mut filters = RestrictionFilters::default();
        filters.event_names.insert("$pageview".to_string()); // our event is "test_event"
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![Restriction {
                restriction_type: RestrictionType::DropEvent,
                scope: RestrictionScope::Filtered(filters),
                args: None,
            }],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        // Event should NOT be dropped because filter doesn't match
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
    }

    #[tokio::test]
    async fn test_process_events_exception_node_rollout() {
        // Initialize the error tracking sampler at 100% to route all exceptions to Node.
        // Note: OnceLock means this only succeeds once per test binary, so this test
        // assumes no other test initializes the sampler first.
        crate::error_tracking_sampler::init(true, 100.0);

        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event_with_name(
            "$exception",
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();

        // At 100% rollout, the exception should be routed to Node (ExceptionErrorTracking)
        assert_eq!(captured.len(), 1);
        assert_eq!(
            captured[0].metadata.data_type,
            DataType::ExceptionErrorTracking
        );
    }

    #[tokio::test]
    async fn test_process_events_redirect_to_topic_restriction() {
        let now = DateTime::parse_from_rfc3339("2023-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let service = EventRestrictionService::new(CaptureMode::Events, Duration::from_secs(300));
        let mut manager = RestrictionManager::new();
        manager.restrictions.insert(
            "test_token".to_string(),
            vec![Restriction {
                restriction_type: RestrictionType::RedirectToTopic,
                scope: RestrictionScope::AllEvents,
                args: Some(json!({"topic": "custom_events_topic"})),
            }],
        );
        service.update(manager).await;

        let result = process_events(
            sink.clone(),
            dropper,
            Some(service),
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert_eq!(
            captured[0].metadata.redirect_to_topic,
            Some("custom_events_topic".to_string())
        );
    }

    fn create_event_with_heatmap_data() -> RawEvent {
        let mut properties = HashMap::new();
        properties.insert("distinct_id".to_string(), json!("test_user"));
        properties.insert(
            "$heatmap_data".to_string(),
            json!({"https://example.com": [{"x": 100, "y": 200, "target_fixed": false, "type": "click"}]}),
        );
        properties.insert("$viewport_height".to_string(), json!(900));
        properties.insert("$viewport_width".to_string(), json!(1440));
        properties.insert("$session_id".to_string(), json!("session-abc"));
        properties.insert("$current_url".to_string(), json!("https://example.com"));
        properties.insert(
            "other_prop".to_string(),
            json!("should_not_appear_in_redirect"),
        );

        RawEvent {
            uuid: Some(uuid_v7()),
            distinct_id: None,
            event: "$pageview".to_string(),
            properties,
            timestamp: Some("2023-01-01T11:00:00Z".to_string()),
            offset: None,
            set: None,
            set_once: None,
            token: Some("test_token".to_string()),
        }
    }

    #[test]
    fn test_has_heatmap_data_with_heatmap_data_property() {
        let event = create_event_with_heatmap_data();
        assert!(has_heatmap_data(&event));
    }

    #[test]
    fn test_has_heatmap_data_with_scroll_depth_properties() {
        let mut properties = HashMap::new();
        properties.insert("distinct_id".to_string(), json!("test_user"));
        properties.insert("$prev_pageview_pathname".to_string(), json!("/old"));
        properties.insert("$current_url".to_string(), json!("https://example.com/new"));

        let event = RawEvent {
            uuid: Some(uuid_v7()),
            distinct_id: None,
            event: "$pageview".to_string(),
            properties,
            timestamp: None,
            offset: None,
            set: None,
            set_once: None,
            token: Some("test_token".to_string()),
        };
        assert!(has_heatmap_data(&event));
    }

    #[test]
    fn test_has_heatmap_data_without_heatmap_properties() {
        let event = create_test_event(None, None, None);
        assert!(!has_heatmap_data(&event));
    }

    #[test]
    fn test_create_heatmap_redirect_properties_and_metadata() {
        let now = Utc::now();
        let context = create_test_context(now, None);
        let event = create_event_with_heatmap_data();
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let redirect = create_heatmap_redirect(&event, historical_cfg, &context).unwrap();

        assert_eq!(redirect.metadata.data_type, DataType::HeatmapMain);
        assert_eq!(redirect.metadata.event_name, "$$heatmap");
        assert!(redirect.metadata.process_heatmap);
        assert_eq!(redirect.event.event, "$$heatmap");
        assert_ne!(redirect.event.uuid, event.uuid.unwrap());

        let data: RawEvent = serde_json::from_str(&redirect.event.data).unwrap();
        assert!(data.properties.contains_key("$heatmap_data"));
        assert!(data.properties.contains_key("$viewport_height"));
        assert!(data.properties.contains_key("$viewport_width"));
        assert!(data.properties.contains_key("$session_id"));
        assert!(data.properties.contains_key("$current_url"));
        assert!(data.properties.contains_key("distinct_id"));
        assert!(
            !data.properties.contains_key("other_prop"),
            "redirect should only contain heatmap properties"
        );
    }

    #[test]
    fn test_strip_heatmap_data_removes_property_and_sets_flag() {
        let now = Utc::now();
        let context = create_test_context(now, None);
        let event = create_event_with_heatmap_data();
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let mut processed = process_single_event(&event, historical_cfg, &context).unwrap();
        assert!(!processed.metadata.process_heatmap);

        strip_heatmap_data(&mut processed);

        assert!(processed.metadata.process_heatmap);
        let data: RawEvent = serde_json::from_str(&processed.event.data).unwrap();
        assert!(!data.properties.contains_key("$heatmap_data"));
        assert!(
            data.properties.contains_key("$viewport_height"),
            "non-$heatmap_data properties should be preserved"
        );
    }

    #[tokio::test]
    async fn test_process_events_creates_heatmap_redirect() {
        let now = Utc::now();
        let context = create_test_context(now, None);
        let events = vec![create_event_with_heatmap_data()];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let result = process_events(
            sink.clone(),
            dropper,
            None,
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 2, "should produce original + redirect");

        let original = &captured[0];
        assert_eq!(original.event.event, "$pageview");
        assert!(original.metadata.process_heatmap);
        let orig_data: RawEvent = serde_json::from_str(&original.event.data).unwrap();
        assert!(
            !orig_data.properties.contains_key("$heatmap_data"),
            "$heatmap_data should be stripped from original"
        );

        let redirect = &captured[1];
        assert_eq!(redirect.event.event, "$$heatmap");
        assert_eq!(redirect.metadata.data_type, DataType::HeatmapMain);
        assert!(redirect.metadata.process_heatmap);
    }

    #[tokio::test]
    async fn test_process_events_no_redirect_for_heatmap_event() {
        let now = Utc::now();
        let context = create_test_context(now, None);

        let mut event = create_event_with_heatmap_data();
        event.event = "$$heatmap".to_string();
        let events = vec![event];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let result = process_events(
            sink.clone(),
            dropper,
            None,
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(
            captured.len(),
            1,
            "$$heatmap events should not produce a redirect"
        );
        assert_eq!(captured[0].metadata.data_type, DataType::HeatmapMain);
        assert!(!captured[0].metadata.process_heatmap);
    }

    #[tokio::test]
    async fn test_process_events_no_redirect_without_heatmap_data() {
        let now = Utc::now();
        let context = create_test_context(now, None);
        let events = vec![create_test_event(
            Some("2023-01-01T11:00:00Z".to_string()),
            None,
            None,
        )];

        let sink = Arc::new(MockSink::new());
        let dropper = Arc::new(limiters::token_dropper::TokenDropper::default());
        let historical_cfg = router::HistoricalConfig::new(false, 1);

        let result = process_events(
            sink.clone(),
            dropper,
            None,
            historical_cfg,
            &events,
            &context,
        )
        .await;

        assert!(result.is_ok());
        let captured = sink.get_events();
        assert_eq!(captured.len(), 1);
        assert!(!captured[0].metadata.process_heatmap);
    }
}
