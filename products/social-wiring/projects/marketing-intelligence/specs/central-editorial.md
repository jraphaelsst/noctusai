# Central Editorial SMM

Source: https://chatgpt.com/share/6ace4990-4280-83e9-b36b-104eb8f5f8eb (extracted 2026-10-15).

## 1 · Origin

Built from the public syllabus of EBAC's **Social Media Marketing** course (https://ebaconline.com.br/social-media-marketing): 26 modules in 7 parts, 25+ hours, 8 months. Only the public syllabus was read — not the lessons. Owner's ask: *"Não quero aula, quero um sistema que faça esses tópicos"* — each syllabus topic becomes a job the system performs for the three profiles, separately, like SIMEC.

| EBAC part | Becomes |
| --- | --- |
| 01 Guia de Sobrevivência das Mídias Sociais | Niche/trend radar, market context |
| 02 Iniciando os Trabalhos | Profile dossiers, positioning |
| 03 Planejamento | Editorial lines, monthly calendar |
| 04 Postagem e Agendamento de Publicações | Scripts, captions, publication prep, scheduling |
| 05 Gestão de Relacionamentos | Comment processing, community, new topics |
| 06 Social Analytics | Delegated to **SIMEC** (import its results) |
| 07 Gerenciamento de Projetos em Redes Sociais | Production flow, tasks, month close |

(Part 01's published topics: what social media is and why it stands out; the SMM profession — prospects, skills, market expectations; trends for the coming years; activity: create a fictitious brand to apply the concepts.)

## 2 · Structure

A central + three independent environments, each with its own strategy, voice, audience, calendar and indicators:

| Profile | Niche |
| --- | --- |
| Mônica | Psychoanalysis and adult life (Nós no Limiar) |
| Gilson | Real-estate market |
| Isadora | Art, architecture and authorial repertoire |

Same management method across three very different niches — compare without mixing audiences or copying what worked in another niche.

## 3 · The loop

1. **Intelligence & planning** — research, audience, topics, goals, calendar
2. **Production & publishing** — scripts, captions, formats, review, scheduling
3. **Relationship** — comments, communities, questions, new topics
4. **SIMEC** — data audit, performance, tests, learnings

→ results feed the next planning round. SIMEC already defines comparison criteria, observation windows, missing-data handling and hypothesis evaluation — **not rebuilt**; the Central adds the ability to turn results into editorial decisions and production tasks.

## 4 · Commands

| Command | Does |
| --- | --- |
| `RADAR DO NICHO` | Researches trends and references relevant to the profile |
| `PLANEJAR MÊS` | Produces the content calendar |
| `ROTEIRIZAR` | Writes the script in the voice of whoever will publish |
| `PREPARAR PUBLICAÇÃO` | Packages the piece for approval and scheduling |
| `PROCESSAR COMENTÁRIOS` | Drafts replies and spots possible new topics |
| `IMPORTAR RESULTADOS SIMEC` | Turns analyzed results into decisions for the next contents |
| `FECHAR MÊS` | Monthly editorial evaluation and pending items |

## 5 · v1.0 kit (ChatGPT) — verbatim in `../kits/central-editorial-1.0/`

27 files: instructions, commands, per-profile dossiers, separate CSV bases for calendars, topics, campaigns and decisions. Proposed install: three ChatGPT Projects (one per person). Trello suggested for tasks (prepares tasks; does not register them until connected). Publishing and private metrics depend on external integrations.

## 6 · SIMEC vs Central Editorial

**SIMEC** — analyze content performance and steer decisions by results.
**Central Editorial** — plan, create and organize content production.

| Activity | SIMEC | Central Editorial |
| --- | --- | --- |
| Analyze metrics | Main | Consumes results |
| Identify winning content | Yes | Uses the findings |
| Analyze video retention | Yes | Applies the learnings |
| Research trends | Secondary | Yes |
| Research competitors and references | Not its focus | Yes |
| Plan calendar | Suggests from data | Builds the calendar |
| Write scripts | Not its focus | Yes |
| Write captions | Not its focus | Yes |
| Prepare campaigns | Not its focus | Yes |
| Organize production | No | Yes |
| Draft comment replies | No | Yes |
| Evaluate test results | Yes | Uses the conclusions |

Examples — SIMEC: "here are 10 Reels' metrics" → what to repeat, change, test. Central: "15 Reels for next month" → research, topic selection, scripts, captions, calendar.

Recommendation (ChatGPT): keep them **separate and connected**.

## 7 · Overlap with what social-wiring already has

Criação de Mídia (`../core-studio/`) already covers parts of "Production": Minha Pesquisa, Segundo Cérebro, headline generation, Roteiro Avançado. `ROTEIRIZAR` and `RADAR DO NICHO` should be checked against those before any new build (seed-first / products-consume-canonical-organs).
