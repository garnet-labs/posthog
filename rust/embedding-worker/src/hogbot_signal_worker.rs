use common_kafka::{
    config::{ConsumerConfig, KafkaConfig},
    kafka_consumer::SingleTopicConsumer,
};
use std::time::Duration;
use tracing::{error, info, warn};

const KAFKA_TOPIC: &str = "hogbot-signals";
const KAFKA_GROUP: &str = "hogbot-signal-worker";
const DJANGO_BASE_URL: &str = "http://localhost:8000";
const INTERNAL_API_SECRET: &str = "posthog123";
const BUSY_RETRY_DELAY: Duration = Duration::from_secs(30);
const ERROR_RETRY_DELAY: Duration = Duration::from_secs(5);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(600);

pub async fn run(kafka_config: KafkaConfig) {
    info!(
        topic = KAFKA_TOPIC,
        group = KAFKA_GROUP,
        django_url = DJANGO_BASE_URL,
        "Hogbot signal worker initializing"
    );

    let consumer_config = ConsumerConfig {
        kafka_consumer_group: KAFKA_GROUP.to_string(),
        kafka_consumer_topic: KAFKA_TOPIC.to_string(),
        kafka_consumer_offset_reset: "latest".to_string(),
        kafka_consumer_auto_commit: false,
        kafka_consumer_auto_commit_interval_ms: 5000,
    };

    let consumer = match SingleTopicConsumer::new(kafka_config, consumer_config) {
        Ok(c) => {
            info!(
                "Kafka consumer created successfully for topic '{}'",
                KAFKA_TOPIC
            );
            c
        }
        Err(e) => {
            error!("Failed to create hogbot signal consumer: {:?}", e);
            return;
        }
    };

    let http_client = reqwest::Client::new();

    info!(
        topic = KAFKA_TOPIC,
        group = KAFKA_GROUP,
        "Hogbot signal worker ready, waiting for messages"
    );

    let mut message_count: u64 = 0;

    loop {
        info!(
            "Waiting for next message from Kafka topic '{}'...",
            KAFKA_TOPIC
        );

        let (signal, offset): (serde_json::Value, _) = match consumer.json_recv().await {
            Ok(msg) => {
                message_count += 1;
                info!(message_count = message_count, "Received message from Kafka");
                msg
            }
            Err(e) => {
                error!("Error receiving hogbot signal: {:?}", e);
                info!(
                    "Sleeping {}s before retrying recv",
                    ERROR_RETRY_DELAY.as_secs()
                );
                tokio::time::sleep(ERROR_RETRY_DELAY).await;
                continue;
            }
        };

        let team_id = match signal.get("team_id").and_then(|v| v.as_i64()) {
            Some(id) => id,
            None => {
                warn!(signal = %signal, "Hogbot signal missing team_id, skipping and committing offset");
                if let Err(e) = offset.store() {
                    error!(error = %e, "Failed to store offset for malformed signal");
                }
                continue;
            }
        };
        let signal_id = signal
            .get("signal_id")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string();
        let prompt = serde_json::to_string(&signal).unwrap_or_default();

        info!(
            team_id = team_id,
            signal_id = %signal_id,
            prompt_len = prompt.len(),
            "Processing hogbot signal, will POST to Django internal endpoint"
        );

        let mut attempt: u64 = 0;

        loop {
            attempt += 1;
            let url = format!(
                "{}/api/projects/{}/internal/hogbot/research",
                DJANGO_BASE_URL, team_id
            );

            info!(
                team_id = team_id,
                signal_id = %signal_id,
                attempt = attempt,
                url = %url,
                "Sending research request to Django"
            );

            let response = match http_client
                .post(&url)
                .header("X-Internal-Api-Secret", INTERNAL_API_SECRET)
                .header("Content-Type", "application/json")
                .json(&serde_json::json!({
                    "signal_id": signal_id,
                    "prompt": prompt,
                }))
                .timeout(REQUEST_TIMEOUT)
                .send()
                .await
            {
                Ok(resp) => resp,
                Err(e) => {
                    if e.is_timeout() {
                        error!(
                            team_id = team_id,
                            signal_id = %signal_id,
                            attempt = attempt,
                            timeout_secs = REQUEST_TIMEOUT.as_secs(),
                            "Request to Django timed out after {}s, sleeping {}s before retry",
                            REQUEST_TIMEOUT.as_secs(),
                            ERROR_RETRY_DELAY.as_secs()
                        );
                    } else if e.is_connect() {
                        error!(
                            team_id = team_id,
                            signal_id = %signal_id,
                            attempt = attempt,
                            url = %url,
                            "Connection refused to Django at {}, sleeping {}s before retry. Is the Django server running?",
                            DJANGO_BASE_URL,
                            ERROR_RETRY_DELAY.as_secs()
                        );
                    } else {
                        error!(
                            team_id = team_id,
                            signal_id = %signal_id,
                            attempt = attempt,
                            error = %e,
                            error_debug = ?e,
                            "HTTP request to Django failed: {}, sleeping {}s before retry",
                            e,
                            ERROR_RETRY_DELAY.as_secs()
                        );
                    }
                    tokio::time::sleep(ERROR_RETRY_DELAY).await;
                    continue;
                }
            };

            let status = response.status().as_u16();

            info!(
                team_id = team_id,
                signal_id = %signal_id,
                status = status,
                attempt = attempt,
                "Received response from Django"
            );

            if (200..300).contains(&status) {
                info!(
                    team_id = team_id,
                    signal_id = %signal_id,
                    attempt = attempt,
                    "Research request accepted ({}), committing Kafka offset", status
                );
                if let Err(e) = offset.store() {
                    error!(
                        team_id = team_id,
                        signal_id = %signal_id,
                        error = %e,
                        "Failed to store Kafka offset"
                    );
                } else {
                    info!(
                        team_id = team_id,
                        signal_id = %signal_id,
                        "Kafka offset committed successfully"
                    );
                }
                break;
            } else if status == 418 {
                info!(
                    team_id = team_id,
                    signal_id = %signal_id,
                    attempt = attempt,
                    "Researcher busy (418), sleeping {}s before retry", BUSY_RETRY_DELAY.as_secs()
                );
                tokio::time::sleep(BUSY_RETRY_DELAY).await;
            } else {
                let body = response.text().await.unwrap_or_default();
                if status >= 500 {
                    error!(
                        team_id = team_id,
                        signal_id = %signal_id,
                        status = status,
                        attempt = attempt,
                        body = %body,
                        "Django returned server error ({}), sleeping {}s before retry",
                        status,
                        ERROR_RETRY_DELAY.as_secs()
                    );
                } else if status >= 400 {
                    error!(
                        team_id = team_id,
                        signal_id = %signal_id,
                        status = status,
                        attempt = attempt,
                        body = %body,
                        "Django returned client error ({}), sleeping {}s before retry. This may indicate a bad signal payload.",
                        status,
                        ERROR_RETRY_DELAY.as_secs()
                    );
                } else {
                    warn!(
                        team_id = team_id,
                        signal_id = %signal_id,
                        status = status,
                        attempt = attempt,
                        body = %body,
                        "Django returned unexpected status ({}), sleeping {}s before retry",
                        status,
                        ERROR_RETRY_DELAY.as_secs()
                    );
                }
                tokio::time::sleep(ERROR_RETRY_DELAY).await;
            }
        }
    }
}
