# clinical-tools-build — our own specs for "Ferramentas" + the Entre sessões area in monica

Guided reflection tools that Mônica sends to a patient between sessions. The patient fills
them in on their phone through a personal link, and the result lands on that patient's record
in monica, ready for the next session.

This folder holds **our** specs only. We studied a third-party tool catalog as a reference
for what the feature has to do. The vendor material (captures, source, analysis) lives outside
git in `_private-studies/geizelima-clinica/` and is never copied here. Nothing below reuses
their content, wording, structure or code.

## Layout

| File | What it holds |
|---|---|
| `README.md` | this map |
| `DECISIONS.md` | owner decisions (dated) + open questions |
| `ENGINE.md` | the tool engine contract: concepts, question kinds, modifiers, result blocks, lifecycle, data model |
| `PILOT-TOOLS.md` | (next) the 6 pilot tools, written in our own words with Mônica |

## Status

S4 synthesis, spec only. **No build until the owner says "go all the way"** (skill
`noc-reverse-engineer` step 8 → skill `noc-contract-first`).

## Shape in one paragraph

A **tool** is data, not code. One engine (a seed organ, consumed by monica) runs any tool
built from **5 question kinds** and **3 modifiers**, and renders the result from
**6 result blocks**. Mônica sends a tool from the patient's record. The patient opens the
**Entre sessões** area (no login), answers, can pause and resume, and on sensitive tools can
leave instantly. The response is stored against the exact tool version, so editing a tool
never breaks an old result.

## Sensitivity

Answers are health data (LGPD art. 11, dado pessoal sensível). Consent, retention and access
rules are open in `DECISIONS.md` and go through the `security` advisor before build.
