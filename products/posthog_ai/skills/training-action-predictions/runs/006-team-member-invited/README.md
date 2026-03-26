# Run 006: Team member invited

**Date**: 2026-03-26
**Target**: `team member invited` (simple named event)
**Population**: All identified users with ≥5 events
**Winner**: v1 baseline (20 features, AUC 0.893)

## What we predicted

P(identified user invites a team member within 14 days) on PostHog prod project 2.

Simple event, 1% base rate among identified users, ~6K positives — clean target with plenty of data. No population filtering needed.

## Iteration comparison

| Variant     | Features | AUC-ROC | AUC-PR | Key finding                                    |
| ----------- | -------- | ------- | ------ | ---------------------------------------------- |
| v1-baseline | 20       | 0.893   | 0.843  | Continuation model — `prior_invites` dominates |

## Key learnings

1. **This is a continuation prediction, and that's OK.** The model mostly learns "people who already invited will invite again" (`prior_invites` at 0.232 importance). This is valid — not every prediction needs to be adoption-from-cold. The agent should _document_ whether a model is continuation vs adoption in the model card, not always filter it out.

2. **The adoption vs continuation distinction is about framing, not correctness.** A continuation model is useful for: targeting expansion campaigns at users likely to grow their team, predicting org growth trajectory, identifying "champions" who repeatedly bring in teammates. An adoption model would answer a different question: which solo users will invite their first teammate?

3. **Simple named events are the easiest targets.** No subquery, no LIKE, direct `event = 'X'` match. Clean label, fast query, no HogQL gymnastics. The skill should prefer these when available.

4. **High base rate in the sample (40%) is an artifact of ORDER BY label DESC.** True rate is ~1%, but balanced sampling + ORDER BY inflates it. The model handles this via isotonic calibration + scale_pos_weight.
