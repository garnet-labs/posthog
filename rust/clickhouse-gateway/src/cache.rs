use redis::AsyncCommands;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tracing::warn;

/// A cached query result stored in Redis.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct CachedResult {
    pub data: serde_json::Value,
    pub rows: u64,
    pub bytes_read: u64,
}

/// Redis-backed query result cache.
///
/// The caller controls TTLs — the gateway does not compute them. PostHog's
/// caching logic varies by interval within query type and stays in Python.
///
/// Cache keys follow the pattern: `gw:cache:{team_id}:{sql_hash}` where
/// `sql_hash` is a SHA-256 digest of the SQL text and serialized params.
pub struct QueryCache {
    client: Option<redis::Client>,
    enabled: bool,
}

impl QueryCache {
    /// Create a new cache backed by Redis.
    ///
    /// If `redis_url` is `None` or connection setup fails, the cache is
    /// created in disabled mode — all gets return `None`, all sets are no-ops.
    pub fn new(redis_url: Option<&str>) -> Self {
        match redis_url {
            Some(url) => match redis::Client::open(url) {
                Ok(client) => Self {
                    client: Some(client),
                    enabled: true,
                },
                Err(e) => {
                    warn!(error = %e, "failed to create redis client, cache disabled");
                    Self {
                        client: None,
                        enabled: false,
                    }
                }
            },
            None => Self {
                client: None,
                enabled: false,
            },
        }
    }

    /// Create a cache that is always disabled (for tests or environments
    /// without Redis).
    pub fn disabled() -> Self {
        Self {
            client: None,
            enabled: false,
        }
    }

    /// Look up a cached result.
    ///
    /// Returns `None` when the cache is disabled, the key is missing, or
    /// deserialization fails (treat corrupt entries as a miss).
    pub async fn get(&self, team_id: u64, sql_hash: &str) -> Option<CachedResult> {
        if !self.enabled {
            return None;
        }

        let client = self.client.as_ref()?;
        let key = cache_key(team_id, sql_hash);

        let mut conn = match client.get_multiplexed_async_connection().await {
            Ok(c) => c,
            Err(e) => {
                warn!(error = %e, "redis connection failed on cache get");
                metrics::counter!("gateway_cache_errors").increment(1);
                return None;
            }
        };

        let raw: Option<String> = match conn.get(&key).await {
            Ok(v) => v,
            Err(e) => {
                warn!(error = %e, key = %key, "redis GET failed");
                metrics::counter!("gateway_cache_errors").increment(1);
                return None;
            }
        };

        let raw = raw?;

        match serde_json::from_str::<CachedResult>(&raw) {
            Ok(result) => Some(result),
            Err(e) => {
                warn!(error = %e, key = %key, "failed to deserialize cached result");
                metrics::counter!("gateway_cache_errors").increment(1);
                None
            }
        }
    }

    /// Store a result in the cache with the given TTL.
    ///
    /// Failures are logged but never propagated — a cache write miss should
    /// not fail the request.
    pub async fn set(
        &self,
        team_id: u64,
        sql_hash: &str,
        result: &CachedResult,
        ttl_seconds: u64,
    ) {
        if !self.enabled {
            return;
        }

        let client = match self.client.as_ref() {
            Some(c) => c,
            None => return,
        };

        let key = cache_key(team_id, sql_hash);

        let serialized = match serde_json::to_string(result) {
            Ok(s) => s,
            Err(e) => {
                warn!(error = %e, "failed to serialize cache result");
                metrics::counter!("gateway_cache_errors").increment(1);
                return;
            }
        };

        let mut conn = match client.get_multiplexed_async_connection().await {
            Ok(c) => c,
            Err(e) => {
                warn!(error = %e, "redis connection failed on cache set");
                metrics::counter!("gateway_cache_errors").increment(1);
                return;
            }
        };

        let result: Result<(), redis::RedisError> =
            conn.set_ex(&key, &serialized, ttl_seconds).await;

        if let Err(e) = result {
            warn!(error = %e, key = %key, "redis SET failed");
            metrics::counter!("gateway_cache_errors").increment(1);
        }
    }

    /// Whether the cache is enabled and has a live Redis client.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }
}

/// Build the full Redis key from team_id and sql_hash.
fn cache_key(team_id: u64, sql_hash: &str) -> String {
    format!("gw:cache:{team_id}:{sql_hash}")
}

/// Compute a deterministic cache key from the SQL text and optional params.
///
/// The hash input is `{team_id}:{sql}:{params_json}` where params_json is
/// the compact JSON serialization of the params value, or the empty string
/// if params are `None`.
pub fn compute_cache_key(team_id: u64, sql: &str, params: &Option<serde_json::Value>) -> String {
    let params_str = match params {
        Some(p) => serde_json::to_string(p).unwrap_or_default(),
        None => String::new(),
    };

    let input = format!("{team_id}:{sql}:{params_str}");

    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    let digest = hasher.finalize();

    digest
        .iter()
        .fold(String::with_capacity(64), |mut acc, byte| {
            use std::fmt::Write;
            let _ = write!(acc, "{byte:02x}");
            acc
        })
}

