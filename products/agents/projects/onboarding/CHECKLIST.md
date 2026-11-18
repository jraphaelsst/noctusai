# Onboarding checklist — a new real-estate client

What the interviewer (`onboarding-imob`) asks, in what order, and where each answer lands. Source of truth in code:
`products/agents/backend/app/onboarding/checklist.py` (a test keeps this table and the code in step).

**Levels.** `R` required before go-live. `C` required only when the client attends the operation it names (item 9
decides). `O` optional: always has a default the interviewer offers, so a client can say "use the default".

**Order of the interview.** Item 9 first (it decides which conditional items exist), then every `R`, then `C`, then `O`.
One question at a time; the interviewer repeats the answer back and waits for a yes before it counts; it never
assumes a value the client did not give.

**Destinations.** `spec` = an org spec key the agents product validates and stores (`PUT .../specs`);
`sw` = a social-wiring operational setting; `humano` = a step the team performs (credentials, approvals) that an
interview cannot.

| # | Lvl | Item | Destination |
|---|---|---|---|
| 1 | R | Nome comercial | spec `nome_imobiliaria` |
| 2 | R | Nome do assistente (default Julia) | sw `agente_nome` |
| 3 | R | CNPJ | spec `cnpj_oficial` |
| 4 | R | CRECI-J | spec `creci_j` |
| 5 | R | Domínios oficiais | spec `dominios_permitidos` |
| 6 | R | Aviso de privacidade (generated from 1–4, owner approves) | spec `aviso_privacidade_url` |
| 7 | O | Mostrar o atendente humano (default não) | sw `mostrar_atendente` |
| 8 | O | Perfil do WhatsApp | humano `perfil_whatsapp` |
| 9 | R | Operações atendidas (compra, locação, administrativo, captação) | spec `operacoes_atendidas` |
| 10 | C | Título do profissional (default Corretor) | spec `titulo_profissional` |
| 11 | R | Regiões atendidas | spec `regioes_atendidas` |
| 12 | O | Regiões adjacentes | spec `regioes_adjacentes` |
| 13 | O | Sobre a região | spec `informacoes_regiao` |
| 14 | R | Horário de atendimento humano | spec `horario_atendimento` |
| 15 | R | Retorno do humano | spec `prazo_retorno_humano` |
| 16 | R | O que é um lead pronto, por operação | spec `criterio_lead_pronto` |
| 17 | O | Perguntas extras (até 5) | spec `perguntas_extras` |
| 18 | O | Mínimo para ofertar imóveis | spec `minimo_para_ofertar` |
| 19 | O | Captação: enviar ou só notificar (default notificar) | sw `envio_captacoes` |
| 20 | R | Fonte do catálogo | humano `fonte_catalogo` |
| 21 | R | Endereço completo ou só bairro | sw `politica_endereco` |
| 22 | O | Informar IPTU (default não) | sw `politica_iptu` |
| 23 | O | Imóveis/empreendimentos de campanha | humano `imoveis_campanha` |
| 24 | R | Destino do lead pronto | sw `destino_lead_pronto` |
| 25 | R | Contatos por setor (setor, finalidade, nome, telefone) | spec `contatos_oficiais` |
| 26 | R | Destino no CRM | humano `crm_destino` |
| 27 | O | Leads frios e WhatsApp inválido (default sim, 30 min) | sw `envio_frios_invalido` |
| 28 | C | Financiamento (compra) | spec `conhecimento_venda` |
| 29 | O | Custos da compra | spec `conhecimento_venda` |
| 30 | O | Documentos de compra | spec `conhecimento_venda` |
| 31 | O | Permuta | spec `conhecimento_venda` |
| 32 | C | Garantias (locação) | spec `conhecimento_locacao` |
| 33 | O | Prazos de contrato | spec `conhecimento_locacao` |
| 34 | O | Multa rescisória | spec `conhecimento_locacao` |
| 35 | O | Documentos de locação | spec `conhecimento_locacao` |
| 36 | O | Chaves e assinatura | spec `conhecimento_locacao` |
| 37 | O | Reengajamento (default lembrete 15 min, final 4 h) | sw `reengajamento` |
| 38 | O | Recesso | sw `recesso` |
| 39 | O | Pré-agendamento de visitas (default off) | sw `visitas` |
| 40 | O | Link de avaliação no Google | sw `avaliacao_google` |
| 41 | O | Pesquisa de satisfação (default não) | sw `pesquisa` |

