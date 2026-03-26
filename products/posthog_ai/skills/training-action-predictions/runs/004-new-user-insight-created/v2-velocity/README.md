# v2: Velocity features (15 features)

AUC-ROC: **0.908** | Features: 15

Hypothesis: how FAST a new user progresses matters more than whether they did it. Added time-to-milestone features (`days_to_first_insight_view`, `days_to_onboarding`, `days_to_first_event`), activity spread (`active_days`), and multi-product exploration.

**Result**: AUC jumped 0.753 → 0.908, but `days_to_first_insight_view` carried 40.6% importance — suspicious.

**Ablation test**: removed `days_to_first_insight_view` → AUC dropped to 0.772. That one feature accounted for 0.13 AUC points.

**Leakage analysis**: `insight viewed` (viewing) ≠ `insight created` (creating), so it's not technically the label in disguise. But it's the closest upstream step — the user is already in the insights UI. For new user activation, "how quickly did they discover insights?" is arguably a legitimate signal, but the model becomes heavily dependent on a single feature.

**Other velocity features that helped** (v1 → ablation comparison, 0.753 → 0.772):

- `has_data_flowing` (0.110) — org ingested events (prerequisite for insights)
- `active_days` — came back on multiple days (retention signal)
- `days_to_first_event` — speed to getting data in
- `products_explored` — tried multiple product areas

**Recommendation**: the ablation (0.772) is the honest model. The full v2 (0.908) is useful if you accept that "time to first insight view" is a legitimate activation signal rather than leakage. Context-dependent — discuss with stakeholder.
