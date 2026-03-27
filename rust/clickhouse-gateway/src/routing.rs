use std::sync::atomic::{AtomicUsize, Ordering};

use crate::config::Config;

/// The type of workload determines which ClickHouse cluster receives the query.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Workload {
    Online,
    Offline,
    Logs,
    Endpoints,
    Default,
}

impl Workload {
    pub fn from_str_value(s: &str) -> Result<Self, String> {
        match s.to_uppercase().as_str() {
            "ONLINE" => Ok(Workload::Online),
            "OFFLINE" => Ok(Workload::Offline),
            "LOGS" => Ok(Workload::Logs),
            "ENDPOINTS" => Ok(Workload::Endpoints),
            "DEFAULT" => Ok(Workload::Default),
            other => Err(format!("unknown workload: {other}")),
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Workload::Online => "ONLINE",
            Workload::Offline => "OFFLINE",
            Workload::Logs => "LOGS",
            Workload::Endpoints => "ENDPOINTS",
            Workload::Default => "DEFAULT",
        }
    }
}

/// Routes queries to the appropriate ClickHouse cluster using round-robin
/// selection within each workload's host list.
pub struct WorkloadRouter {
    online_hosts: Vec<String>,
    offline_hosts: Vec<String>,
    logs_hosts: Vec<String>,
    endpoints_hosts: Vec<String>,
    online_counter: AtomicUsize,
    offline_counter: AtomicUsize,
    logs_counter: AtomicUsize,
    endpoints_counter: AtomicUsize,
}

impl WorkloadRouter {
    pub fn from_config(config: &Config) -> Self {
        Self {
            online_hosts: config.online_hosts(),
            offline_hosts: config.offline_hosts(),
            logs_hosts: config.logs_hosts(),
            endpoints_hosts: config.endpoints_hosts(),
            online_counter: AtomicUsize::new(0),
            offline_counter: AtomicUsize::new(0),
            logs_counter: AtomicUsize::new(0),
            endpoints_counter: AtomicUsize::new(0),
        }
    }

    /// Select a host for the given workload using round-robin.
    pub fn route(&self, workload: &Workload) -> &str {
        let (hosts, counter) = match workload {
            Workload::Online | Workload::Default => (&self.online_hosts, &self.online_counter),
            Workload::Offline => (&self.offline_hosts, &self.offline_counter),
            Workload::Logs => (&self.logs_hosts, &self.logs_counter),
            Workload::Endpoints => (&self.endpoints_hosts, &self.endpoints_counter),
        };

        if hosts.is_empty() {
            // Fallback — should never happen with valid config
            return "http://localhost:8123";
        }

        let idx = counter.fetch_add(1, Ordering::Relaxed) % hosts.len();
        &hosts[idx]
    }

    /// Returns all hosts for a given workload (useful for health checks).
    pub fn hosts_for(&self, workload: &Workload) -> &[String] {
        match workload {
            Workload::Online | Workload::Default => &self.online_hosts,
            Workload::Offline => &self.offline_hosts,
            Workload::Logs => &self.logs_hosts,
            Workload::Endpoints => &self.endpoints_hosts,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_router() -> WorkloadRouter {
        WorkloadRouter {
            online_hosts: vec![
                "http://online1:8123".to_string(),
                "http://online2:8123".to_string(),
            ],
            offline_hosts: vec![
                "http://offline1:8123".to_string(),
                "http://offline2:8123".to_string(),
                "http://offline3:8123".to_string(),
            ],
            logs_hosts: vec!["http://logs1:8123".to_string()],
            endpoints_hosts: vec!["http://endpoints1:8123".to_string()],
            online_counter: AtomicUsize::new(0),
            offline_counter: AtomicUsize::new(0),
            logs_counter: AtomicUsize::new(0),
            endpoints_counter: AtomicUsize::new(0),
        }
    }

    #[test]
    fn test_route_online_round_robin() {
        let router = make_router();
        assert_eq!(router.route(&Workload::Online), "http://online1:8123");
        assert_eq!(router.route(&Workload::Online), "http://online2:8123");
        assert_eq!(router.route(&Workload::Online), "http://online1:8123");
    }

    #[test]
    fn test_route_offline() {
        let router = make_router();
        assert_eq!(router.route(&Workload::Offline), "http://offline1:8123");
        assert_eq!(router.route(&Workload::Offline), "http://offline2:8123");
        assert_eq!(router.route(&Workload::Offline), "http://offline3:8123");
        assert_eq!(router.route(&Workload::Offline), "http://offline1:8123");
    }

    #[test]
    fn test_route_default_uses_online() {
        let router = make_router();
        let host = router.route(&Workload::Default);
        assert!(host.contains("online"));
    }

    #[test]
    fn test_workload_from_str() {
        assert_eq!(
            Workload::from_str_value("ONLINE").unwrap(),
            Workload::Online
        );
        assert_eq!(
            Workload::from_str_value("offline").unwrap(),
            Workload::Offline
        );
        assert_eq!(Workload::from_str_value("Logs").unwrap(), Workload::Logs);
        assert_eq!(
            Workload::from_str_value("ENDPOINTS").unwrap(),
            Workload::Endpoints
        );
        assert!(Workload::from_str_value("INVALID").is_err());
    }

    #[test]
    fn test_hosts_for() {
        let router = make_router();
        assert_eq!(router.hosts_for(&Workload::Online).len(), 2);
        assert_eq!(router.hosts_for(&Workload::Offline).len(), 3);
        assert_eq!(router.hosts_for(&Workload::Logs).len(), 1);
        assert_eq!(router.hosts_for(&Workload::Endpoints).len(), 1);
    }
}
