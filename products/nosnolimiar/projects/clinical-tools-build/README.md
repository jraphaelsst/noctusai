# clinical-tools-build — our own specs for "Ferramentas" + the patient area (name TBD) in Nós no Limiar

> **Status note (2026-11-02):** the product was renamed `monica` -> `nosnolimiar` ("Nós no Limiar"). The "Entre sessões" patient app is **PAUSED 2026-11-02**; the patient area keeps the working name "área do paciente (nome a definir)" until the owner names it.

Guided reflection tools that Mônica sends to a patient between sessions. The patient signs
in to the patient area (name TBD) of Nós no Limiar, fills them in on their phone, and the result lands on
that patient's record, ready for the next session.

This folder holds **our** specs only. We studied a third-party tool catalog as a reference
for what the feature has to do. The vendor material (captures, source, analysis) lives outside
git in `_private-studies/geizelima-clinica/` and is never copied here. Nothing below reuses
their content, wording, structure or code.

## Layout

| File | What it holds |
|---|---|
| `README.md` | this map |
| `DECISIONS.md` | owner decisions (dated) + open questions |
| `ENGINE.md` | the tool engine contract: concepts, question kinds, modifiers, result blocks, identity, lifecycle, data model, surfaces |
| `PILOT-TOOLS.md` | (next) the 6 pilot tools, written in our own words with Mônica |

## Status

S4 synthesis, spec only. **No build until the owner says "go all the way"** (skill
`noc-reverse-engineer` step 8 → skill `noc-contract-first`).

## Shape in one paragraph

A **tool** is data, not code. One engine (a seed organ, consumed by Nós no Limiar) runs any tool
built from **5 question kinds** and **3 modifiers**, and renders the result from
**6 result blocks**. Mônica can also create and edit tools in an editor. She sends a tool from the patient's
record. The patient, who is a noc user linked to their record but never a member of Mônica's
team, signs in to the **patient area (name TBD)**, answers, can pause and resume, and can leave
instantly on any tool. The response is stored against the exact tool version, so editing a
tool never breaks an old result.

## Sensitivity

Answers are health data (LGPD art. 11, dado pessoal sensível). The binding security & LGPD
requirements (consent, retention, deletion, access, audit, encryption, quick exit) are in
`DECISIONS.md` § Security & LGPD, from the `security` advisor review of 2026-11-02. The legal
basis and retention years still need a lawyer's confirmation.
