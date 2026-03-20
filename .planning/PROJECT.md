# Onboarding Product Selection — Card Stack Variant

## What This Is

A new "card stack" variant for the onboarding product selection screen in PostHog. Instead of showing all products at once (control) or one product at a time linearly (simplified), users swipe through a stack of product cards — accepting or rejecting each — creating an engaging, exploratory selection experience inspired by trading card mechanics.

## Core Value

Users explore and actively choose products through an engaging card-swiping interaction that encourages discovery while keeping decisions simple (one product at a time).

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Multi-variant feature flag `onboarding-product-selection-variant` with control/simplified/card-stack variants
- [ ] Card stack UI with swipeable product cards in a visible stack
- [ ] Swipe right to accept, swipe left to reject interaction
- [ ] Accepted/rejected card deck display at bottom of screen
- [ ] Animated card transitions (fly into decks)
- [ ] Trading card visual design (PostHog brand, not dating-app aesthetic)
- [ ] User-centric, use-case-oriented card content (matching simplified variant pattern)
- [ ] Replace existing simplified experiment flag with the new multi-variant flag
- [ ] Mobile-friendly touch swiping and desktop drag/click support

### Out of Scope

- Changing the control (original) product selection variant — preserve as-is
- Changing the simplified variant behavior — preserve as-is
- Backend changes to product selection logic — this is purely UI/UX
- A/B test statistical analysis tooling — use existing PostHog experiments

## Context

- Experiment 362270 tested a simplified one-product-at-a-time variant against the original multi-product grid
- The simplified variant shows promise: single-product focus makes decisions easier
- Problem: users tend to skip the screen without exploring when shown one product at a time
- Goal: keep the one-at-a-time decision simplicity but incentivize exploration through engagement
- The card stack/swiping metaphor adds gamification that encourages going through all cards
- Visual direction: trading cards, not Tinder — collectible feel, not dating-app feel
- PostHog brand: bold, playful, hedgehog mascots, dark theme compatible

## Constraints

- **Tech stack**: React/TypeScript frontend, existing onboarding flow infrastructure
- **Feature flag**: Must use PostHog feature flags (multi-variant) for experiment control
- **Brand**: Must follow PostHog brand guidelines — trading card aesthetic, not dating-app
- **Compatibility**: Must work alongside existing control and simplified variants without breaking them
- **Performance**: Card animations must be smooth (60fps), no layout shift on load

## Key Decisions

| Decision                                              | Rationale                                                                                 | Outcome   |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- | --------- |
| Trading card aesthetic over Tinder-style              | Avoid relationship/dating connotations; trading cards feel collectible and fun            | — Pending |
| Multi-variant flag replacing existing simplified flag | Cleaner experiment management with one flag controlling all variants                      | — Pending |
| Bottom deck layout for accepted/rejected cards        | Provides visual feedback and sense of progress; horizontally overlapping cards save space | — Pending |

---

_Last updated: 2026-03-20 after initialization_
