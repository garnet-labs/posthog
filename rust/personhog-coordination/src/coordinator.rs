use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use etcd_client::EventType;
use metrics::{counter, gauge, histogram};
use tokio_util::sync::CancellationToken;

use assignment_coordination::store::parse_watch_value;
use assignment_coordination::util::compute_required_handoffs;
use k8s_awareness::types::ControllerKind;
use k8s_awareness::{DepartureReason, K8sAwareness};

use crate::error::{Error, Result};
use crate::store::{self, PersonhogStore};
use crate::strategy::AssignmentStrategy;
use crate::types::{
    AssignmentStatus, HandoffPhase, HandoffState, PartitionAssignment, PodStatus, RegisteredPod,
};
use crate::util;

#[derive(Debug, Clone)]
pub struct CoordinatorConfig {
    pub name: String,
    pub leader_lease_ttl: i64,
    pub keepalive_interval: Duration,
    pub election_retry_interval: Duration,
    /// How long to wait after the first pod event before rebalancing, to batch
    /// rapid pod registrations into a single rebalance.
    pub rebalance_debounce_interval: Duration,
}

impl Default for CoordinatorConfig {
    fn default() -> Self {
        Self {
            name: "coordinator-0".to_string(),
            leader_lease_ttl: 15,
            keepalive_interval: Duration::from_secs(5),
            election_retry_interval: Duration::from_secs(5),
            rebalance_debounce_interval: Duration::from_secs(1),
        }
    }
}

pub struct Coordinator {
    store: Arc<PersonhogStore>,
    config: CoordinatorConfig,
    strategy: Arc<dyn AssignmentStrategy>,
    k8s_awareness: Option<Arc<K8sAwareness>>,
}

impl Coordinator {
    pub fn new(
        store: Arc<PersonhogStore>,
        config: CoordinatorConfig,
        strategy: Arc<dyn AssignmentStrategy>,
        k8s_awareness: Option<Arc<K8sAwareness>>,
    ) -> Self {
        Self {
            store,
            config,
            strategy,
            k8s_awareness,
        }
    }

    /// Run the coordinator loop. Continuously attempts leader election;
    /// when elected, runs the coordination loop until leadership is lost
    /// or cancellation is requested.
    pub async fn run(&self, cancel: CancellationToken) -> Result<()> {
        loop {
            tokio::select! {
                _ = cancel.cancelled() => return Ok(()),
                result = self.try_lead(cancel.clone()) => {
                    match result {
                        Ok(()) => tracing::info!(name = %self.config.name, "leadership ended normally"),
                        Err(e) => tracing::warn!(name = %self.config.name, error = %e, "leader loop ended with error"),
                    }
                    tokio::select! {
                        _ = cancel.cancelled() => return Ok(()),
                        _ = tokio::time::sleep(self.config.election_retry_interval) => {}
                    }
                }
            }
        }
    }

    async fn try_lead(&self, cancel: CancellationToken) -> Result<()> {
        let lease_id = self.store.grant_lease(self.config.leader_lease_ttl).await?;

        let acquired = self
            .store
            .try_acquire_leadership(&self.config.name, lease_id)
            .await?;

        if !acquired {
            tracing::debug!(name = %self.config.name, "another coordinator is leader, standing by");
            gauge!("personhog_coordinator_is_leader").set(0.0);
            return Ok(());
        }

        tracing::info!(name = %self.config.name, "acquired leadership");
        gauge!("personhog_coordinator_is_leader").set(1.0);
        counter!("personhog_coordinator_elections_total").increment(1);

        // Spawn lease keepalive
        let keepalive_cancel = cancel.child_token();
        let keepalive_handle = {
            let store = Arc::clone(&self.store);
            let interval = self.config.keepalive_interval;
            let token = keepalive_cancel.clone();
            tokio::spawn(async move {
                if let Err(e) = util::run_lease_keepalive(store, lease_id, interval, token).await {
                    tracing::error!(error = %e, "keepalive failed");
                }
            })
        };

        let result = self.run_coordination_loop(cancel.clone()).await;

        gauge!("personhog_coordinator_is_leader").set(0.0);

        // Clean up keepalive
        keepalive_cancel.cancel();
        drop(keepalive_handle.await);

        // Best-effort revoke so next leader can take over quickly
        drop(self.store.revoke_lease(lease_id).await);

        result
    }

