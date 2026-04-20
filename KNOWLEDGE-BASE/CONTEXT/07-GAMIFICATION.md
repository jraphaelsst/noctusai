# Gamification Philosophy

NoctusAI products embed gamification **subtly** across the user experience. The goal: motivate and delight users without cluttering or infantilizing the UI. Competition numbers, progress toward goals, and achievements are visible — but never noisy.

## Principles

1. **Subtle, never shouty.** No confetti on every click. Use small badges, rank numbers, progress bars, colored dots. Celebrations (toasts, animations) are rate-limited and reserved for real milestones.
2. **Discrete informational icons (ⓘ).** Every gamified metric shows a small info icon. Hover/tap reveals the formula: "Score unificado = pontos de atividade + (VGV × 10/100K)".
3. **Tied to real work.** Every point corresponds to real business activity — captação, visita, venda, sessão, transação. No "logged-in-today" rewards. No fake achievements.
4. **Privacy-aware.** Agents see themselves, leaders see their team, owners see all. Rankings respect hierarchy — an agent never sees other teams' rankings unless explicitly opened.
5. **Role-aware.** Gamification appears differently for each role. Agents see competitive rank. Leaders see team aggregate + agent contributions. Owners see organizational patterns.
6. **Context-aware placement.** Gamification surfaces on pages where it's relevant (dashboard, profile, closings) and is absent where it would distract (settings, admin, data entry forms).
7. **Opt-visible where sensitive.** Some users may want to hide their rank. Respect that.
8. **Owner-tunable.** Scoring rules, point values, and conversion rates are configurable by the tenant owner. No hardcoded business logic.

## UI patterns

| Pattern | Where | How |
|---|---|---|
| **Rank badge** | Next to user name on profile, leaderboards | Small pill: "#3 in team" |
| **Progress ring** | Dashboard cards, goal widgets | Radial progress toward meta |
| **Score pill** | Header, agent row in tables | Compact number with ⓘ |
| **Milestone toast** | On hitting 50%, 80%, 100% of meta | Subtle toast, rate-limited |
| **Achievement marker** | Profile, activity log | Small icon next to relevant events |
| **Comparison indicator** | Agent row in team view | "+12% vs last period" with arrow |
| **Streak counter** | Profile, dashboard | "N consecutive biweeklies hit" |

## What gamification is NOT

- Not a distraction. If it interferes with getting work done, it's wrong.
- Not punishing. Low ranks are not shamed. No "you're last" messaging.
- Not arbitrary. Every point earned has a real-world source.
- Not permanent. Old closed periods are archived, not rubbed in.

## Shared components

As the ERP Metas domain matures, reusable gamification components should be extracted to `seed/frontend/lib/src/design-system/gamification/` and consumed across products.

Candidates for extraction (once stable):
- `<RankBadge />`
- `<ScorePill />` (with built-in ⓘ tooltip)
- `<ProgressRing />`
- `<MilestoneToast />`
- `<ComparisonIndicator />`

## Per-product adoption plan

| Product | Gamification surface |
|---|---|
| **ERP** | Metas domain (agent performance, VGV, points, rankings). Reference implementation. |
| **Therapy** | Session counts, patient milestones, therapist output — **future**, after ERP stabilizes. |
| **Personal Finance** | Saving streaks, budget goal achievement — **future**. |
| **Daily Life** | Habit streaks, routine consistency — **future**. |
| **Mailing** | Campaign KPIs per user — **likely not user-facing gamification**. |
| **Core** | Cross-product org-level achievements — **future**. |

The ERP Metas domain is the reference implementation. Patterns validated there get extracted and adopted elsewhere — not before they're stable in production.

## Reference

- Reference implementation: `products/erp-imobiliario/METAS-PLAN.md`
