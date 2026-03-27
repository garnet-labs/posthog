use envconfig::Envconfig;

#[derive(Envconfig, Clone, Debug)]
pub struct Config {
    #[envconfig(from = "GATEWAY_HOST", default = "0.0.0.0")]
    pub host: String,

    #[envconfig(from = "GATEWAY_PORT", default = "3100")]
    pub port: u16,

    #[envconfig(from = "CLICKHOUSE_ONLINE_HOSTS", default = "http://localhost:8123")]
    pub clickhouse_online_hosts: String,

    #[envconfig(from = "CLICKHOUSE_OFFLINE_HOSTS", default = "http://localhost:8123")]
    pub clickhouse_offline_hosts: String,

    #[envconfig(from = "CLICKHOUSE_LOGS_HOSTS", default = "http://localhost:8123")]
    pub clickhouse_logs_hosts: String,

    #[envconfig(from = "CLICKHOUSE_ENDPOINTS_HOSTS", default = "http://localhost:8123")]
    pub clickhouse_endpoints_hosts: String,

    // Per-workload concurrency limits
    #[envconfig(from = "GATEWAY_ONLINE_MAX_CONCURRENT", default = "50")]
    pub online_max_concurrent: u32,

    #[envconfig(from = "GATEWAY_ONLINE_MAX_EXECUTION_TIME", default = "30")]
    pub online_max_execution_time: u32,

    #[envconfig(from = "GATEWAY_OFFLINE_MAX_CONCURRENT", default = "10")]
    pub offline_max_concurrent: u32,

    #[envconfig(from = "GATEWAY_OFFLINE_MAX_EXECUTION_TIME", default = "600")]
    pub offline_max_execution_time: u32,

    #[envconfig(from = "GATEWAY_LOGS_MAX_CONCURRENT", default = "20")]
    pub logs_max_concurrent: u32,

    #[envconfig(from = "GATEWAY_LOGS_MAX_EXECUTION_TIME", default = "60")]
    pub logs_max_execution_time: u32,

    #[envconfig(from = "GATEWAY_ENDPOINTS_MAX_CONCURRENT", default = "30")]
    pub endpoints_max_concurrent: u32,

    #[envconfig(from = "GATEWAY_ENDPOINTS_MAX_EXECUTION_TIME", default = "120")]
    pub endpoints_max_execution_time: u32,

    // Service token for authenticating callers. Requests must send
    // `Authorization: Bearer <token>`.
    #[envconfig(from = "GATEWAY_SERVICE_TOKEN", default = "")]
    pub service_token: String,

    // When true, auth is disabled even if service_token is empty.
    // Intended for local development only — production deployments must
    // set GATEWAY_SERVICE_TOKEN and leave this false (default).
    #[envconfig(from = "GATEWAY_AUTH_DISABLED", default = "false")]
    pub auth_disabled: bool,

    // Redis URL for query result caching (optional — cache is disabled when unset)
    #[envconfig(from = "GATEWAY_REDIS_URL")]
    pub redis_url: Option<String>,

    // EXPLAIN-based cost estimation (opt-in, ONLINE workload only)
    #[envconfig(from = "GATEWAY_EXPLAIN_ENABLED", default = "true")]
    pub explain_enabled: bool,

    // Metrics export
    #[envconfig(from = "GATEWAY_METRICS_PORT", default = "9090")]
    pub metrics_port: u16,

    #[envconfig(from = "GATEWAY_LOG_LEVEL", default = "info")]
    pub log_level: String,
}

impl Config {
    /// Validate that auth is properly configured.
    ///
    /// Panics at startup if `GATEWAY_SERVICE_TOKEN` is empty and
    /// `GATEWAY_AUTH_DISABLED` is not explicitly set to true. This prevents
    /// accidentally running without authentication in production.
    pub fn validate_auth(&self) {
        if self.auth_disabled {
            tracing::warn!("GATEWAY_AUTH_DISABLED=true — authentication is disabled. Do not use in production.");
            return;
        }
        if self.service_token.is_empty() {
            panic!(
                "GATEWAY_SERVICE_TOKEN is empty and GATEWAY_AUTH_DISABLED is not set. \
                 Set GATEWAY_SERVICE_TOKEN to a non-empty value for production, \
                 or set GATEWAY_AUTH_DISABLED=true for local development."
            );
        }
    }