    async fn run_coordination_loop(&self, cancel: CancellationToken) -> Result<()> {
        // Reconcile any handoffs that already have full ack quorum.
        // This handles acks that arrived before this coordinator took leadership.
        self.reconcile_pending_handoffs().await?;

        // Compute initial assignments for any pods that are already registered
        self.handle_pod_change().await?;

        // Watch pods, handoffs, and router acks concurrently
        let mut tasks = tokio::task::JoinSet::new();

        {
            let store = Arc::clone(&self.store);
            let strategy = Arc::clone(&self.strategy);
            let k8s_awareness = self.k8s_awareness.clone();
            let debounce_interval = self.config.rebalance_debounce_interval;
            let token = cancel.child_token();
            tasks.spawn(async move {
                Self::watch_pods_loop(store, strategy, k8s_awareness, debounce_interval, token)
                    .await
            });
        }

        {
            let store = Arc::clone(&self.store);
            let strategy = Arc::clone(&self.strategy);
            let k8s_awareness = self.k8s_awareness.clone();
            let token = cancel.child_token();
            tasks.spawn(async move {
                Self::watch_handoffs_loop(store, strategy, k8s_awareness, token).await
            });
        }

        {
            let store = Arc::clone(&self.store);
            let token = cancel.child_token();
            tasks.spawn(async move { Self::watch_handoff_acks_loop(store, token).await });
        }

        let result = tokio::select! {
            _ = cancel.cancelled() => Ok(()),
            Some(result) = tasks.join_next() => {
                result.map_err(|e| Error::invalid_state(format!("task panicked: {e}")))?
            }
        };

        // Abort and await all remaining tasks for clean shutdown
        tasks.shutdown().await;

        result
    }

    async fn watch_pods_loop(
        store: Arc<PersonhogStore>,
        strategy: Arc<dyn AssignmentStrategy>,
        k8s_awareness: Option<Arc<K8sAwareness>>,
        debounce_interval: Duration,
        cancel: CancellationToken,
    ) -> Result<()> {
        let mut stream = store.watch_pods().await?;

        loop {
            // Wait for the first pod event
            tokio::select! {
                _ = cancel.cancelled() => return Ok(()),
                msg = stream.message() => {
                    let resp = msg?.ok_or_else(|| Error::invalid_state("pod watch stream ended".to_string()))?;
                    Self::handle_pod_events(&resp, &store, k8s_awareness.as_deref()).await;
                }
            }

            // Drain additional events arriving within the debounce window
            let deadline = tokio::time::Instant::now() + debounce_interval;
            loop {
                tokio::select! {
                    _ = cancel.cancelled() => return Ok(()),
                    _ = tokio::time::sleep_until(deadline) => break,
                    msg = stream.message() => {
                        let resp = msg?.ok_or_else(|| Error::invalid_state("pod watch stream ended".to_string()))?;
                        Self::handle_pod_events(&resp, &store, k8s_awareness.as_deref()).await;
                    }
                }
            }

            Self::handle_pod_change_static(&store, strategy.as_ref(), k8s_awareness.as_deref())
                .await?;
        }
    }

    /// Log pod watch events and enrich new registrations with K8s metadata.
    ///
    /// When a pod registers with empty generation (which is the normal case —
    /// leader pods self-register without K8s context), the coordinator discovers
    /// the pod's controller and generation via the K8s API and persists it back
    /// to etcd. This is a one-time operation per pod registration.
    async fn handle_pod_events(
        resp: &etcd_client::WatchResponse,
        store: &PersonhogStore,
        k8s_awareness: Option<&K8sAwareness>,
    ) {
        for event in resp.events() {
            match event.event_type() {
                EventType::Put => {
                    let pod: RegisteredPod = match parse_watch_value(event) {
                        Ok(p) => p,
                        Err(e) => {
                            tracing::warn!(error = %e, "failed to parse pod event");
                            continue;
                        }
                    };
                    tracing::info!(pod = %pod.pod_name, status = ?pod.status, "pod registered or updated");

                    if pod.generation.is_empty() {
                        if let Some(k8s) = k8s_awareness {
                            match k8s.discover_controller(&pod.pod_name).await {
                                Ok(info) => {
                                    tracing::info!(
                                        pod = %pod.pod_name,
                                        controller = %info.controller,
                                        generation = %info.generation,
                                        "discovered K8s controller for pod"
                                    );
                                    if let Err(e) = store
                                        .enrich_pod_k8s(
                                            &pod.pod_name,
                                            &info.generation,
                                            &info.controller,
                                        )
                                        .await
                                    {
                                        tracing::warn!(
                                            pod = %pod.pod_name,
                                            error = %e,
                                            "failed to persist K8s enrichment"
                                        );
                                        counter!("personhog_coordinator_k8s_enrichments_total", "outcome" => "persist_error").increment(1);
                                    } else {
                                        counter!("personhog_coordinator_k8s_enrichments_total", "outcome" => "success").increment(1);
                                    }
                                }
                                Err(e) => {
                                    tracing::warn!(
                                        pod = %pod.pod_name,
                                        error = %e,
                                        "failed to discover K8s controller, proceeding without"
                                    );
                                    counter!("personhog_coordinator_k8s_enrichments_total", "outcome" => "discovery_error").increment(1);
                                }
                            }
                        }
                    }
                }
                EventType::Delete => tracing::warn!("pod lease expired or deleted"),
            }
        }
    }

