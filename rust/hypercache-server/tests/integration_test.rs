/// Integration tests for hypercache-server.
///
/// These tests require Docker services running (Redis + MinIO/S3):
///   docker compose -f docker-compose.dev.yml up redis7 objectstorage -d
///
/// The tests write real data to Redis and S3, start the actual HTTP server,
/// and verify the full request flow including cache fallback behavior.
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use common_hypercache::{HyperCacheConfig, KeyType};
use common_redis::{Client as RedisClientTrait, RedisClient};
use serde_json::{json, Value};
use tokio::net::TcpListener;
use tokio::sync::Notify;

use hypercache_server::config::Config;

// -- Test infrastructure --

struct TestServer {
    addr: SocketAddr,
    shutdown: Arc<Notify>,
    redis: RedisClient,
    s3: aws_sdk_s3::Client,
    s3_bucket: String,
}

impl TestServer {
    async fn start() -> anyhow::Result<Self> {
        // AWS creds for local MinIO
        std::env::set_var("AWS_ACCESS_KEY_ID", "object_storage_root_user");
        std::env::set_var("AWS_SECRET_ACCESS_KEY", "object_storage_root_password");

        let config = Config {
            address: "127.0.0.1:0".parse().unwrap(),
            redis_url: "redis://localhost:6379/".to_string(),
            redis_reader_url: String::new(),
            redis_timeout_ms: 1000,
            object_storage_region: "us-east-1".to_string(),
            object_storage_bucket: "posthog".to_string(),
            object_storage_endpoint: "http://localhost:19000".to_string(),
            enable_metrics: hypercache_server::config::FlexBool(false),
            debug: hypercache_server::config::FlexBool(true),
            max_concurrency: 100,
        };

        let listener = TcpListener::bind("127.0.0.1:0").await?;
        let addr = listener.local_addr()?;
        let notify = Arc::new(Notify::new());
        let shutdown = notify.clone();

        let config_clone = config.clone();
        tokio::spawn(async move {
            hypercache_server::server::serve(config_clone, listener, async move {
                notify.notified().await
            })
            .await
        });

        // Wait for server to start
        tokio::time::sleep(Duration::from_millis(200)).await;

        // Create Redis client for test data setup
        let redis = RedisClient::with_config(
            config.redis_url.clone(),
            common_redis::CompressionConfig::disabled(),
            common_redis::RedisValueFormat::default(),
            Some(Duration::from_millis(1000)),
            Some(Duration::from_millis(5000)),
        )
        .await?;

        // Create S3 client for test data setup
        let aws_config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new("us-east-1"))
            .endpoint_url("http://localhost:19000")
            .load()
            .await;

        let s3 = aws_sdk_s3::Client::from_conf(
            aws_sdk_s3::config::Builder::from(&aws_config)
                .force_path_style(true)
                .build(),
        );

        Ok(TestServer {
            addr,
            shutdown,
            redis,
            s3,
            s3_bucket: config.object_storage_bucket,
        })
    }

    fn url(&self, path: &str) -> String {
        format!("http://{}{}", self.addr, path)
    }

    /// Write data to Redis using pickle format (matching Django's HyperCache).
    async fn write_to_redis(
        &self,
        namespace: &str,
        value: &str,
        token: &str,
        data: &Value,
    ) -> anyhow::Result<()> {
        let mut config = HyperCacheConfig::new(
            namespace.to_string(),
            value.to_string(),
            "us-east-1".to_string(),
            self.s3_bucket.clone(),
        );
        config.token_based = true;
        let key = config.get_redis_cache_key(&KeyType::string(token));
        let json_str = serde_json::to_string(data)?;
        self.redis.set(key, json_str).await?;
        Ok(())
    }

    /// Write data to S3 (matching Django's HyperCache).
    async fn write_to_s3(
        &self,
        namespace: &str,
        value: &str,
        token: &str,
        data: &Value,
    ) -> anyhow::Result<()> {
        let mut config = HyperCacheConfig::new(
            namespace.to_string(),
            value.to_string(),
            "us-east-1".to_string(),
            self.s3_bucket.clone(),
        );
        config.token_based = true;
        let key = config.get_s3_cache_key(&KeyType::string(token));
        let json_str = serde_json::to_string(data)?;
        self.s3
            .put_object()
            .bucket(&self.s3_bucket)
            .key(&key)
            .body(json_str.into_bytes().into())
            .send()
            .await?;
        Ok(())
    }

    /// Clear data from Redis for a given cache key.
    async fn clear_redis(&self, namespace: &str, value: &str, token: &str) -> anyhow::Result<()> {
        let mut config = HyperCacheConfig::new(
            namespace.to_string(),
            value.to_string(),
            "us-east-1".to_string(),
            self.s3_bucket.clone(),
        );
        config.token_based = true;
        let key = config.get_redis_cache_key(&KeyType::string(token));
        drop(self.redis.del(key).await);
        Ok(())
    }

    /// Clear data from S3 for a given cache key.
    async fn clear_s3(&self, namespace: &str, value: &str, token: &str) -> anyhow::Result<()> {
        let mut config = HyperCacheConfig::new(
            namespace.to_string(),
            value.to_string(),
            "us-east-1".to_string(),
            self.s3_bucket.clone(),
        );
        config.token_based = true;
        let key = config.get_s3_cache_key(&KeyType::string(token));
        drop(
            self.s3
                .delete_object()
                .bucket(&self.s3_bucket)
                .key(&key)
                .send()
                .await,
        );
        Ok(())
    }
}