/// Detect whether a SQL statement is a write (mutating) operation.
///
/// Write queries skip cache lookup/store but still get routing, limits,
/// and tagging from the gateway.
pub fn is_write_query(sql: &str) -> bool {
    let trimmed = sql.trim_start().to_uppercase();
    trimmed.starts_with("INSERT")
        || trimmed.starts_with("ALTER")
        || trimmed.starts_with("DROP")
        || trimmed.starts_with("CREATE")
        || trimmed.starts_with("TRUNCATE")
        || trimmed.starts_with("OPTIMIZE")
        || trimmed.starts_with("SYSTEM")
        || trimmed.starts_with("RENAME")
        || trimmed.starts_with("ATTACH")
        || trimmed.starts_with("DETACH")
        || trimmed.starts_with("KILL")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_key_format() {
        let key = cache_key(42, "abc123");
        assert_eq!(key, "gw:cache:42:abc123");
    }

    #[test]
    fn test_cache_key_deterministic() {
        let sql = "SELECT count() FROM events WHERE team_id = {team_id:UInt64}";
        let params = Some(serde_json::json!({"team_id": 42}));

        let key1 = compute_cache_key(42, sql, &params);
        let key2 = compute_cache_key(42, sql, &params);

        assert_eq!(key1, key2);
        // SHA-256 hex output is always 64 chars
        assert_eq!(key1.len(), 64);
    }

    #[test]
    fn test_cache_key_different_params() {
        let sql = "SELECT count() FROM events WHERE team_id = {team_id:UInt64}";
        let params_a = Some(serde_json::json!({"team_id": 42}));
        let params_b = Some(serde_json::json!({"team_id": 99}));

        let key_a = compute_cache_key(42, sql, &params_a);
        let key_b = compute_cache_key(42, sql, &params_b);

        assert_ne!(key_a, key_b);
    }

    #[test]
    fn test_cache_key_different_team_id() {
        let sql = "SELECT 1";
        let params = None;

        let key_a = compute_cache_key(1, sql, &params);
        let key_b = compute_cache_key(2, sql, &params);

        assert_ne!(key_a, key_b);
    }

    #[test]
    fn test_cache_key_none_params_vs_empty_object() {
        let sql = "SELECT 1";

        let key_none = compute_cache_key(1, sql, &None);
        let key_empty = compute_cache_key(1, sql, &Some(serde_json::json!({})));

        // None and {} should produce different keys
        assert_ne!(key_none, key_empty);
    }

    #[test]
    fn test_is_write_query_insert() {
        assert!(is_write_query("INSERT INTO events VALUES (1, 2, 3)"));
    }

    #[test]
    fn test_is_write_query_select_is_not_write() {
        assert!(!is_write_query("SELECT count() FROM events"));
    }

    #[test]
    fn test_is_write_query_case_insensitive() {
        assert!(is_write_query("insert into events VALUES (1)"));
        assert!(is_write_query("Insert Into events VALUES (1)"));
        assert!(is_write_query("  INSERT INTO events VALUES (1)"));
    }

    #[test]
    fn test_is_write_query_alter() {
        assert!(is_write_query("ALTER TABLE events ADD COLUMN foo String"));
    }

    #[test]
    fn test_is_write_query_drop() {
        assert!(is_write_query("DROP TABLE events"));
    }

    #[test]
    fn test_is_write_query_create() {
        assert!(is_write_query("CREATE TABLE foo (id UInt64) ENGINE = Memory"));
    }

    #[test]
    fn test_is_write_query_truncate() {
        assert!(is_write_query("TRUNCATE TABLE events"));
    }

    #[test]
    fn test_is_write_query_optimize() {
        assert!(is_write_query("OPTIMIZE TABLE events FINAL"));
    }

    #[test]
    fn test_is_write_query_system() {
        assert!(is_write_query("SYSTEM RELOAD DICTIONARIES"));
    }

    #[test]
    fn test_is_write_query_with_leading_whitespace() {
        assert!(is_write_query("   DROP TABLE events"));
        assert!(!is_write_query("   SELECT 1"));
    }

    #[test]
    fn test_disabled_cache_returns_none() {
        let cache = QueryCache::disabled();
        assert!(!cache.is_enabled());
    }

    #[test]
    fn test_cached_result_serialization_roundtrip() {
        let result = CachedResult {
            data: serde_json::json!([{"count": 42}]),
            rows: 1,
            bytes_read: 128,
        };

        let json = serde_json::to_string(&result).unwrap();
        let deserialized: CachedResult = serde_json::from_str(&json).unwrap();

        assert_eq!(deserialized.rows, 1);
        assert_eq!(deserialized.bytes_read, 128);
        assert_eq!(deserialized.data, serde_json::json!([{"count": 42}]));
    }
}