    async fn watch_handoffs_loop(
        store: Arc<PersonhogStore>,
        strategy: Arc<dyn AssignmentStrategy>,
        k8s_awareness: Option<Arc<K8sAwareness>>,
        cancel: CancellationToken,
    ) -> Result<()> {
        let mut stream = store.watch_handoffs().await?;

        loop {
            tokio::select! {
                _ = cancel.cancelled() => return Ok(()),
                msg = stream.message() => {
                    let resp = msg?.ok_or_else(|| Error::invalid_state("handoff watch stream ended".to_string()))?;
                    for event in resp.events() {
                        if event.event_type() == EventType::Put {
                            match parse_watch_value::<HandoffState>(event) {
                                Ok(handoff) => {
                                    Self::handle_handoff_update_static(&store, &handoff).await?;
                                }
                                Err(e) => {
                                    tracing::error!(error = %e, "failed to parse handoff event");
                                }
                            }
                        }
                    }

                    // After processing all events in this batch, check if all
                    // handoffs have completed. If so, re-trigger rebalancing to
                    // pick up any pod changes that were deferred.
                    if store.list_handoffs().await?.is_empty() {
                        Self::handle_pod_change_static(
                            &store,
                            strategy.as_ref(),
                            k8s_awareness.as_deref(),
                        )
                        .await?;
                    }
                }
            }
        }
    }

    /// Watch for router cutover acks. When all registered routers have acked
    /// a partition's handoff, complete the handoff (update assignment + phase).
    async fn watch_handoff_acks_loop(
        store: Arc<PersonhogStore>,
        cancel: CancellationToken,
    ) -> Result<()> {
        let mut stream = store.watch_handoff_acks().await?;

        loop {
            tokio::select! {
                _ = cancel.cancelled() => return Ok(()),
                msg = stream.message() => {
                    let resp = msg?.ok_or_else(|| Error::invalid_state("ack watch stream ended".to_string()))?;
                    for event in resp.events() {
                        if event.event_type() == EventType::Put {
                            // Extract partition from the ack key
                            let partition = event.kv().and_then(|kv| {
                                let key = std::str::from_utf8(kv.key()).ok()?;
                                store::extract_partition_from_ack_key(key)
                            });

                            if let Some(partition) = partition {
                                Self::check_ack_completion(&store, partition).await?;
                            }
                        }
                    }
                }
            }
        }
    }

    /// Check if all routers have acked a partition handoff.
    /// If so, atomically complete the handoff.
    async fn check_ack_completion(store: &PersonhogStore, partition: u32) -> Result<()> {
        let routers = store.list_routers().await?;
        if routers.is_empty() {
            tracing::warn!(partition, "no routers registered, cannot complete handoff");
            return Ok(());
        }

        let acks = store.list_router_acks(partition).await?;

        if acks.len() >= routers.len() {
            tracing::info!(
                partition,
                acks = acks.len(),
                routers = routers.len(),
                "all routers acked, completing handoff"
            );
            match store.complete_handoff(partition).await {
                Ok(true) => {}
                Ok(false) => {
                    tracing::warn!(partition, "handoff was modified concurrently, skipping");
                }
                Err(Error::NotFound(_)) => {
                    tracing::warn!(partition, "handoff already deleted, ignoring duplicate ack");
                }
                Err(e) => return Err(e),
            }
        }

        Ok(())
    }

