use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, RwLock};

use tracing::warn;

use crate::config::Config;
use crate::error::GatewayError;

/// Default per-team concurrency limits by ClickHouse user (caller identity).
///
/// These represent the maximum number of concurrent queries a single team can
/// run through a given CH user. They exist to prevent a single team from
/// monopolizing a workload's global concurrency budget.
const DEFAULT_LIMIT_API: u32 = 3;
const DEFAULT_LIMIT_APP: u32 = 10;
const DEFAULT_LIMIT_BATCH_EXPORT: u32 = 2;
const DEFAULT_LIMIT_MAX_AI: u32 = 5;

/// Fallback limit for any CH user not explicitly configured.
const DEFAULT_LIMIT_FALLBACK: u32 = 5;

/// In-memory per-team concurrency tracking.
///
/// Each (team_id, ch_user) pair has an atomic counter that tracks how many
/// queries are currently in-flight. `try_acquire` checks the counter against
/// the configured limit and, if below, atomically increments it and returns
/// a [`TeamPermit`] RAII guard that decrements the counter on drop.
pub struct TeamLimits {
    /// team_id → AtomicU32 counter of current concurrent queries.
    /// The RwLock is only taken as a write lock when a team is seen for the
    /// first time; the hot path (existing teams) only needs a read lock.
    counters: RwLock<HashMap<(u64, String), Arc<AtomicU32>>>,

    /// ch_user (uppercased) → max concurrent queries per team.
    limits: HashMap<String, u32>,
}

