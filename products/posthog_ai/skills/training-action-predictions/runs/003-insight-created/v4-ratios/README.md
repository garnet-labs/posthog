# v4: Behavioral ratios (11 features)

AUC-ROC: **0.899** | Features: 11 (4 activity + 3 ratios + 3 raw engagement + 1 recency)

Hypothesis: engagement depth ratios (insight_view_ratio, analyze_to_view_ratio, acceleration) would capture user intent better than raw counts alone.

Added to v2's core features:

- `insight_view_ratio` = insight views / total events (engagement depth)
- `dashboard_view_ratio` = dashboard views / total events
- `analyze_to_view_ratio` = insight analyzed / insight viewed (conversion depth)
- `acceleration_7d_vs_prior` = events_7d / events in prior 2 weeks (trajectory)

**Result**: AUC 0.899 — essentially tied with v2 (0.902). The ratios didn't improve the model.

**Why**: XGBoost can learn these ratios implicitly from the raw features. Given `insight_viewed` and `events_total`, the tree can split on thresholds that approximate the ratio. The explicit ratio features are redundant for tree-based models.

However, the ratios did show up with meaningful importance:

- `dashboard_view_ratio` (0.058) — slightly useful
- `analyze_to_view_ratio` (0.058) — conversion depth has signal
- `acceleration_7d_vs_prior` (0.057) — user trajectory has signal

**Takeaway**: For XGBoost, raw features + tree splits ≈ explicit ratios. Ratios might matter more for linear models. The v2 simple model remains the winner — same performance, fewer features.