    /// Reconcile all coordination state on leadership acquisition.
    ///
    /// The previous leader may have crashed at any point, leaving partial state:
    /// - Ready handoffs with full ack quorum that were never completed
    /// - Complete handoffs that were never cleaned up (acks + handoff key)
    /// - Handoffs targeting pods that no longer exist
    async fn reconcile_pending_handoffs(&self) -> Result<()> {
        let handoffs = self.store.list_handoffs().await?;
        if handoffs.is_empty() {
            return Ok(());
        }

        tracing::info!(
            count = handoffs.len(),
            "reconciling existing handoffs on startup"
        );

        let pods = self.store.list_pods().await?;
        let active = active_pod_names(&pods);

        for handoff in &handoffs {
            match handoff.phase {
                // Ready: check if acks already reached quorum
                HandoffPhase::Ready => {
                    Self::check_ack_completion(&self.store, handoff.partition).await?;
                }
                // Complete: old leader crashed before cleanup — finish it
                HandoffPhase::Complete => {
                    tracing::info!(
                        partition = handoff.partition,
                        "cleaning up orphaned Complete handoff from previous leader"
                    );
                    self.store
                        .delete_router_acks(handoff.partition)
                        .await?;
                    self.store.delete_handoff(handoff.partition).await?;
                    counter!("personhog_coordinator_handoffs_total", "outcome" => "completed")
                        .increment(1);
                }
                // Warming: check if new_owner is still alive
                HandoffPhase::Warming => {}
            }
        }

        // Clean up handoffs targeting dead pods (covers all phases)
        Self::cleanup_stale_handoffs(&self.store, &active).await?;

        Ok(())
    }

    /// Handle a pod registration/deletion by recomputing assignments.
    async fn handle_pod_change(&self) -> Result<()> {
        Self::handle_pod_change_static(
            &self.store,
            self.strategy.as_ref(),
            self.k8s_awareness.as_deref(),
        )
        .await
    }