A client attending purchase and rental answers 20 required items; everything optional has a default, so that
interview alone yields a working agent.

## Apply, report, then evaluate

One apply step takes `{item number: value}` and returns one line per answered item: `aplicado`, `recusado` (with a code
and the reason — validator message, item not applicable, spec not declared, SW refusal) or `pendente_humano`. Spec
values are written through the one org-spec write path (validation, audit); an invalid value is refused, never stored.
Items 28–31 and 32–36 feed one knowledge spec each, written as labelled lines. After the apply the owner is sent to
evaluation mode (`modo_avaliacao`) for a dry conversation before go-live; going live stays a human act.

## Import

Paste or upload an existing export (a JSON object or `chave: valor` lines; keys can be the item number, its title, the
spec key or the setting id). Recognised lines come back as unconfirmed answers (`origem=importado`) the interviewer
confirms instead of asking; an imported item is only written once someone confirms it (otherwise the apply report says `pendente_confirmacao`); unrecognised lines come back verbatim; conflicting duplicates are named, not guessed.

## Deferred (named destinations)

## The live interviewer (resolved: onboarding-interviewer-tools / -evals)

The `onboarding-imob` agent (claude_sdk, a studio agent of the staff org) runs in the Studio chat. The Onboarding tab's
"Iniciar entrevista" (`POST .../onboarding/conversa`) opens one conversation bound to the chosen company
(`agents.onboarding_sessoes`); its four tools (`onboarding` group: `progresso_onboarding`, `registrar_resposta`,
`importar_configuracao`, `revisar_e_aplicar`; `app/onboarding/entrevista.py`) never take an org: the server reads it from
the conversation. Gates the model cannot talk past: an answer needs the client's own words (`trecho`) found in the
conversation and passes the apply step's validation in dry-run; an imported value needs the client's explicit yes; the
apply needs a summary and a yes written AFTER it, and re-checks the live grant. Every answer, refusal, pending mark,
import, summary and apply is one append-only event (`agents.onboarding_eventos`); the tab polls the folded state.
Evals: behaviour (LLM-judged) `agent/onboarding-imob-evals-comportamento.json`; mechanism
`agent/onboarding-imob-evals-mecanismo.json`, replayed by `tests/onboarding/test_evals_mecanismo.py`.

## Deferred (named destinations)

- SW settings are applied through `SwSettingsPort` -> social-wiring's onboarding staff channel (service token + staff
  `ator`; SW allow-lists the settings). Not yet allow-listed in SW (reported `recusado`, apply by hand): items `visitas`,
  `agente_nome`, `destino_lead_pronto` — `NOC-REMEDIATE[onboarding-sw-staff-more-settings]`, destination: next SW slice.
- Free-prose import (extracting items from a pasted paragraph) is the interviewer's conversational job, not the
  parser's — `NOC-REMEDIATE[onboarding-import-prose]`, destination: interviewer evals once the agent is applied.
- Applying the `onboarding-imob` definition rows to a live environment (needs the studio content token; payloads
  `agent/onboarding-imob-{secoes,ferramentas,rascunho,evals-comportamento}.json`, drafts only, never published from here) —
  `NOC-REMEDIATE[onboarding-agent-rows]`, destination: the owner's next studio session (`noctus.agents.content`).
- The studio mechanism executor drives CHANNEL turns; the interviewer's mechanism cases therefore live in the repo and run
  as a pytest suite — `NOC-REMEDIATE[onboarding-evals-mecanismo-studio]`, destination: an in-app (claude_sdk) mechanism
  driver in the agents eval engine.
