use common_hypercache::{HyperCacheReader, KeyType, HYPER_CACHE_EMPTY_VALUE};
use serde_json::Value;
use std::sync::Arc;

/// Read cached data from HyperCache as raw JSON.
///
/// Returns the data blob as-is without interpreting its structure.
///
/// HyperCache handles infrastructure resilience internally (Redis → S3 fallback),
/// converting operational errors to cache misses. This function only distinguishes:
/// - `Some(value)` - Cache hit with JSON data
/// - `None` - Cache miss (key not found, or infrastructure error handled by HyperCache)
pub async fn get_cached_data(reader: &Arc<HyperCacheReader>, key: &str) -> Option<Value> {
    let cache_key = KeyType::string(key);

    let value = match reader.get(&cache_key).await {
        Ok(v) => v,
        Err(_) => {
            return None;
        }
    };

    if value.is_null() {
        return None;
    }

    // Check for Python's explicit "__missing__" marker
    if let Some(s) = value.as_str() {
        if s == HYPER_CACHE_EMPTY_VALUE {
            return None;
        }
    }

    Some(value)
}