    async fn handle_pod_change_static(
        store: &PersonhogStore,
        strategy: &dyn AssignmentStrategy,
        k8s_awareness: Option<&K8sAwareness>,
    ) -> Result<()> {
        let rebalance_start = Instant::now();

        let pods = store.list_pods().await?;
        let total_partitions = match store.get_total_partitions().await {
            Ok(n) => n,
            Err(Error::NotFound(_)) => {
                tracing::debug!("total_partitions not set, skipping assignment");
                return Ok(());
            }
            Err(e) => return Err(e),
        };

        // Emit pod gauges
        let ready = pods.iter().filter(|p| p.status == PodStatus::Ready).count();
        let draining = pods.iter().filter(|p| p.status == PodStatus::Draining).count();
        gauge!("personhog_coordinator_pods_registered", "status" => "ready").set(ready as f64);
        gauge!("personhog_coordinator_pods_registered", "status" => "draining").set(draining as f64);

        // Emit router gauge
        let routers = store.list_routers().await.unwrap_or_default();
        gauge!("personhog_coordinator_routers_registered").set(routers.len() as f64);

        let mut active_pods = active_pod_names(&pods);

        // K8s-aware pod filtering for smarter rebalancing
        if let Some(k8s) = k8s_awareness {
            active_pods = filter_pods_for_k8s(k8s, &pods, active_pods).await;
        }

        // Clean up any in-flight handoffs targeting pods that are no longer active.
        // This happens when a pod crashes during the Warming phase before it can
        // signal Ready — the handoff would be stuck forever otherwise.
        Self::cleanup_stale_handoffs(store, &active_pods).await?;

        // Skip rebalancing while handoffs are in flight to prevent overlapping
        // rebalances from overwriting each other. The watch_handoffs_loop will
        // re-trigger rebalancing once all handoffs complete.
        let remaining_handoffs = store.list_handoffs().await?;
        emit_handoff_gauges(&remaining_handoffs);
        if !remaining_handoffs.is_empty() {
            tracing::info!(
                in_flight = remaining_handoffs.len(),
                "handoffs in progress, deferring rebalance"
            );
            return Ok(());
        }

        let current_assignments = store.list_assignments().await?;
        emit_assignment_gauges(&current_assignments);

        let current_map: HashMap<u32, String> = current_assignments
            .iter()
            .map(|a| (a.partition, a.owner.clone()))
            .collect();

        let new_assignments =
            strategy.compute_assignments(&current_map, &active_pods, total_partitions);
        let handoffs = compute_required_handoffs(&current_map, &new_assignments);

        if handoffs.is_empty() && !current_map.is_empty() {
            tracing::debug!("no handoffs needed");
            return Ok(());
        }

        // Build assignment objects for all partitions
        let assignment_objects: Vec<PartitionAssignment> = new_assignments
            .iter()
            .map(|(&partition, owner)| PartitionAssignment {
                partition,
                owner: owner.clone(),
                status: AssignmentStatus::Active,
            })
            .collect();

        if handoffs.is_empty() {
            // Initial assignment, no handoffs needed
            tracing::info!(
                partitions = total_partitions,
                pods = pods.len(),
                "writing initial assignments"
            );
            store.put_assignments(&assignment_objects).await?;
            emit_assignment_gauges(&assignment_objects);
            counter!("personhog_coordinator_rebalances_total").increment(1);
            histogram!("personhog_coordinator_rebalance_duration_seconds")
                .record(rebalance_start.elapsed().as_secs_f64());
            return Ok(());
        }

        // Create handoff states for partitions that need to move
        let now = util::now_seconds();
        let handoff_objects: Vec<HandoffState> = handoffs
            .iter()
            .map(|(partition, old_owner, new_owner)| HandoffState {
                partition: *partition,
                old_owner: old_owner.clone(),
                new_owner: new_owner.clone(),
                phase: HandoffPhase::Warming,
                started_at: now,
            })
            .collect();

        tracing::info!(
            handoffs = handoff_objects.len(),
            "creating handoffs for partition reassignment"
        );

        // Only write assignments for partitions that are NOT being handed off.
        // Handed-off partitions keep their current assignment until cutover.
        let handoff_partitions: std::collections::HashSet<u32> =
            handoffs.iter().map(|(p, _, _)| *p).collect();
        let stable_assignments: Vec<PartitionAssignment> = assignment_objects
            .into_iter()
            .filter(|a| !handoff_partitions.contains(&a.partition))
            .collect();

        store
            .create_assignments_and_handoffs(&stable_assignments, &handoff_objects)
            .await?;

        counter!("personhog_coordinator_handoffs_total", "outcome" => "started")
            .increment(handoff_objects.len() as u64);
        counter!("personhog_coordinator_rebalances_total").increment(1);
        histogram!("personhog_coordinator_rebalance_duration_seconds")
            .record(rebalance_start.elapsed().as_secs_f64());

        Ok(())
    }

    /// Delete handoffs whose `new_owner` is no longer an active pod.
    async fn cleanup_stale_handoffs(store: &PersonhogStore, active_pods: &[String]) -> Result<()> {
        let handoffs = store.list_handoffs().await?;
        let active_set: std::collections::HashSet<&str> =
            active_pods.iter().map(|s| s.as_str()).collect();

        for handoff in &handoffs {
            if !active_set.contains(handoff.new_owner.as_str()) {
                tracing::warn!(
                    partition = handoff.partition,
                    new_owner = %handoff.new_owner,
                    phase = ?handoff.phase,
                    "cleaning up stale handoff targeting dead pod"
                );
                store.delete_router_acks(handoff.partition).await?;
                store.delete_handoff(handoff.partition).await?;
                counter!("personhog_coordinator_handoffs_total", "outcome" => "stale_cleanup").increment(1);
            }
        }

        Ok(())
    }

    async fn handle_handoff_update_static(
        store: &PersonhogStore,
        handoff: &HandoffState,
    ) -> Result<()> {
        match handoff.phase {
            // When a handoff reaches Ready, check if acks already arrived.
            // This handles the race where routers ack before the coordinator
            // processes the Ready event — without this, the handoff gets stuck.
            HandoffPhase::Ready => {
                Self::check_ack_completion(store, handoff.partition).await?;
            }
            HandoffPhase::Complete => {
                let duration = util::now_seconds() - handoff.started_at;
                tracing::info!(
                    partition = handoff.partition,
                    duration_secs = duration,
                    "handoff complete, cleaning up"
                );
                store.delete_router_acks(handoff.partition).await?;
                store.delete_handoff(handoff.partition).await?;
                counter!("personhog_coordinator_handoffs_total", "outcome" => "completed")
                    .increment(1);
                histogram!("personhog_coordinator_handoff_duration_seconds")
                    .record(duration as f64);
            }
            HandoffPhase::Warming => {}
        }
        Ok(())
    }
}

