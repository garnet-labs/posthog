# PostHog PR #71294 replay

This fork-only fixture tests one cold-read hypothesis against the exact public
base and head commits of `PostHog/posthog#71294`.

- Base: `507f13ecc15a2e4ed314ba73612b302da6f2d3b8`
- Head: `88eb5feb56242ff2eb7f6a3d907bb38f62966e93`
- Mutation target: `garnet-labs/posthog`

The probe uses Django 5.2 QuerySets with the source filters and selection shapes
from those commits. It tests both insertion orders for a legacy `type=NULL`
String row and a current `type=EVENT` Numeric row.

The output is deliberately narrow. It can show the ORM selection and query
count under the isolated fixture, but it is not a full PostHog, HogQL, or
PostgreSQL integration test.

The `exp/pr-71294-replay-control` branch changes only this note. Its PR runs the
base subject, establishing a control before the exact two-file head patch runs.
The control is then promoted in place, preserving the PR identity for comparison.
