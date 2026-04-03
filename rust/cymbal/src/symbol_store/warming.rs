use std::sync::Arc;
use std::time::Instant;

use posthog_symbol_data::{sniff_data_type, SymbolDataType};
use sqlx::PgPool;
use tokio::sync::{Mutex, Semaphore};
use tracing::{info, warn};

use crate::{
    config::Config,
    error::UnhandledError,
    metric_consts::{
        CACHE_WARMING_BYTES_LOADED, CACHE_WARMING_DURATION, CACHE_WARMING_ENTRIES_FAILED,
        CACHE_WARMING_ENTRIES_LOADED,
    },
    symbol_store::{
        apple::{AppleProvider, ParsedAppleSymbols},
        caching::{Countable, SymbolSetCache},
        hermesmap::{HermesMapProvider, ParsedHermesMap},
        proguard::{FetchedMapping, ProguardProvider},
        saving::SymbolSetRecord,
        sourcemap::{OwnedSourceMapCache, SourcemapProvider},
        BlobClient, Parser,
    },
};

struct WarmingParsers {
    smp: SourcemapProvider,
    hmp: HermesMapProvider,
    pgp: ProguardProvider,
    apple: AppleProvider,
}

/// Leave 15% headroom in the cache for incoming traffic after the consumer starts.
const WARMING_FILL_FRACTION: f64 = 0.85;

/// Pre-populates the symbol set cache from DB + S3 on startup. Queries for recently-used
/// symbol sets, fetches their raw data from S3, parses them using the type discriminator
/// in the `posthog_symbol_data` binary format, and inserts the results into the shared cache.
/// Stops early once the cache reaches 85% of its byte capacity.
pub async fn warm_cache(
    pool: &PgPool,
    s3_client: &Arc<dyn BlobClient>,
    bucket: &str,
    ss_cache: &Arc<Mutex<SymbolSetCache>>,
    config: &Config,
) -> Result<(), UnhandledError> {
    let start = Instant::now();

    let lookback_hours = config.cache_warming_lookback_hours as i64;
    let records: Vec<SymbolSetRecord> = sqlx::query_as::<_, SymbolSetRecord>(
        r#"SELECT id, team_id, ref AS set_ref, storage_ptr, failure_reason, created_at, content_hash, last_used
        FROM posthog_errortrackingsymbolset
        WHERE content_hash IS NOT NULL
          AND storage_ptr IS NOT NULL
          AND last_used > NOW() - make_interval(hours => $1::integer)
        ORDER BY last_used DESC
        LIMIT $2"#,
    )
    .bind(lookback_hours)
    .bind(config.cache_warming_max_entries as i64)
    .fetch_all(pool)
    .await?;

    let total = records.len();
    let byte_budget = (config.symbol_store_cache_max_bytes as f64 * WARMING_FILL_FRACTION) as usize;
    info!(
        count = total,
        byte_budget, "Fetched warming candidates from DB"
    );

    if total == 0 {
        return Ok(());
    }

    let semaphore = Arc::new(Semaphore::new(config.cache_warming_concurrency));
    let parsers = Arc::new(WarmingParsers {
        smp: SourcemapProvider::new(config),
        hmp: HermesMapProvider {},
        pgp: ProguardProvider {},
        apple: AppleProvider {},
    });

    let mut handles = Vec::with_capacity(total);

    // Spawn all tasks immediately — the semaphore is acquired inside each task
    // so the spawn loop doesn't block. This ensures the timeout below covers
    // the full warming duration, not just the result-collection phase.
    for record in records {
        let sem = semaphore.clone();
        let s3 = s3_client.clone();
        let bucket = bucket.to_string();
        let cache = ss_cache.clone();
        let parsers = parsers.clone();

        handles.push(tokio::spawn(async move {
            let _permit = sem.acquire_owned().await.unwrap();
            let result =
                warm_single_entry(&s3, &bucket, &cache, &parsers, &record, byte_budget).await;
            (record.set_ref, result)
        }));
    }

    let mut loaded: u64 = 0;
    let mut failed: u64 = 0;
    let mut skipped: u64 = 0;
    let mut bytes_loaded: u64 = 0;

    // Collect results one at a time under a shared deadline. If we exceed the
    // timeout, abort remaining tasks so they don't compete with real traffic
    // after the pod is marked ready.
    let deadline =
        tokio::time::Instant::now() + tokio::time::Duration::from_secs(config.cache_warming_timeout_seconds);
    let mut timed_out = false;

    for handle in handles.iter_mut() {
        match tokio::time::timeout_at(deadline, handle).await {
            Ok(Ok((_, Ok(Some(bytes))))) => {
                loaded += 1;
                bytes_loaded += bytes as u64;
            }
            Ok(Ok((_, Ok(None)))) => {
                skipped += 1;
            }
            Ok(Ok((ref_name, Err(e)))) => {
                warn!(set_ref = %ref_name, error = %e, "Failed to warm symbol set");
                failed += 1;
            }
            Ok(Err(e)) => {
                warn!(error = %e, "Warming task panicked");
                failed += 1;
            }
            Err(_) => {
                timed_out = true;
                break;
            }
        }
    }

    if timed_out {
        for handle in &handles {
            handle.abort();
        }
        warn!(
            timeout_seconds = config.cache_warming_timeout_seconds,
            loaded, failed, skipped, "Cache warming timed out, aborting remaining tasks"
        );
    }

    let elapsed = start.elapsed();
    info!(
        loaded,
        failed,
        skipped,
        total,
        bytes_loaded,
        byte_budget,
        elapsed_ms = elapsed.as_millis() as u64,
        "Cache warming complete"
    );

    metrics::counter!(CACHE_WARMING_ENTRIES_LOADED).increment(loaded);
    metrics::counter!(CACHE_WARMING_ENTRIES_FAILED).increment(failed);
    metrics::counter!(CACHE_WARMING_BYTES_LOADED).increment(bytes_loaded);
    metrics::histogram!(CACHE_WARMING_DURATION).record(elapsed.as_secs_f64());

    Ok(())
}

