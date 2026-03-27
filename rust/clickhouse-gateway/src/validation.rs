use crate::cache;
use crate::error::GatewayError;
use crate::query::QueryRequest;

/// Strip leading SQL block comments (`/* ... */`) and line comments (`-- ...`)
/// so that the actual SQL keyword is at the start. This prevents bypass via
/// `/* comment */ INSERT INTO ...`.
fn strip_leading_comments(sql: &str) -> &str {
    let mut s = sql.trim_start();
    loop {
        if s.starts_with("/*") {
            match s.find("*/") {
                Some(end) => {
                    s = s[end + 2..].trim_start();
                }
                None => break, // unterminated — let CH reject it
            }
        } else if s.starts_with("--") {
            match s.find('\n') {
                Some(nl) => {
                    s = s[nl + 1..].trim_start();
                }
                None => break, // entire string is a comment
            }
        } else {
            break;
        }
    }
    s
}

/// Validates that a query marked as read_only does not contain write operations.
///
/// Strips leading SQL comments before checking, and delegates to the shared
/// `cache::is_write_query()` detector to avoid duplicate pattern lists.
pub fn validate_readonly(req: &QueryRequest) -> Result<(), GatewayError> {
    if !req.read_only {
        return Ok(());
    }

    let stripped = strip_leading_comments(&req.sql);
    if cache::is_write_query(stripped) {
        return Err(GatewayError::WriteNotAllowed);
    }

    Ok(())
}

/// Settings keys that callers are allowed to forward to ClickHouse.
/// Everything not on this list is silently dropped to prevent injection
/// of dangerous params like `user`, `password`, `readonly`, `session_id`.
const ALLOWED_SETTINGS: &[&str] = &[
    "max_execution_time",
    "max_memory_usage",
    "max_rows_to_read",
    "max_bytes_to_read",
    "max_result_rows",
    "max_result_bytes",
    "max_threads",
    "max_block_size",
    "output_format_json_quote_64bit_integers",
    "date_time_output_format",
    "use_query_cache",
    "query_cache_ttl",
    "extremes",
    "max_ast_elements",
    "max_expanded_ast_elements",
    "max_query_size",
    "timeout_before_checking_execution_speed",
    "join_use_nulls",
    "transform_null_in",
    "allow_experimental_analyzer",
];

/// Filter caller-supplied settings to the allowlist. Returns a new object
/// containing only permitted keys. Unknown keys are logged and dropped.
pub fn filter_settings(settings: &serde_json::Value) -> serde_json::Value {
    let obj = match settings.as_object() {
        Some(o) => o,
        None => return serde_json::json!({}),
    };

    let mut filtered = serde_json::Map::new();
    for (k, v) in obj {
        if ALLOWED_SETTINGS.contains(&k.as_str()) {
            filtered.insert(k.clone(), v.clone());
        } else {
            tracing::warn!(key = %k, "dropping disallowed settings key");
        }
    }
    serde_json::Value::Object(filtered)
}

/// Enforces the max_execution_time ceiling from server config.
/// Callers cannot set a value higher than the workload's configured maximum.
pub fn enforce_settings_ceiling(settings: &mut serde_json::Value, config_max_execution_time: u32) {
    if let Some(obj) = settings.as_object_mut() {
        if let Some(met) = obj.get("max_execution_time") {
            if let Some(requested) = met.as_u64() {
                if requested > config_max_execution_time as u64 {
                    obj.insert(
                        "max_execution_time".to_string(),
                        serde_json::Value::Number(config_max_execution_time.into()),
                    );
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_readonly_allows_select() {
        let req = QueryRequest {
            sql: "SELECT count() FROM events".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: true,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_ok());
    }

    #[test]
    fn test_validate_readonly_rejects_insert() {
        let req = QueryRequest {
            sql: "INSERT INTO events VALUES (1, 2, 3)".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: true,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_err());
    }

    #[test]
    fn test_validate_readonly_allows_insert_when_not_readonly() {
        let req = QueryRequest {
            sql: "INSERT INTO events VALUES (1, 2, 3)".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: false,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_ok());
    }

    #[test]
    fn test_validate_readonly_rejects_drop() {
        let req = QueryRequest {
            sql: "DROP TABLE events".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: true,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_err());
    }

    #[test]
    fn test_validate_readonly_rejects_insert_with_block_comment() {
        let req = QueryRequest {
            sql: "/* my comment */ INSERT INTO events VALUES (1, 2, 3)".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: true,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_err());
    }

    #[test]
    fn test_validate_readonly_rejects_insert_with_line_comment() {
        let req = QueryRequest {
            sql: "-- comment\nINSERT INTO events VALUES (1, 2, 3)".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: true,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_err());
    }

    #[test]
    fn test_validate_readonly_rejects_nested_comments() {
        let req = QueryRequest {
            sql: "/* a */ /* b */ DROP TABLE events".to_string(),
            params: None,
            workload: "ONLINE".to_string(),
            ch_user: "APP".to_string(),
            team_id: 1,
            org_id: None,
            read_only: true,
            priority: None,
            cache_ttl_seconds: None,
            settings: None,
            query_tags: None,
            query_id: None,
            columnar: None,
        };
        assert!(validate_readonly(&req).is_err());
    }

    #[test]
    fn test_strip_leading_comments() {
        assert_eq!(strip_leading_comments("SELECT 1"), "SELECT 1");
        assert_eq!(strip_leading_comments("/* comment */ SELECT 1"), "SELECT 1");
        assert_eq!(strip_leading_comments("-- comment\nSELECT 1"), "SELECT 1");
        assert_eq!(
            strip_leading_comments("/* a */ /* b */ SELECT 1"),
            "SELECT 1"
        );
        assert_eq!(
            strip_leading_comments("  /* padded */  SELECT 1"),
            "SELECT 1"
        );
    }

    #[test]
    fn test_filter_settings_allows_safe_keys() {
        let settings = serde_json::json!({
            "max_execution_time": 30,
            "max_threads": 4,
        });
        let filtered = filter_settings(&settings);
        assert_eq!(filtered["max_execution_time"], 30);
        assert_eq!(filtered["max_threads"], 4);
    }

    #[test]
    fn test_filter_settings_drops_dangerous_keys() {
        let settings = serde_json::json!({
            "max_execution_time": 30,
            "user": "default",
            "password": "secret",
            "readonly": 0,
            "session_id": "hijack",
        });
        let filtered = filter_settings(&settings);
        assert_eq!(filtered["max_execution_time"], 30);
        assert!(filtered.get("user").is_none());
        assert!(filtered.get("password").is_none());
        assert!(filtered.get("readonly").is_none());
        assert!(filtered.get("session_id").is_none());
    }

    #[test]
    fn test_filter_settings_non_object_returns_empty() {
        let settings = serde_json::json!("not an object");
        let filtered = filter_settings(&settings);
        assert_eq!(filtered, serde_json::json!({}));
    }

    #[test]
    fn test_enforce_settings_ceiling_caps_value() {
        let mut settings = serde_json::json!({
            "max_execution_time": 999
        });
        enforce_settings_ceiling(&mut settings, 30);
        assert_eq!(settings["max_execution_time"], 30);
    }

    #[test]
    fn test_enforce_settings_ceiling_allows_lower() {
        let mut settings = serde_json::json!({
            "max_execution_time": 10
        });
        enforce_settings_ceiling(&mut settings, 30);
        assert_eq!(settings["max_execution_time"], 10);
    }
}
