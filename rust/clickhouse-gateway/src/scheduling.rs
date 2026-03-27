use serde::{Deserialize, Serialize};
use tracing::warn;

use crate::config::Config;

/// Estimated cost of a query, used for scheduling decisions.
#[derive(Debug, Clone, Serialize)]
pub struct QueryCost {
    /// Relative weight from 0.1 (trivial) to 10.0 (very heavy).
    pub slot_weight: f64,
    /// Estimated rows to read, when available from EXPLAIN.
    pub estimated_rows: u64,
    /// Whether the query uses a primary key index (from EXPLAIN).
    pub uses_index: bool,
    /// How the cost was determined.
    pub method: CostMethod,
}

/// How the cost estimate was produced.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CostMethod {
    /// Ran EXPLAIN PLAN against ClickHouse.
    Explain,
    /// SQL complexity heuristic (pattern matching).
    Heuristic,
    /// Fallback when no analysis was possible.
    Default,
}

/// Intermediate types for deserializing EXPLAIN PLAN JSON output from ClickHouse.
///
/// ClickHouse returns `EXPLAIN PLAN indexes=1, json=1 <query>` as a single row
/// containing a JSON array of plan nodes. Each node may contain an `Indexes`
/// field with primary-key selectivity information we use for cost estimation.
#[derive(Deserialize, Debug)]
#[allow(dead_code)]
struct ExplainPlanNode {
    #[serde(rename = "Node Type")]
    node_type: Option<String>,
    #[serde(rename = "Indexes")]
    indexes: Option<Vec<ExplainIndex>>,
    #[serde(rename = "Parts")]
    parts: Option<u64>,
    #[serde(rename = "ReadType")]
    read_type: Option<String>,
}

#[derive(Deserialize, Debug)]
struct ExplainIndex {
    #[serde(rename = "Type")]
    index_type: Option<String>,
    #[serde(rename = "Initial Granules")]
    initial_granules: Option<u64>,
    #[serde(rename = "Selected Granules")]
    selected_granules: Option<u64>,
}

/// Scheduler provides query cost estimation. For ONLINE workloads it can run
/// EXPLAIN PLAN on ClickHouse to get selectivity data. For other workloads
/// (and as a fallback) it uses a SQL-pattern heuristic.
/// Timeout for EXPLAIN queries — much shorter than the main query timeout.
const EXPLAIN_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);

pub struct Scheduler {
    online_explain_enabled: bool,
    /// Dedicated HTTP client for EXPLAIN with a short timeout, separate from
    /// the main query client so a slow EXPLAIN can't exhaust query connections.
    explain_client: reqwest::Client,
}

impl Scheduler {
    pub fn new(config: &Config) -> Self {
        let explain_client = reqwest::Client::builder()
            .timeout(EXPLAIN_TIMEOUT)
            .pool_max_idle_per_host(2)
            .build()
            .expect("failed to build EXPLAIN HTTP client");

        Self {
            online_explain_enabled: config.explain_enabled,
            explain_client,
        }
    }

    /// Estimate the cost of a query before execution.
    ///
    /// For ONLINE workloads with EXPLAIN enabled, runs `EXPLAIN PLAN` against
    /// the target ClickHouse host using a dedicated client with a 5s timeout.
    /// For all other workloads, or on any EXPLAIN error, falls back to a
    /// heuristic based on SQL structure.
    pub async fn estimate_cost(
        &self,
        _client: &reqwest::Client,
        host: &str,
        sql: &str,
        workload: &str,
    ) -> QueryCost {
        if workload == "ONLINE" && self.online_explain_enabled {
            self.explain_cost(host, sql).await
        } else {
            self.heuristic_cost(sql)
        }
    }

    /// Run `EXPLAIN PLAN indexes=1, json=1` on ClickHouse and parse the result
    /// to estimate query cost from granule selectivity.
    ///
    /// Uses a dedicated HTTP client with a 5s timeout so a slow EXPLAIN never
    /// blocks the main query path or exhausts its connection pool.
    async fn explain_cost(&self, host: &str, sql: &str) -> QueryCost {
        let explain_sql = format!("EXPLAIN PLAN indexes=1, json=1 {sql}");
        let url = format!("{host}/");

        let resp = match self
            .explain_client
            .post(&url)
            .header("Content-Type", "text/plain")
            .body(explain_sql)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => {
                warn!(error = %e, "EXPLAIN request failed, falling back to heuristic");
                return self.heuristic_cost(sql);
            }
        };

        if !resp.status().is_success() {
            warn!(status = %resp.status(), "EXPLAIN returned non-200, falling back to heuristic");
            return self.heuristic_cost(sql);
        }

        let body = match resp.text().await {
            Ok(b) => b,
            Err(e) => {
                warn!(error = %e, "failed to read EXPLAIN response body");
                return self.heuristic_cost(sql);
            }
        };