    /// Parse a comma-separated host string into a list of host URLs.
    pub fn parse_hosts(hosts: &str) -> Vec<String> {
        hosts
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect()
    }

    pub fn online_hosts(&self) -> Vec<String> {
        Self::parse_hosts(&self.clickhouse_online_hosts)
    }

    pub fn offline_hosts(&self) -> Vec<String> {
        Self::parse_hosts(&self.clickhouse_offline_hosts)
    }

    pub fn logs_hosts(&self) -> Vec<String> {
        Self::parse_hosts(&self.clickhouse_logs_hosts)
    }

    pub fn endpoints_hosts(&self) -> Vec<String> {
        Self::parse_hosts(&self.clickhouse_endpoints_hosts)
    }

    /// Returns (max_concurrent, max_execution_time) for a given workload.
    pub fn limits_for_workload(&self, workload: &crate::routing::Workload) -> (u32, u32) {
        match workload {
            crate::routing::Workload::Online => {
                (self.online_max_concurrent, self.online_max_execution_time)
            }
            crate::routing::Workload::Offline => {
                (self.offline_max_concurrent, self.offline_max_execution_time)
            }
            crate::routing::Workload::Logs => {
                (self.logs_max_concurrent, self.logs_max_execution_time)
            }
            crate::routing::Workload::Endpoints => (
                self.endpoints_max_concurrent,
                self.endpoints_max_execution_time,
            ),
            crate::routing::Workload::Default => {
                (self.online_max_concurrent, self.online_max_execution_time)
            }
        }
    }
}

/// Helper to build a Config for tests with auth disabled.
pub fn test_config() -> Config {
    Config {
        host: "0.0.0.0".to_string(),
        port: 3100,
        clickhouse_online_hosts: "http://localhost:8123".to_string(),
        clickhouse_offline_hosts: "http://localhost:8123".to_string(),
        clickhouse_logs_hosts: "http://localhost:8123".to_string(),
        clickhouse_endpoints_hosts: "http://localhost:8123".to_string(),
        online_max_concurrent: 50,
        online_max_execution_time: 30,
        offline_max_concurrent: 10,
        offline_max_execution_time: 600,
        logs_max_concurrent: 20,
        logs_max_execution_time: 60,
        endpoints_max_concurrent: 30,
        endpoints_max_execution_time: 120,
        service_token: String::new(),
        auth_disabled: true,
        redis_url: None,
        explain_enabled: true,
        metrics_port: 9090,
        log_level: "info".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_hosts_single() {
        let hosts = Config::parse_hosts("http://localhost:8123");
        assert_eq!(hosts, vec!["http://localhost:8123"]);
    }

    #[test]
    fn test_parse_hosts_multiple() {
        let hosts = Config::parse_hosts("http://ch1:8123,http://ch2:8123,http://ch3:8123");
        assert_eq!(
            hosts,
            vec!["http://ch1:8123", "http://ch2:8123", "http://ch3:8123"]
        );
    }

    #[test]
    fn test_parse_hosts_with_whitespace() {
        let hosts = Config::parse_hosts("http://ch1:8123 , http://ch2:8123");
        assert_eq!(hosts, vec!["http://ch1:8123", "http://ch2:8123"]);
    }

    #[test]
    fn test_parse_hosts_empty() {
        let hosts = Config::parse_hosts("");
        assert!(hosts.is_empty());
    }

    #[test]
    #[should_panic(expected = "GATEWAY_SERVICE_TOKEN is empty")]
    fn test_validate_auth_panics_on_empty_token() {
        let mut config = test_config();
        config.auth_disabled = false;
        config.service_token = String::new();
        config.validate_auth();
    }

    #[test]
    fn test_validate_auth_ok_with_token() {
        let mut config = test_config();
        config.auth_disabled = false;
        config.service_token = "my-secret".to_string();
        config.validate_auth();
    }

    #[test]
    fn test_validate_auth_ok_with_auth_disabled() {
        let mut config = test_config();
        config.auth_disabled = true;
        config.service_token = String::new();
        config.validate_auth();
    }
}