impl TeamLimits {
    /// Build a new `TeamLimits` from the gateway config.
    ///
    /// Currently the per-user limits are hard-coded defaults. When we add
    /// env-var overrides to [`Config`] we can wire them through here.
    pub fn new(_config: &Config) -> Self {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), DEFAULT_LIMIT_API);
        limits.insert("APP".to_string(), DEFAULT_LIMIT_APP);
        limits.insert("BATCH_EXPORT".to_string(), DEFAULT_LIMIT_BATCH_EXPORT);
        limits.insert("MAX_AI".to_string(), DEFAULT_LIMIT_MAX_AI);

        Self {
            counters: RwLock::new(HashMap::new()),
            limits,
        }
    }

    /// Create a `TeamLimits` with custom per-user limits.
    pub fn with_limits(limits: HashMap<String, u32>) -> Self {
        Self {
            counters: RwLock::new(HashMap::new()),
            limits,
        }
    }

    /// Look up the concurrency limit for a given CH user.
    ///
    /// Returns the configured limit if the user is known, otherwise falls back
    /// to [`DEFAULT_LIMIT_FALLBACK`].
    pub fn limit_for_user(&self, ch_user: &str) -> u32 {
        let key = ch_user.to_uppercase();
        self.limits
            .get(&key)
            .copied()
            .unwrap_or(DEFAULT_LIMIT_FALLBACK)
    }

    /// Attempt to acquire a concurrency slot for `(team_id, ch_user)`.
    ///
    /// On success, returns a [`TeamPermit`] that holds the slot and releases
    /// it on drop. On failure (limit reached), returns a `GatewayError`.
    ///
    /// The implementation uses a CAS loop on an `AtomicU32` so the hot path
    /// is lock-free once the counter exists.
    pub fn try_acquire(&self, team_id: u64, ch_user: &str) -> Result<TeamPermit, GatewayError> {
        let limit = self.limit_for_user(ch_user);
        let key = (team_id, ch_user.to_uppercase());

        let counter = self.get_or_create_counter(&key);

        // CAS loop: try to increment if below limit.
        loop {
            let current = counter.load(Ordering::Acquire);
            if current >= limit {
                warn!(
                    team_id = team_id,
                    ch_user = %ch_user,
                    current = current,
                    limit = limit,
                    "team concurrency limit reached"
                );
                return Err(GatewayError::TeamConcurrencyLimit {
                    team_id,
                    ch_user: ch_user.to_string(),
                    limit,
                });
            }
            // Try to atomically move current → current + 1.
            match counter.compare_exchange_weak(
                current,
                current + 1,
                Ordering::AcqRel,
                Ordering::Acquire,
            ) {
                Ok(_) => {
                    return Ok(TeamPermit {
                        counter: Arc::clone(&counter),
                        team_id,
                        ch_user: ch_user.to_uppercase(),
                    });
                }
                Err(_) => {
                    // Another thread changed the counter; retry.
                    continue;
                }
            }
        }
    }

    /// Return the current in-flight count for a (team_id, ch_user) pair.
    ///
    /// Useful for metrics and debugging. Returns 0 if the team has never been
    /// seen.
    pub fn current_count(&self, team_id: u64, ch_user: &str) -> u32 {
        let key = (team_id, ch_user.to_uppercase());
        let counters = self.counters.read().expect("counters lock poisoned");
        counters
            .get(&key)
            .map(|c| c.load(Ordering::Acquire))
            .unwrap_or(0)
    }

    /// Remove HashMap entries where the counter is zero.
    ///
    /// Called periodically by the background eviction task to prevent the
    /// counters map from growing without bound as new (team_id, ch_user)
    /// pairs are observed over time.
    pub fn evict_idle_entries(&self) -> usize {
        let mut counters = self.counters.write().expect("counters lock poisoned");
        let before = counters.len();
        counters.retain(|_key, counter| counter.load(Ordering::Acquire) > 0);
        let evicted = before - counters.len();
        if evicted > 0 {
            tracing::debug!(
                evicted,
                remaining = counters.len(),
                "evicted idle team counters"
            );
        }
        evicted
    }

    /// Spawn a background tokio task that periodically evicts idle counters.
    ///
    /// The task runs every `interval` and removes entries where the atomic
    /// counter is zero — meaning no queries are in-flight for that
    /// (team_id, ch_user) pair.
    pub fn spawn_eviction_task(self: &Arc<Self>, interval: std::time::Duration) {
        let limits = Arc::clone(self);
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(interval);
            tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                tick.tick().await;
                limits.evict_idle_entries();
            }
        });
    }

    /// Get or lazily create the atomic counter for a (team_id, ch_user) pair.
    ///
    /// Fast path: read lock only (existing teams). Slow path: write lock to
    /// insert a new counter.
    fn get_or_create_counter(&self, key: &(u64, String)) -> Arc<AtomicU32> {
        // Fast path: read lock.
        {
            let counters = self.counters.read().expect("counters lock poisoned");
            if let Some(counter) = counters.get(key) {
                return Arc::clone(counter);
            }
        }

        // Slow path: write lock to insert.
        let mut counters = self.counters.write().expect("counters lock poisoned");
        // Double-check after acquiring write lock.
        counters
            .entry(key.clone())
            .or_insert_with(|| Arc::new(AtomicU32::new(0)))
            .clone()
    }
}

/// RAII guard that releases a per-team concurrency slot on drop.
///
/// Held by the query handler for the duration of the ClickHouse request.
/// When the query completes (or the handler is cancelled), the permit is
/// dropped and the counter is decremented.
#[derive(Debug)]
pub struct TeamPermit {
    counter: Arc<AtomicU32>,
    /// Stored for logging/debugging only.
    #[allow(dead_code)]
    team_id: u64,
    #[allow(dead_code)]
    ch_user: String,
}

impl Drop for TeamPermit {
    fn drop(&mut self) {
        let prev = self.counter.fetch_sub(1, Ordering::AcqRel);
        debug_assert!(
            prev > 0,
            "TeamPermit drop underflowed counter for team_id={} ch_user={}",
            self.team_id,
            self.ch_user,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> Config {
        crate::config::test_config()
    }

    #[test]
    fn test_default_limits() {
        let tl = TeamLimits::new(&test_config());
        assert_eq!(tl.limit_for_user("API"), 3);
        assert_eq!(tl.limit_for_user("APP"), 10);
        assert_eq!(tl.limit_for_user("BATCH_EXPORT"), 2);
        assert_eq!(tl.limit_for_user("MAX_AI"), 5);
        // Case-insensitive lookup
        assert_eq!(tl.limit_for_user("api"), 3);
        assert_eq!(tl.limit_for_user("App"), 10);
        // Unknown user gets fallback
        assert_eq!(tl.limit_for_user("UNKNOWN"), 5);
    }

    #[test]
    fn test_acquire_within_limit() {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), 2);
        let tl = TeamLimits::with_limits(limits);

        let _p1 = tl
            .try_acquire(1, "API")
            .expect("first acquire should succeed");
        let _p2 = tl
            .try_acquire(1, "API")
            .expect("second acquire should succeed");

        assert_eq!(tl.current_count(1, "API"), 2);
    }

