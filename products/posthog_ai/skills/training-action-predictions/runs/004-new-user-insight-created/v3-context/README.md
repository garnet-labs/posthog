# v3: Acquisition/onboarding context (18 features)

AUC-ROC: **0.746** | Features: 18 (v1 core + onboarding product selection + signup context + velocity)

Hypothesis: what users chose during onboarding (product_analytics vs session_replay vs web_analytics) and how they signed up (EU vs US, social vs regular) would add signal for new user activation.

**EDA showed clear signal**: users who onboarded into product_analytics activated at 12.9% vs 7.5% baseline. EU regular signups at 9.8% vs US social at 6.9%.

**Result**: AUC 0.746 — slightly BELOW v1 (0.753). The context features didn't help.

**Why the EDA signal didn't translate to model improvement**:

1. **Onboarding product selection is too uniform** — the vast majority of users who complete onboarding select product_analytics anyway. It's the default/primary product. So `onboarded_product_analytics` is essentially "did they complete onboarding" which is already captured by `completed_onboarding`.

2. **Signup method signal is weak** — EU vs US and social vs regular have ~2% activation rate differences. This is statistically real but too small to move AUC when behavioral features (insight_viewed, events_7d) have much stronger per-user signal.

3. **More features, more noise** — 18 features for a thin-data population (new users with ≤14 days). The run 003 lesson applies: when you add features that don't carry strong signal, you dilute the model.

**Notable**: `onboarded_web_analytics` (0.052) showed slightly more importance than `onboarded_product_analytics` (0.037). Web analytics users may be a slightly different population — worth investigating in future.

**Takeaway**: for new user activation, behavioral features (what they DID) beat context features (who they ARE / how they arrived) by a wide margin. Context features might matter more when there's zero behavioral data (scoring at the moment of signup).
