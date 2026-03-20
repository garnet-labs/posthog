# Requirements: Onboarding Card Stack Variant

**Defined:** 2026-03-20
**Core Value:** Users explore and actively choose products through an engaging card-swiping interaction that encourages discovery while keeping decisions simple

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Feature Flag

- [ ] **FLAG-01**: Multi-variant feature flag `onboarding-product-selection-variant` exists with variants: control, simplified, card-stack
- [ ] **FLAG-02**: ProductSelection component routes to the correct variant based on the new flag value
- [ ] **FLAG-03**: Old `onboarding-simplified-product-selection` flag is replaced by the new multi-variant flag
- [ ] **FLAG-04**: `RecommendationSource` type includes `'card-stack'` for analytics attribution

### Card Interaction

- [ ] **CARD-01**: User can swipe a card right to accept or left to reject a product
- [ ] **CARD-02**: Card tilts/rotates proportionally to drag distance during swipe
- [ ] **CARD-03**: Card snaps back with spring animation when released below the swipe threshold
- [ ] **CARD-04**: Card flies out to the accepted or rejected pile when swipe exceeds threshold
- [ ] **CARD-05**: Directional overlay (accept/reject stamp) fades in proportionally during drag
- [ ] **CARD-06**: User can accept or reject via visible buttons (single-pointer alternative, WCAG 2.5.7)
- [ ] **CARD-07**: User can accept or reject via keyboard (ArrowRight = accept, ArrowLeft = reject)
- [ ] **CARD-08**: `touch-action: none` applied on drag surface to prevent scroll-swipe conflicts on mobile

### Card Stack Display

- [ ] **STACK-01**: Cards are displayed in a visible stack with 2-3 cards behind the top card (depth illusion)
- [ ] **STACK-02**: Progress indicator shows cards remaining (e.g., "3 of 10")
- [ ] **STACK-03**: Card content includes: product color accent, hedgehog mascot, product name, user-centric description, capabilities list, social proof

### Deck Piles

- [ ] **PILE-01**: Accepted cards accumulate in a visible pile at the bottom-right of the screen
- [ ] **PILE-02**: Rejected cards accumulate in a visible pile at the bottom-left of the screen
- [ ] **PILE-03**: Pile cards are laid out horizontally with slight overlap (fanned/stacked appearance)
- [ ] **PILE-04**: Pile shows product icon thumbnails as card previews

### End State

- [ ] **END-01**: End-of-deck view displays when all cards have been swiped
- [ ] **END-02**: End-of-deck view shows the list of accepted products
- [ ] **END-03**: "Continue" CTA proceeds to onboarding flow with selected products

### Visual Design

- [ ] **VIS-01**: Card design follows trading card aesthetic (collectible feel, not dating-app)
- [ ] **VIS-02**: Accept/reject feedback uses PostHog-branded icons (checkmark/X from @posthog/icons), not Tinder-style hearts/fire
- [ ] **VIS-03**: All animations use only transform and opacity (no layout-triggering properties) for 60fps performance
- [ ] **VIS-04**: Design works on mobile (360px+) and desktop

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Polish

- **POLISH-01**: Undo last swipe (single level) with brief "Undo" button after each swipe
- **POLISH-02**: Pile animation when a card lands (brief scale pulse)
- **POLISH-03**: Entrance animation with staggered card deal-in on mount
- **POLISH-04**: Haptic feedback on card commit (navigator.vibrate)

### Optimization

- **OPT-01**: Deck pre-filtering based on recommendation signals
- **OPT-02**: Interactive rejected pile (drag back from rejected pile to re-accept)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature                                                | Reason                                                            |
| ------------------------------------------------------ | ----------------------------------------------------------------- |
| Tinder visual language (hearts, fire, "It's a Match!") | B2B developer tool — dating-app connotations undermine trust      |
| Swipe up/down actions                                  | Adds complexity with no clear product-selection meaning           |
| Super-like / special swipe variants                    | Gamification beyond core loop adds confusion during onboarding    |
| Score / compatibility rating framing                   | Dating-app framing explicitly prohibited by project direction     |
| Sound effects                                          | Browser audio during onboarding is jarring and unexpected         |
| Gamification score / leaderboard                       | Onboarding flow, not a game — metrics invisible to user           |
| Heavy 3D perspective / holographic foil                | Trading card aesthetic informs tone, not literal card CSS effects |
| Skip-all button                                        | Defeats purpose of card-stack variant — exploration is the point  |
| Deck reordering / sorting                              | Unnecessary complexity; fixed recommended order                   |
| Swipe sensitivity settings                             | Over-engineering; calibrate threshold once                        |
| Backend changes to product selection logic             | This is purely UI/UX                                              |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase   | Status  |
| ----------- | ------- | ------- |
| FLAG-01     | Phase 1 | Pending |
| FLAG-02     | Phase 1 | Pending |
| FLAG-03     | Phase 1 | Pending |
| FLAG-04     | Phase 1 | Pending |
| CARD-01     | Phase 2 | Pending |
| CARD-02     | Phase 2 | Pending |
| CARD-03     | Phase 2 | Pending |
| CARD-04     | Phase 2 | Pending |
| CARD-05     | Phase 2 | Pending |
| CARD-06     | Phase 2 | Pending |
| CARD-07     | Phase 2 | Pending |
| CARD-08     | Phase 2 | Pending |
| STACK-01    | Phase 2 | Pending |
| STACK-02    | Phase 2 | Pending |
| STACK-03    | Phase 3 | Pending |
| PILE-01     | Phase 2 | Pending |
| PILE-02     | Phase 2 | Pending |
| PILE-03     | Phase 3 | Pending |
| PILE-04     | Phase 3 | Pending |
| END-01      | Phase 2 | Pending |
| END-02      | Phase 2 | Pending |
| END-03      | Phase 2 | Pending |
| VIS-01      | Phase 3 | Pending |
| VIS-02      | Phase 3 | Pending |
| VIS-03      | Phase 2 | Pending |
| VIS-04      | Phase 3 | Pending |

**Coverage:**

- v1 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0 ✓

---

_Requirements defined: 2026-03-20_
_Last updated: 2026-03-20 after initial definition_