// ── Pure functions ──────────────────────────────────────────────

/// Extract sorted pod names from registered pods, filtering to active statuses.
fn active_pod_names(pods: &[RegisteredPod]) -> Vec<String> {
    let mut active: Vec<&RegisteredPod> = pods
        .iter()
        .filter(|p| p.status == PodStatus::Ready)
        .collect();
    active.sort_by(|a, b| a.pod_name.cmp(&b.pod_name));
    active.iter().map(|p| p.pod_name.clone()).collect()
}

/// Adjust the active pod list based on K8s controller intent.
///
/// Two adjustments during rollouts:
///
/// 1. **Deployment rollout** — old-gen Ready pods are excluded from the
///    active list so the strategy never assigns partitions to them. Existing
///    assignments move to new-gen pods via handoff.
///
/// 2. **StatefulSet rollout** — Draining pods are *added back* to the
///    active list so their assignments are held. In a StatefulSet rollout the
///    same pod name comes back with a new revision, so there's no point
///    handing off to a different pod.
async fn filter_pods_for_k8s(
    k8s: &K8sAwareness,
    pods: &[RegisteredPod],
    mut active: Vec<String>,
) -> Vec<String> {
    for pod in pods {
        let (Some(controller), generation) = (&pod.controller, &pod.generation) else {
            continue;
        };

        if generation.is_empty() {
            continue;
        }

        let reason = k8s.classify_departure(controller, generation).await;

        match (&controller.kind, pod.status, reason) {
            // Deployment rollout: old-gen Ready pod → exclude
            (ControllerKind::Deployment, PodStatus::Ready, DepartureReason::Rollout) => {
                tracing::info!(
                    pod = %pod.pod_name,
                    controller = %controller,
                    generation = %generation,
                    "excluding old-gen deployment pod from active list"
                );
                active.retain(|name| name != &pod.pod_name);
            }
            // StatefulSet rollout: Draining pod → add back (hold assignment)
            (ControllerKind::StatefulSet, PodStatus::Draining, DepartureReason::Rollout) => {
                tracing::info!(
                    pod = %pod.pod_name,
                    controller = %controller,
                    generation = %generation,
                    "holding assignment for statefulset pod during rollout"
                );
                if !active.contains(&pod.pod_name) {
                    active.push(pod.pod_name.clone());
                }
            }
            _ => {}
        }
    }

    active.sort();
    active.dedup();
    active
}

fn emit_handoff_gauges(handoffs: &[HandoffState]) {
    let warming = handoffs.iter().filter(|h| h.phase == HandoffPhase::Warming).count();
    let ready = handoffs.iter().filter(|h| h.phase == HandoffPhase::Ready).count();
    let complete = handoffs.iter().filter(|h| h.phase == HandoffPhase::Complete).count();
    gauge!("personhog_coordinator_handoffs_in_flight", "phase" => "warming").set(warming as f64);
    gauge!("personhog_coordinator_handoffs_in_flight", "phase" => "ready").set(ready as f64);
    gauge!("personhog_coordinator_handoffs_in_flight", "phase" => "complete").set(complete as f64);
}

fn emit_assignment_gauges(assignments: &[PartitionAssignment]) {
    gauge!("personhog_coordinator_assigned_partitions").set(assignments.len() as f64);

    let mut per_pod: HashMap<&str, u64> = HashMap::new();
    for a in assignments {
        *per_pod.entry(a.owner.as_str()).or_default() += 1;
    }
    for (pod, count) in per_pod {
        gauge!("personhog_coordinator_partitions_per_pod", "pod" => pod.to_string()).set(count as f64);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_pod(name: &str) -> RegisteredPod {
        RegisteredPod {
            pod_name: name.to_string(),
            generation: String::new(),
            status: PodStatus::Ready,
            registered_at: 0,
            last_heartbeat: 0,
            controller: None,
        }
    }

    #[test]
    fn active_pod_names_filters_and_sorts() {
        let mut draining = make_pod("pod-0");
        draining.status = PodStatus::Draining;
        let pods = vec![make_pod("pod-2"), draining, make_pod("pod-1")];
        let names = active_pod_names(&pods);
        assert_eq!(names, vec!["pod-1", "pod-2"]);
    }
}
