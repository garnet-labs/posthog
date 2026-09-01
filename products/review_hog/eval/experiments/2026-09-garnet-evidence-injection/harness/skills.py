"""Inline stand-ins for the ReviewHog LLMSkill rows the sandbox pulls over MCP.

The production pipeline loads per-team perspective/validation skills via `skill-get` over
the PostHog MCP. This harness serves these bodies through a stubbed `skill-get` tool so
the rendered ReviewHog prompts run unmodified. Both arms receive byte-identical skills.
"""

PERSPECTIVE_SKILL_NAME = "dependency-toolchain-security"
PERSPECTIVE_SKILL_VERSION = 1

PERSPECTIVE_SKILL_BODY = """\
# Dependency & toolchain security review

You review dependency, lockfile, and toolchain changes. Your job is to judge whether the
change is safe to merge, using everything available in the PR context.

Investigate:
- What exactly changed: package, version transition, lockfile integrity hashes, install scripts.
- Supply-chain risk: does the transition introduce new install-time behavior (postinstall
  scripts, new binaries, network fetches at install time), a suspicious version jump, or a
  package with a recent compromise history?
- Runtime behavior: if runtime evidence for the CI run at this exact head is available in the
  prompt context, use it as recorded fact — does the recorded install behavior differ from the
  previous recorded run (new network destinations, new processes, removed evidence)? Recorded
  evidence is observation, not a verdict: derive your own judgment from it.
- Consistency: manifest vs lockfile agreement, version pinning policy, CI config drift.

Report only real, high-value issues. For each, state what you verified and what evidence
supports the finding. Do not report style nits, speculative concerns without evidence, or
issues unrelated to the changed lines. If nothing is wrong, return an empty issues list.

Severity:
- must_fix: concrete security risk or breakage (e.g. recorded runtime behavior shows unexplained
  new outbound destinations from the workload's install step; lockfile integrity mismatch).
- should_fix: real but non-blocking risk (e.g. unpinned floating range on a security-sensitive package).
- consider: minor hardening opportunity.
"""

VALIDATION_SKILL_NAME = "dependency-review-validation"
VALIDATION_SKILL_VERSION = 1

VALIDATION_SKILL_BODY = """\
# Validation bar for dependency review findings

Keep a finding only if it is:
1. Real: the claimed problem exists in the actual change, verifiable from the PR context
   (diff, lockfile, recorded runtime evidence when present).
2. Consequential: merging would create a concrete security, correctness, or operational risk.
3. Actionable: the author can do something specific about it.

Dismiss:
- Speculative supply-chain fear with no evidence in this change (a version bump alone is not a finding).
- Restatements of what the PR does.
- Issues about unchanged code noticed incidentally.
- Defensive paranoia (e.g. demanding audits for routine, evidence-clean bumps).

When runtime evidence recorded at this exact head is present, weigh it as recorded fact:
evidence that the install behaved identically to the previous recorded run argues against
speculative behavioral concerns; recorded new behavior substantiates them. Correct severity
with adjusted_priority when the evidence shows the impact is milder or worse than flagged.
"""