async fn warm_single_entry(
    s3_client: &Arc<dyn BlobClient>,
    bucket: &str,
    cache: &Arc<Mutex<SymbolSetCache>>,
    parsers: &WarmingParsers,
    record: &SymbolSetRecord,
    byte_budget: usize,
) -> Result<Option<usize>, UnhandledError> {
    // Check byte budget before doing any expensive S3/parse work. Concurrent tasks may
    // slightly overshoot, but the cache's own eviction handles that gracefully.
    if cache.lock().await.held_bytes() >= byte_budget {
        return Ok(None);
    }

    let storage_ptr = record
        .storage_ptr
        .as_ref()
        .ok_or_else(|| UnhandledError::Other("missing storage_ptr".to_string()))?;

    let data = s3_client
        .get(bucket, storage_ptr)
        .await?
        .ok_or_else(|| UnhandledError::Other("S3 object not found".to_string()))?;

    let data_type = sniff_data_type(&data)
        .map_err(|e| UnhandledError::Other(format!("failed to sniff data type: {e}")))?;

    let cache_key = format!("{}:{}", record.team_id, record.set_ref);
    let bytes;

    match data_type {
        SymbolDataType::SourceAndMap => {
            let parsed = parsers
                .smp
                .parse(data)
                .await
                .map_err(|e| UnhandledError::Other(format!("sourcemap parse failed: {e}")))?;
            bytes = parsed.byte_count();
            cache
                .lock()
                .await
                .insert::<OwnedSourceMapCache>(cache_key, Arc::new(parsed), bytes);
        }
        SymbolDataType::HermesMap => {
            let parsed = parsers
                .hmp
                .parse(data)
                .await
                .map_err(|e| UnhandledError::Other(format!("hermes parse failed: {e}")))?;
            bytes = parsed.byte_count();
            cache
                .lock()
                .await
                .insert::<ParsedHermesMap>(cache_key, Arc::new(parsed), bytes);
        }
        SymbolDataType::ProguardMapping => {
            let parsed = parsers
                .pgp
                .parse(data)
                .await
                .map_err(|e| UnhandledError::Other(format!("proguard parse failed: {e}")))?;
            bytes = parsed.byte_count();
            cache
                .lock()
                .await
                .insert::<FetchedMapping>(cache_key, Arc::new(parsed), bytes);
        }
        SymbolDataType::AppleDsym => {
            let parsed = parsers
                .apple
                .parse(data)
                .await
                .map_err(|e| UnhandledError::Other(format!("apple parse failed: {e}")))?;
            bytes = parsed.byte_count();
            cache
                .lock()
                .await
                .insert::<ParsedAppleSymbols>(cache_key, Arc::new(parsed), bytes);
        }
    }

    Ok(Some(bytes))
}

#[cfg(test)]
mod test {
    use super::*;
    use chrono::Utc;
    use posthog_symbol_data::write_symbol_data;
    use uuid::Uuid;

    use crate::symbol_store::{saving::SymbolSetRecord, MockS3Client};

    const MINIFIED: &[u8] = include_bytes!("../../tests/static/chunk-PGUQKT6S.js");
    const MAP: &[u8] = include_bytes!("../../tests/static/chunk-PGUQKT6S.js.map");

    fn test_symbol_data() -> Vec<u8> {
        write_symbol_data(posthog_symbol_data::SourceAndMap {
            minified_source: String::from_utf8(MINIFIED.to_vec()).unwrap(),
            sourcemap: String::from_utf8(MAP.to_vec()).unwrap(),
        })
        .unwrap()
    }

    fn make_record(key: &str) -> SymbolSetRecord {
        SymbolSetRecord {
            id: Uuid::now_v7(),
            team_id: 1,
            set_ref: format!("http://example.com/{key}"),
            storage_ptr: Some(key.to_string()),
            failure_reason: None,
            created_at: Utc::now(),
            content_hash: Some("abc123".to_string()),
            last_used: Some(Utc::now()),
        }
    }

