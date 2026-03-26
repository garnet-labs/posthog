# v4: Device/platform metadata (15 features)

AUC-ROC: **0.760** | Features: 15 (v1 core + device/OS + velocity helpers)

Hypothesis: mobile users activate at 2x the rate of desktop users (15.9% vs 7.8% from EDA). Device type and OS extracted from `$pageview` event properties (not person properties which are null for server-side signups).

**EDA showed strong signal**: iOS 16.5%, Android 14.8%, Mac 8.8%, Windows 6.6%. Mobile vs Desktop was the strongest metadata split we found.

**Result**: AUC 0.760 — small improvement over v1 (0.753). `is_mac_user` ranked 4th in importance (0.070), higher than several behavioral features. But the overall lift is modest.

**Why the 2x EDA signal gives only +0.007 AUC**:

- The 2x rate difference is a population-level statistic, not a per-user predictor. Many desktop users still activate — device type alone doesn't separate well enough
- XGBoost already captures the behavioral differences that correlate with device type (mobile users tend to have different `events_7d` patterns)
- Binary features (is_mac, has_mobile) have limited splitting power vs continuous behavioral features

**Key finding for the skill**: device/platform metadata from `$pageview` events is accessible and mildly useful. Worth including as cheap features, but behavioral signals remain dominant for activation prediction. The technique of extracting metadata from event properties (not person properties) is important — person properties are often null for server-side events.
