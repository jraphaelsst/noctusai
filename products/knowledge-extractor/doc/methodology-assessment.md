# Methodology Assessment — "Método Audience"

> Honest evaluation of the extracted course methodology against validated,
> trusted sources, plus the gaps that drove the enrichment work. Full citations
> live in [`../data/methodology/REFERENCIAS.md`](../data/methodology/REFERENCIAS.md).
> Assessment date: 2026-05-22.

## Verdict

- **As a content-and-attention playbook:** strong (~8/10).
- **As an end-to-end "grow + monetize + run campaigns" system:** incomplete (~5.5/10 before enrichment).

The methodology is not folk theory — it is a well-chosen repackaging of the
canonical, empirically-grounded frameworks in this field, translated to pt-BR and
operationalized for Instagram. The bones are sound; the gaps were the bottom half
of the business (measurement rigor, audience ownership, monetization, campaigns).

## Scorecard

| Dimension | Score | Notes |
|---|---|---|
| Evidence grounding | 9 | Maps cleanly to Berger, Loewenstein, Cialdini, StoryBrand, Eyal, Meta guidance |
| Attention/hook craft | 9 | 30 templates + 7 triggers + 3 formats; matches what the algorithm rewards |
| Virality/content model | 8 | Essentially Berger's STEPPS + high-arousal-emotion finding |
| Positioning/identity | 8 | "Núcleo de Influência" is StoryBrand done well |
| Audience research | 5 → addressed | Autocomplete mining only → deepened in módulo 9 |
| Measurement & iteration | 5 → addressed | 3 metrics, under-weighted sends → fixed in módulo 10 |
| Distribution & ownership | 4 → addressed | Single-platform; no list → módulo 8 (campaigns/ownership) |
| Monetization & campaigns | 2 → addressed | Absent → new módulo 8 |
| Ethics/durability | 6 → addressed | Manipulation-heavy → guardrails added to METHODOLOGY.md |

## Validated (keep, now cited)

- **Conteúdos Notáveis ≈ Berger's STEPPS** (Contagious). — R-02
- **"Emoções quentes vs. frias"** = Berger & Milkman (2012), *J. Marketing Research* — high-arousal emotions drive sharing. — R-01
- **Gatilho do mistério** = Loewenstein (1994) information-gap theory of curiosity. — R-03
- **The 7 triggers** overlap heavily with **Cialdini** (authority, social proof, scarcity). — R-04
- **Núcleo de Influência + "inimigo"** = **StoryBrand** (customer=hero, brand=guide, villain). — R-05
- **First-3-seconds / watch-time** claim is currently correct per **Mosseri (2025)**. — R-08
- **"Economia da atenção"** traces to **Simon (1971)** and **Wu**'s *Attention Merchants*. — R-07

## Oversimplified (corrected in-place)

- **"Dopamina" framing** — reward mechanism is real (Eyal, Hooked) but "dopamine = pleasure" is wrong; dopamine is *wanting*, not *liking* (Berridge & Robinson, 1998). — R-06, R-15
- **"1 reels/dia por 90 dias"** — consistency beats raw volume; diminishing returns. Reframed as a learning sprint. — R-11
- **Measurement** — sends/DM-shares are now the top driver of reach to non-followers (Mosseri, 2025). — R-08

## Gaps (closed by enrichment)

| Gap | Closed by |
|---|---|
| Monetization & campaigns absent | `8-CAMPANHAS-E-MONETIZACAO.md` (AIDA + See-Think-Do-Care, offers, funnel, launch) |
| Shallow audience research | `9-PESQUISA-DE-AUDIENCIA.md` (ICP, JTBD, voice-of-customer) |
| Thin measurement | `10-MEDICAO-E-FEEDBACK.md` (per-surface metrics, sends, retention) |
| No ethics/durability guardrails | `METHODOLOGY.md § Ética e durabilidade` |
| No agent-ready structure | `ESQUEMA-BASE-DE-CONHECIMENTO.md` (claim→mechanism→source→confidence→how-to) |

## How this was produced

Sources gathered via web research (academic papers, official platform guidance);
enrichment executed via the [branching-dispatch](branching-dispatch.md) workflow
(four parallel agents, reconciled on `methodology-dev`).