        self.parse_explain_response(&body)
            .unwrap_or_else(|| self.heuristic_cost(sql))
    }

    /// Parse the ClickHouse EXPLAIN PLAN JSON output into a QueryCost.
    ///
    /// The response is a JSON array of plan nodes. We look for the PrimaryKey
    /// index entry to compute the selectivity ratio (selected / initial granules).
    /// A low ratio means the query is well-indexed and cheap; a high ratio means
    /// it scans most of the data.
    fn parse_explain_response(&self, body: &str) -> Option<QueryCost> {
        let nodes: Vec<ExplainPlanNode> = serde_json::from_str(body).ok()?;

        let mut total_initial: u64 = 0;
        let mut total_selected: u64 = 0;
        let mut found_index = false;
        let mut _total_parts: u64 = 0;

        for node in &nodes {
            if let Some(parts) = node.parts {
                _total_parts += parts;
            }

            if let Some(indexes) = &node.indexes {
                for idx in indexes {
                    let is_primary = idx
                        .index_type
                        .as_deref()
                        .map(|t| t == "PrimaryKey")
                        .unwrap_or(false);
                    if is_primary {
                        if let (Some(initial), Some(selected)) =
                            (idx.initial_granules, idx.selected_granules)
                        {
                            total_initial += initial;
                            total_selected += selected;
                            found_index = true;
                        }
                    }
                }
            }
        }

        if !found_index || total_initial == 0 {
            return None;
        }

        // selectivity: 0.0 (perfect index) to 1.0 (full scan)
        let selectivity = total_selected as f64 / total_initial as f64;

        // Map selectivity to slot weight:
        //   0.0  -> 0.1  (trivial, highly selective)
        //   0.01 -> ~0.2
        //   0.1  -> ~1.1
        //   0.5  -> ~5.1
        //   1.0  -> 10.0 (full scan)
        let weight = (0.1 + selectivity * 9.9).min(10.0);

        // Rough row estimate: 8192 rows per granule (ClickHouse default)
        let estimated_rows = total_selected * 8192;

        Some(QueryCost {
            slot_weight: weight,
            estimated_rows,
            uses_index: true,
            method: CostMethod::Explain,
        })
    }

    /// Heuristic cost based on SQL complexity patterns.
    ///
    /// Cheap queries (DESCRIBE, SHOW, system tables) get low weight. JOINs,
    /// missing WHERE clauses, GROUP BY, and DISTINCT each increase cost.
    pub fn heuristic_cost(&self, sql: &str) -> QueryCost {
        let upper = sql.to_uppercase();
        let mut weight: f64 = 1.0;

        // Metadata queries are cheap
        if upper.starts_with("DESCRIBE")
            || upper.starts_with("SHOW")
            || upper.contains("SYSTEM.COLUMNS")
        {
            return QueryCost {
                slot_weight: 0.1,
                estimated_rows: 0,
                uses_index: true,
                method: CostMethod::Heuristic,
            };
        }

        // SELECT 1 / ping queries are cheap
        if upper.starts_with("SELECT 1") {
            return QueryCost {
                slot_weight: 0.1,
                estimated_rows: 0,
                uses_index: true,
                method: CostMethod::Heuristic,
            };
        }

        // JOINs increase cost
        let join_count = upper.matches(" JOIN ").count();
        weight += join_count as f64 * 1.5;

        // No WHERE clause = full scan
        if !upper.contains("WHERE") {
            weight += 3.0;
        }

        // GROUP BY adds cost
        if upper.contains("GROUP BY") {
            weight += 0.5;
        }

        // DISTINCT adds cost
        if upper.contains("DISTINCT") {
            weight += 0.5;
        }

        // Cap at 10
        weight = weight.min(10.0);

        QueryCost {
            slot_weight: weight,
            estimated_rows: 0,
            uses_index: false,
            method: CostMethod::Heuristic,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_scheduler() -> Scheduler {
        Scheduler {
            online_explain_enabled: true,
            explain_client: reqwest::Client::builder()
                .timeout(EXPLAIN_TIMEOUT)
                .build()
                .unwrap(),
        }
    }

    #[test]
    fn test_parse_explain_response_good() {
        let scheduler = make_scheduler();
        let json = serde_json::json!([
            {
                "Node Type": "ReadFromMergeTree",
                "Parts": 5,
                "Indexes": [
                    {
                        "Type": "PrimaryKey",
                        "Initial Granules": 1000,
                        "Selected Granules": 10
                    }
                ]
            }
        ]);

        let cost = scheduler
            .parse_explain_response(&serde_json::to_string(&json).unwrap())
            .unwrap();

        assert_eq!(cost.method, CostMethod::Explain);
        assert!(cost.uses_index);
        assert_eq!(cost.estimated_rows, 10 * 8192);
        // selectivity = 10/1000 = 0.01 -> weight = 0.1 + 0.01*9.9 = 0.199
        assert!((cost.slot_weight - 0.199).abs() < 0.01);
    }

    #[test]
    fn test_parse_explain_response_full_scan() {
        let scheduler = make_scheduler();
        let json = serde_json::json!([
            {
                "Node Type": "ReadFromMergeTree",
                "Parts": 10,
                "Indexes": [
                    {
                        "Type": "PrimaryKey",
                        "Initial Granules": 500,
                        "Selected Granules": 500
                    }
                ]
            }
        ]);

        let cost = scheduler
            .parse_explain_response(&serde_json::to_string(&json).unwrap())
            .unwrap();

        // selectivity = 1.0 -> weight = 10.0
        assert!((cost.slot_weight - 10.0).abs() < 0.01);
    }

    #[test]
    fn test_parse_explain_response_no_index_returns_none() {
        let scheduler = make_scheduler();
        let json = serde_json::json!([
            {
                "Node Type": "ReadFromMergeTree",
                "Parts": 5
            }
        ]);

        let result = scheduler.parse_explain_response(&serde_json::to_string(&json).unwrap());
        assert!(result.is_none());
    }

    #[test]
    fn test_parse_explain_response_invalid_json_returns_none() {
        let scheduler = make_scheduler();
        let result = scheduler.parse_explain_response("not valid json");
        assert!(result.is_none());
    }
}
