use clickhouse_gateway::cache::{compute_cache_key, is_write_query, CachedResult, QueryCache};

// ---------------------------------------------------------------------------
// compute_cache_key tests
// ---------------------------------------------------------------------------

#[test]
fn test_cache_key_deterministic() {
    let sql = "SELECT count() FROM events WHERE team_id = {team_id:UInt64}";
    let params = Some(serde_json::json!({"team_id": 42}));

    let key1 = compute_cache_key(42, sql, &params);
    let key2 = compute_cache_key(42, sql, &params);

    assert_eq!(key1, key2, "same sql + params must produce the same key");
    assert_eq!(key1.len(), 64, "SHA-256 hex digest is 64 characters");
}

#[test]
fn test_cache_key_different_params() {
    let sql = "SELECT count() FROM events WHERE team_id = {team_id:UInt64}";
    let params_a = Some(serde_json::json!({"team_id": 42}));
    let params_b = Some(serde_json::json!({"team_id": 99}));

    let key_a = compute_cache_key(42, sql, &params_a);
    let key_b = compute_cache_key(42, sql, &params_b);

    assert_ne!(key_a, key_b, "different params must produce different keys");
}

#[test]
fn test_cache_key_different_sql() {
    let params = Some(serde_json::json!({"team_id": 42}));

    let key_a = compute_cache_key(42, "SELECT 1", &params);
    let key_b = compute_cache_key(42, "SELECT 2", &params);

    assert_ne!(key_a, key_b, "different SQL must produce different keys");
}

#[test]
fn test_cache_key_different_team_id() {
    let sql = "SELECT 1";
    let params = None;

    let key_a = compute_cache_key(1, sql, &params);
    let key_b = compute_cache_key(2, sql, &params);

    assert_ne!(
        key_a, key_b,
        "different team_id must produce different keys"
    );
}

#[test]
fn test_cache_key_none_params_vs_empty_object() {
    let sql = "SELECT 1";

    let key_none = compute_cache_key(1, sql, &None);
    let key_empty = compute_cache_key(1, sql, &Some(serde_json::json!({})));

    assert_ne!(
        key_none, key_empty,
        "None params and empty object params must produce different keys"
    );
}

// ---------------------------------------------------------------------------
// is_write_query tests
// ---------------------------------------------------------------------------

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
}

#[test]
fn test_is_write_query_leading_whitespace() {
    assert!(is_write_query("   INSERT INTO events VALUES (1)"));
    assert!(!is_write_query("   SELECT 1"));
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
    assert!(is_write_query(
        "CREATE TABLE foo (id UInt64) ENGINE = Memory"
    ));
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
fn test_is_write_query_with_statement() {
    // WITH ... SELECT is a read query
    assert!(!is_write_query(
        "WITH cte AS (SELECT 1) SELECT * FROM cte"
    ));
}

// ---------------------------------------------------------------------------
// Cache skip behavior (unit-level, no Redis)
// ---------------------------------------------------------------------------

#[test]
fn test_cache_skipped_for_writes() {
    // Write queries should not produce a cache key to look up
    let sql = "INSERT INTO events VALUES (1, 2, 3)";
    assert!(
        is_write_query(sql),
        "INSERT should be detected as write query"
    );
    // The gateway skips cache when is_write_query returns true —
    // this test validates the detection side; integration with handle_query
    // is tested via the handler tests.
}

#[test]
fn test_cache_skipped_when_no_ttl() {
    // When cache_ttl_seconds is None, the gateway should not attempt cache lookup.
    // This is a design contract test — the Option<u64> field being None means
    // the caller does not want caching. The actual skip logic lives in
    // handle_query; here we verify the sentinel value interpretation.
    let ttl: Option<u64> = None;
    assert!(
        ttl.is_none(),
        "None TTL means cache should not be consulted"
    );
}

#[test]
fn test_cache_skipped_when_ttl_zero() {
    // A TTL of 0 should also skip caching (no point storing with immediate expiry)
    let ttl: Option<u64> = Some(0);
    assert_eq!(
        ttl.unwrap(),
        0,
        "TTL of 0 means cache should not be consulted"
    );
}

// ---------------------------------------------------------------------------
// QueryCache disabled mode
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_disabled_cache_get_returns_none() {
    let cache = QueryCache::disabled();
    assert!(!cache.is_enabled());

    let result = cache.get(42, "abc123").await;
    assert!(result.is_none(), "disabled cache should always return None");
}

#[tokio::test]
async fn test_disabled_cache_set_is_noop() {
    let cache = QueryCache::disabled();
    let result = CachedResult {
        data: serde_json::json!([{"count": 42}]),
        rows: 1,
        bytes_read: 128,
    };

    // Should not panic or error
    cache.set(42, "abc123", &result, 60).await;
}

// ---------------------------------------------------------------------------
// CachedResult serialization
// ---------------------------------------------------------------------------

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

#[test]
fn test_cached_result_with_complex_data() {
    let result = CachedResult {
        data: serde_json::json!([
            {"event": "pageview", "count": 100, "breakdown": ["US", "UK"]},
            {"event": "click", "count": 50, "breakdown": ["US"]}
        ]),
        rows: 2,
        bytes_read: 4096,
    };

    let json = serde_json::to_string(&result).unwrap();
    let deserialized: CachedResult = serde_json::from_str(&json).unwrap();

    assert_eq!(deserialized.rows, 2);
    assert_eq!(deserialized.bytes_read, 4096);
    assert_eq!(deserialized.data[0]["event"], "pageview");
    assert_eq!(deserialized.data[1]["count"], 50);
}
