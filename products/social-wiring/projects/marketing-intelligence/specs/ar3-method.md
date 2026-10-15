# Método AR3 — Árvore de Ramificação Tripla

Source: https://chatgpt.com/share/6acee3e1-516c-83e9-8b8d-0fd488e59956 (extracted 2026-10-15). Method designed by Mônica (hand-drawn sketch, WhatsApp image 2026-10-12 11:11, not retrieved); name proposed by ChatGPT.

## 1 · The method

A method of **infinite idea creation** organized as a tree of subjects:

- Pick the **3 main themes** someone wants to talk about.
- Split each into **3 subthemes**, each of those into 3 more, and so on, **until the subthemes are exhausted, with no repetition at all**.

Name: **A**rvore · **R**amificação · **3** (tripla).
Command: *"Shelly, aplique o AR3 ao tema maternidade na maturidade."*
Purpose: a large, organized bank of ideas from three central themes, surfacing specific subjects for content, scripts, classes, talks and other products — no fresh idea hunt for every post.

## 2 · Rules

1. **Thematic coherence** — every child belongs to its parent.
2. **Progressive deepening** — a child must *decompose* its parent into something more specific, not just be "related to the root". Example: FOTOGRAFIA → {Ângulos, Luz, Método}; Luz → {Natural, Artificial, Mista}; Luz natural → {Luz direta, Luz difusa, Contraluz}.
3. **No repetition** — including across different branches and different roots.
4. **Exhaustion, not forcing** — a branch stops when it has no three genuinely distinct, relevant children; never invent artificial splits.
5. A branch counts as done only when exhausted (the owner's requirement).
6. Expansion stays **open**: any leaf can be expanded later if it has three distinct, pertinent, not-yet-covered children.

## 3 · Numbers

| Level | Per root | 3 roots |
| --- | ---: | ---: |
| 1 Temas | 1 | 3 |
| 2 Eixos | 3 | 9 |
| 3 Subtemas | 9 | 27 |
| 4 Recortes | 27 | 81 |
| 5 Microtemas | 81 | 243 |

(Application 01 counted differently: it went one level deeper per root — 243 microthemes per root, 729 total, 1,092 positions including roots and intermediates. See the content file.)

## 4 · Output format (as produced in application 01)

```
ÁRVORE n. <ROOT>
Território: <one-line scope of the root>

n.m <Eixo>
  n.m.k <Subtema>
    <Recorte> → <microtema>; <microtema>; <microtema>.
```

Each final line holds three independent possibilities.

## 5 · Applications

| # | Roots | File |
| --- | --- | --- |
| 01 | Maternidade · Maturidade · Vida Adulta Contemporânea | `../content/ar3-01-maternidade-maturidade-vida-adulta.md` |

Known gap from application 01: conceptual repetition **across roots** (e.g. "filhos adultos" under Maternidade vs "envelhecimento dos pais" under Maturidade) still needs a dedup pass in future expansions — a natural job for embeddings-based similarity when this is built.

## 6 · Build notes

- The tree is data, not prose: store nodes (id, parent, level, label, root) so expansion, dedup and "pick next topic" are queries.
- Dedup check against the whole tree (not just siblings) before accepting a new node.
- Leaves link naturally to SIMEC (which topics performed) and to the Central Editorial (`PLANEJAR MÊS` pulls from unused leaves).