impl Drop for TestServer {
    fn drop(&mut self) {
        self.shutdown.notify_one();
    }
}

// -- Surveys integration tests --

#[tokio::test]
async fn test_surveys_redis_hit() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_surveys_redis";

    let survey_data = json!({
        "surveys": [{"id": "s1", "name": "NPS Survey", "type": "popover"}],
        "survey_config": {"appearance": {"theme": "light"}}
    });

    server
        .write_to_redis("surveys", "surveys.json", token, &survey_data)
        .await?;

    let resp = reqwest::get(server.url(&format!("/api/surveys?token={token}"))).await?;
    assert_eq!(resp.status(), 200);

    let body: Value = resp.json().await?;
    assert_eq!(body["surveys"][0]["name"], "NPS Survey");
    assert_eq!(body["survey_config"]["appearance"]["theme"], "light");

    // Cleanup
    server.clear_redis("surveys", "surveys.json", token).await?;
    Ok(())
}

#[tokio::test]
async fn test_surveys_s3_fallback() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_surveys_s3";

    let survey_data = json!({
        "surveys": [{"id": "s2", "name": "S3 Fallback Survey"}],
        "survey_config": null
    });

    // Write to S3 only (not Redis) to test fallback
    server
        .write_to_s3("surveys", "surveys.json", token, &survey_data)
        .await?;
    server.clear_redis("surveys", "surveys.json", token).await?;

    let resp = reqwest::get(server.url(&format!("/api/surveys?token={token}"))).await?;
    assert_eq!(resp.status(), 200);

    let body: Value = resp.json().await?;
    assert_eq!(body["surveys"][0]["name"], "S3 Fallback Survey");

    // Cleanup
    server.clear_s3("surveys", "surveys.json", token).await?;
    Ok(())
}

#[tokio::test]
async fn test_surveys_complete_miss_returns_empty() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_surveys_miss";

    // Ensure nothing is cached
    server.clear_redis("surveys", "surveys.json", token).await?;
    server.clear_s3("surveys", "surveys.json", token).await?;

    let resp = reqwest::get(server.url(&format!("/api/surveys?token={token}"))).await?;
    assert_eq!(resp.status(), 200);

    let body: Value = resp.json().await?;
    assert_eq!(body["surveys"], json!([]));
    assert_eq!(body["survey_config"], json!(null));

    Ok(())
}

#[tokio::test]
async fn test_surveys_missing_token_returns_401() -> anyhow::Result<()> {
    let server = TestServer::start().await?;

    let resp = reqwest::get(server.url("/api/surveys")).await?;
    assert_eq!(resp.status(), 401);

    Ok(())
}

// -- Remote config integration tests --