    #[test]
    fn test_acquire_exceeds_limit_rejected() {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), 1);
        let tl = TeamLimits::with_limits(limits);

        let _p1 = tl
            .try_acquire(1, "API")
            .expect("first acquire should succeed");
        let result = tl.try_acquire(1, "API");

        assert!(result.is_err());
        match result.unwrap_err() {
            GatewayError::TeamConcurrencyLimit {
                team_id,
                ch_user,
                limit,
            } => {
                assert_eq!(team_id, 1);
                assert_eq!(ch_user, "API");
                assert_eq!(limit, 1);
            }
            other => panic!("expected TeamConcurrencyLimit, got: {other:?}"),
        }
    }

    #[test]
    fn test_permit_drop_releases_slot() {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), 1);
        let tl = TeamLimits::with_limits(limits);

        {
            let _p = tl.try_acquire(1, "API").expect("should succeed");
            assert_eq!(tl.current_count(1, "API"), 1);
        }
        // Permit dropped — slot released.
        assert_eq!(tl.current_count(1, "API"), 0);

        // Should be able to acquire again.
        let _p2 = tl
            .try_acquire(1, "API")
            .expect("should succeed after release");
        assert_eq!(tl.current_count(1, "API"), 1);
    }

    #[test]
    fn test_different_teams_independent() {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), 1);
        let tl = TeamLimits::with_limits(limits);

        let _p1 = tl.try_acquire(1, "API").expect("team 1 should succeed");
        let _p2 = tl
            .try_acquire(2, "API")
            .expect("team 2 should succeed independently");

        assert_eq!(tl.current_count(1, "API"), 1);
        assert_eq!(tl.current_count(2, "API"), 1);
    }

    #[test]
    fn test_different_users_different_limits() {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), 1);
        limits.insert("APP".to_string(), 2);
        let tl = TeamLimits::with_limits(limits);

        // API at limit
        let _p1 = tl.try_acquire(1, "API").expect("API should succeed");
        assert!(tl.try_acquire(1, "API").is_err());

        // APP still has room for team 1
        let _p2 = tl.try_acquire(1, "APP").expect("APP should succeed");
        let _p3 = tl.try_acquire(1, "APP").expect("APP second should succeed");
        assert!(tl.try_acquire(1, "APP").is_err());
    }

    #[test]
    fn test_current_count_unseen_team() {
        let tl = TeamLimits::new(&test_config());
        assert_eq!(tl.current_count(999, "API"), 0);
    }

    #[test]
    fn test_evict_idle_entries() {
        let mut limits = HashMap::new();
        limits.insert("API".to_string(), 5);
        let tl = TeamLimits::with_limits(limits);

        // Acquire and release for team 1 — counter goes to 0.
        {
            let _p = tl.try_acquire(1, "API").expect("should succeed");
        }
        // Team 1 counter is 0 but entry still exists.
        assert_eq!(tl.current_count(1, "API"), 0);

        // Acquire for team 2 — still active.
        let _p2 = tl.try_acquire(2, "API").expect("should succeed");
        assert_eq!(tl.current_count(2, "API"), 1);

        // Evict should remove team 1's entry but keep team 2's.
        let evicted = tl.evict_idle_entries();
        assert_eq!(evicted, 1);
        assert_eq!(tl.current_count(2, "API"), 1);

        // Team 1 can still be re-acquired (new entry will be created).
        let _p3 = tl
            .try_acquire(1, "API")
            .expect("should succeed after eviction");
        assert_eq!(tl.current_count(1, "API"), 1);
    }
}
