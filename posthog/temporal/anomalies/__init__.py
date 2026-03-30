from posthog.temporal.anomalies.activities import (
    cleanup_anomaly_scores,
    discover_anomaly_insights,
    fetch_insights_due_for_scoring,
    fetch_insights_needing_training,
    score_insight,
    train_insight,
)
from posthog.temporal.anomalies.workflows import (
    ScoreAnomaliesWorkflow,
    ScoreInsightWorkflow,
    TrainAnomaliesWorkflow,
    TrainInsightWorkflow,
)

WORKFLOWS = [TrainAnomaliesWorkflow, TrainInsightWorkflow, ScoreAnomaliesWorkflow, ScoreInsightWorkflow]

ACTIVITIES = [
    discover_anomaly_insights,
    fetch_insights_needing_training,
    train_insight,
    fetch_insights_due_for_scoring,
    score_insight,
    cleanup_anomaly_scores,
]