#[tokio::test]
async fn test_config_redis_hit() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_config_redis";

    let config_data = json!({
        "sessionRecording": {"endpoint": "/s/", "consoleLogRecordingEnabled": true},
        "heatmaps": true,
        "surveys": false,
        "token": token
    });

    server
        .write_to_redis("array", "config.json", token, &config_data)
        .await?;

    let resp = reqwest::get(server.url(&format!("/array/{token}/config"))).await?;
    assert_eq!(resp.status(), 200);
    assert_eq!(
        resp.headers()
            .get("cache-control")
            .unwrap()
            .to_str()
            .unwrap(),
        "public, max-age=300"
    );

    let body: Value = resp.json().await?;
    assert_eq!(body["heatmaps"], json!(true));
    assert_eq!(body["token"], json!(token));
    // sessionRecording should be preserved (no domain restriction)
    assert!(body["sessionRecording"].is_object());

    server.clear_redis("array", "config.json", token).await?;
    Ok(())
}

#[tokio::test]
async fn test_config_s3_fallback() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_config_s3";

    let config_data = json!({
        "heatmaps": true,
        "token": token
    });

    // S3 only
    server
        .write_to_s3("array", "config.json", token, &config_data)
        .await?;
    server.clear_redis("array", "config.json", token).await?;

    let resp = reqwest::get(server.url(&format!("/array/{token}/config"))).await?;
    assert_eq!(resp.status(), 200);

    let body: Value = resp.json().await?;
    assert_eq!(body["heatmaps"], json!(true));

    server.clear_s3("array", "config.json", token).await?;
    Ok(())
}

#[tokio::test]
async fn test_config_complete_miss_returns_404() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_config_miss";

    server.clear_redis("array", "config.json", token).await?;
    server.clear_s3("array", "config.json", token).await?;

    let resp = reqwest::get(server.url(&format!("/array/{token}/config"))).await?;
    assert_eq!(resp.status(), 404);

    Ok(())
}

#[tokio::test]
async fn test_config_invalid_token_returns_400() -> anyhow::Result<()> {
    let server = TestServer::start().await?;

    let resp = reqwest::get(server.url("/array/token.with.dots/config")).await?;
    assert_eq!(resp.status(), 400);

    Ok(())
}

#[tokio::test]
async fn test_config_js_returns_javascript() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_configjs";

    let config_data = json!({
        "heatmaps": true,
        "siteAppsJS": ["function() { return 42; }"],
        "siteApps": [{"id": 1, "url": "/app.js"}]
    });

    server
        .write_to_redis("array", "config.json", token, &config_data)
        .await?;

    let resp = reqwest::get(server.url(&format!("/array/{token}/config.js"))).await?;
    assert_eq!(resp.status(), 200);
    assert_eq!(
        resp.headers()
            .get("content-type")
            .unwrap()
            .to_str()
            .unwrap(),
        "application/javascript"
    );

    let body = resp.text().await?;
    assert!(body.contains("window._POSTHOG_REMOTE_CONFIG"));
    assert!(body.contains(token));
    assert!(body.contains("siteApps: [function() { return 42; }]"));
    // siteAppsJS should NOT appear in the config JSON portion
    assert!(!body.contains("\"siteAppsJS\""));

    server.clear_redis("array", "config.json", token).await?;
    Ok(())
}

#[tokio::test]
async fn test_config_sanitizes_session_recording_domains() -> anyhow::Result<()> {
    let server = TestServer::start().await?;
    let token = "phc_inttest_sanitize";

    let config_data = json!({
        "sessionRecording": {
            "endpoint": "/s/",
            "domains": ["https://allowed.example.com"]
        },
        "heatmaps": true
    });

    server
        .write_to_redis("array", "config.json", token, &config_data)
        .await?;

    // Request without Origin header — domain check fails, recording disabled
    let resp = reqwest::get(server.url(&format!("/array/{token}/config"))).await?;
    assert_eq!(resp.status(), 200);

    let body: Value = resp.json().await?;
    // sessionRecording should be set to false (no Origin = not permitted)
    assert_eq!(body["sessionRecording"], json!(false));
    // domains field should be stripped either way
    assert!(body.get("domains").is_none());

    server.clear_redis("array", "config.json", token).await?;
    Ok(())
}

#[tokio::test]
async fn test_health_endpoints() -> anyhow::Result<()> {
    let server = TestServer::start().await?;

    let resp = reqwest::get(server.url("/")).await?;
    assert_eq!(resp.status(), 200);
    assert_eq!(resp.text().await?, "hypercache-server");

    let resp = reqwest::get(server.url("/_readiness")).await?;
    assert_eq!(resp.status(), 200);

    Ok(())
}