    fn make_parsers() -> WarmingParsers {
        let config = Config::init_with_defaults().unwrap();
        WarmingParsers {
            smp: SourcemapProvider::new(&config),
            hmp: HermesMapProvider {},
            pgp: ProguardProvider {},
            apple: AppleProvider {},
        }
    }

    #[tokio::test]
    async fn skips_entry_when_over_byte_budget() {
        let parsers = make_parsers();
        let cache = Arc::new(Mutex::new(SymbolSetCache::new(1000)));
        cache
            .lock()
            .await
            .insert("prefill".to_string(), Arc::new(vec![0u8; 500]), 500);

        // MockS3Client::new() panics on any unexpected call, verifying S3 is never touched
        let s3_client: Arc<dyn BlobClient> = Arc::new(MockS3Client::new());
        let record = make_record("test-key");

        let result = warm_single_entry(&s3_client, "bucket", &cache, &parsers, &record, 100).await;

        assert!(result.unwrap().is_none());
        assert_eq!(cache.lock().await.held_bytes(), 500);
    }

    #[tokio::test]
    async fn loads_entry_when_under_byte_budget() {
        let parsers = make_parsers();
        let cache = Arc::new(Mutex::new(SymbolSetCache::new(100_000_000)));

        let data = test_symbol_data();
        let mut s3_client = MockS3Client::new();
        s3_client
            .expect_get()
            .returning(move |_, _| Ok(Some(data.clone())));

        let s3_client: Arc<dyn BlobClient> = Arc::new(s3_client);
        let record = make_record("test-key");

        let result =
            warm_single_entry(&s3_client, "bucket", &cache, &parsers, &record, 100_000_000).await;

        let bytes = result.unwrap().unwrap();
        assert!(bytes > 0);
        assert_eq!(cache.lock().await.held_bytes(), bytes);
    }

    #[sqlx::test(migrations = "./tests/test_migrations")]
    async fn warm_cache_skips_all_when_budget_is_zero(db: PgPool) {
        for i in 0..3 {
            sqlx::query(
                "INSERT INTO posthog_errortrackingsymbolset \
                 (id, team_id, ref, storage_ptr, content_hash, last_used, created_at) \
                 VALUES ($1, $2, $3, $4, $5, NOW(), NOW())",
            )
            .bind(Uuid::now_v7())
            .bind(1i32)
            .bind(format!("http://example.com/test-{i}.js"))
            .bind(format!("symbolsets/test-{i}"))
            .bind("somehash")
            .execute(&db)
            .await
            .unwrap();
        }

        // No S3 expectations — budget is zero so nothing should be fetched
        let s3_client: Arc<dyn BlobClient> = Arc::new(MockS3Client::new());
        let cache = Arc::new(Mutex::new(SymbolSetCache::new(1)));

        let mut config = Config::init_with_defaults().unwrap();
        config.cache_warming_lookback_hours = 1;
        config.cache_warming_max_entries = 100;
        config.cache_warming_concurrency = 1;
        config.cache_warming_timeout_seconds = 30;
        config.symbol_store_cache_max_bytes = 1;

        warm_cache(&db, &s3_client, "bucket", &cache, &config)
            .await
            .unwrap();

        assert_eq!(cache.lock().await.held_bytes(), 0);
    }

    #[sqlx::test(migrations = "./tests/test_migrations")]
    async fn warm_cache_loads_entries(db: PgPool) {
        for i in 0..2 {
            sqlx::query(
                "INSERT INTO posthog_errortrackingsymbolset \
                 (id, team_id, ref, storage_ptr, content_hash, last_used, created_at) \
                 VALUES ($1, $2, $3, $4, $5, NOW(), NOW())",
            )
            .bind(Uuid::now_v7())
            .bind(1i32)
            .bind(format!("http://example.com/test-{i}.js"))
            .bind(format!("symbolsets/test-{i}"))
            .bind("somehash")
            .execute(&db)
            .await
            .unwrap();
        }

        let data = test_symbol_data();
        let mut s3_client = MockS3Client::new();
        s3_client
            .expect_get()
            .returning(move |_, _| Ok(Some(data.clone())));

        let s3_client: Arc<dyn BlobClient> = Arc::new(s3_client);
        let cache = Arc::new(Mutex::new(SymbolSetCache::new(100_000_000)));

        let mut config = Config::init_with_defaults().unwrap();
        config.cache_warming_lookback_hours = 1;
        config.cache_warming_max_entries = 100;
        config.cache_warming_concurrency = 1;
        config.cache_warming_timeout_seconds = 30;
        config.symbol_store_cache_max_bytes = 100_000_000;

        warm_cache(&db, &s3_client, "bucket", &cache, &config)
            .await
            .unwrap();

        assert!(cache.lock().await.held_bytes() > 0);
    }
}
