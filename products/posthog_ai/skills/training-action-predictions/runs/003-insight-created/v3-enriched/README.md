# v3: Enriched (17 features)

AUC-ROC: **0.883** | Features: 17 (5 generic + 4 engagement + 4 query events + 4 person properties)

Added to the strong features from v1:

- Query events: `query_executed`, `query_completed`, `taxonomic_search`, `definition_hovered`
- Person properties: `team_member_count`, `project_count`, `organization_count`, `completed_onboarding`

**Result**: AUC dropped from 0.889 → 0.883. The new features didn't help:

- Query events are too correlated with `events_30d` (general activity) — redundant signal
- Person properties (team size, project count) don't predict insight creation behavior well — static org attributes are less predictive than behavioral signals for this target
- `query_completed` showed some promise (0.078 importance) but not enough to offset the noise from the others

**HogQL note**: Person properties in GROUP BY queries require `any()` aggregate wrapper. Also `toFloatOrDefault` needs `0.0` not `0` as the default (type must match).
