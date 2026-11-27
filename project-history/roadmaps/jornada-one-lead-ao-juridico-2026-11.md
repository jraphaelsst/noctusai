# jornada-one-lead-ao-juridico-2026-11 — Jornada da One: do lead à conclusão do Jurídico

> **Registro durável** (conforme `KB § PATTERNS/common/roadmap-tracking.md`).
> Origem: um planejamento feito por outro agente **sem acesso ao repositório**
> (`jornada-one-lead-ao-juridico-2026-11.original.md`, mantido verbatim ao lado), avaliado aqui contra o código da `dev` @ `ed04390`.
> Decisão: **nada é implementado neste commit.** O documento converte o plano original numa lista de especificações
> classificadas (confirmada / diverge / decisão pendente / proposta), reduz as pendências ao que o código ainda não responde,
> e organiza as fases de trabalho reaproveitando o que já existe.

---

## 0 · Como ler este documento (leia antes de qualquer coisa)

**O plano original NÃO é fonte de verdade.** Ordem do owner (Rapha, 2026-11-26): *"é só um planejamento feito por uma IA que não
tinha acesso ao nosso repositório… a gente vai fazer esse planejamento virar uma verdade, mas ele não é ainda."*
Cada item dele é uma **especificação candidata** e só vira regra quando (a) bate com o código ou (b) o Rapha ratifica.

**"ERP" no plano original = Social Wiring.** Owner, 2026-11-26: o Social Wiring é o CRM + CMS + ERP imobiliário (white label
para outros mercados depois; hoje, imobiliário). O produto `products/erp-imobiliario` está **dormente** (`ativo=false`,
`deploy/fleet/active-scope.txt`). Por isso:
- toda a jornada deste plano vive em `products/social-wiring` (+ `products/agents`, onde a Julia roda);
- as evidências que o plano original tirou de `products/erp-imobiliario/**` (migration 041, `ProcessosVenda.tsx`,
  `Contratos.tsx`, `Chaves.tsx`, `processos_venda_service.py`) **não descrevem o sistema vivo**; os equivalentes vivos no SW
  estão citados abaixo, e onde não há equivalente isso está dito;
- a pergunta do plano original "fonte de verdade dos contratos: ERP ou Social Wiring?" **deixa de existir**: é o SW.

**Onde cada parte da jornada mora na sidebar do SW** (`products/social-wiring/frontend/src/nav/navGroups.ts`, plano
`crm-cms-erp-vertical-seeds-2026-11`). O CMS, por enquanto, é o **CoreStudio** (owner 2026-11-26).

| Módulo da sidebar | Páginas que esta jornada toca |
|---|---|
| **CRM** › Pessoas | Contatos, Clientes, Revisão de Duplicados, Guia de documentos |
| **CRM** › Vendas | Leads, **Funil de Vendas**, **Processos de Venda**, **Agendamentos** |
| **CRM** › Atendimento | Monitor, **Blocos do Atendimento** (donos/handoffs), **Supervisão** |
| **ERP** › Imóveis / Financeiro | Imóveis, Condomínios, **Permutas**, Financeiro |
| **Emissões** | Certidões, Extrator de Matrículas (pós-aceite automático, contrato §7) |
| **CoreStudio** (CMS) | Fora desta jornada (conteúdo/marketing) |
| Julia (produto `agents` + páginas Julia do SW) | Visitas (pré-agendamento), Leads, Equipes, Relatórios, Reengajamento, Avaliações |

Nota: no SW, **Processos de Venda fica no CRM › Vendas**, não no ERP. Quando o plano original diz "ERP", leia "Social Wiring" e
use a tabela acima para achar a página.

**Legenda de status** (usada em todo o documento):

| Marca | Significado |
|---|---|
| ✅ CONFIRMADO | Existe no código da `dev` @ `ed04390`; o caminho está citado. |
| ⚠️ DIVERGE | O plano original diz uma coisa e o código faz outra; precisa de decisão. |
| 🟡 DECISÃO RELATADA | Regra que o plano original atribui ao Rapha. Plausível, mas **ainda precisa ser ratificada** (veio de outra conversa). |
| 🔵 PROPOSTA | Recomendação técnica deste documento; não aprovada. |
| ❓ PENDENTE | O código não responde; precisa de decisão do Rapha ou de leitura do banco de produção. |

**Limite da verificação:** o que é configuração por org (destino dos relatórios, equipes, regras de envio, etapas do funil/processo)
fica no **banco**, não no repo. Este documento diz o que o código *permite*; o que a org da One *usa hoje* entra na Fase 0.

---

## Origin

Em 2026-11-26 o Rapha trouxe um plano da jornada comercial/operacional da One (lead → Julia → Rapha → corretor → visita →
proposta → aceite → Processo de Venda → Jurídico), feito com outro agente, e pediu que ele fosse avaliado contra o que já
existe na NoctusAI, refinado, e salvo na `dev` para ser retomado numa sessão local. A verificação mostrou que boa parte do que o
plano trata como "a definir" ou "futuro" **já está construída no SW** (pré-agendamento de visitas da Julia, distribuição por
equipes, destino configurável dos relatórios, ciclo de vida de roteiros com no-show, caminho único de aceite, revisão jurídica,
organ de aprovações), e que algumas regras do plano **conflitam** com decisões de owner já registradas no código.

---

## 1 · Achados que mudam o plano (resumo executivo)

1. **A Julia já faz pré-agendamento de visita, com grade de horários.** ✅ `julia_visitas` + `julia_visitas_config`
   (migrations 272 → renomeada em 287; `backend/app/services/julia_visitas_service.py`). A Julia **oferece horários livres** de uma
   grade semanal configurada (`horarios_para_ferramenta`, via `SchedulingEngine` do seed) e registra um pedido `solicitada`.
   **Confirmar é ato humano** (`POST /api/julia/visitas/{id}/confirmar`), e ao confirmar o sistema cria um
   `atendimento_agendamentos` (tipo `visita`) e manda WhatsApp ao lead.
   ⚠️ O plano original diz que a Julia "coleta uma ou, preferencialmente, duas opções livres de dia/horário". O código tem
   **um slot por pedido**, escolhido de uma grade, com unicidade "uma visita viva por (org, início)". → decisão D1.
2. **A distribuição para corretores já existe e é configurável.** ✅ `julia_equipes_service.atribuir_responsavel`
   (round-robin por cursor, `manter_ultimo`, `atende_apos_julia`, `modo julia|funil`). ⚠️ O plano diz que "não há distribuição
   automática". No código isso é um **estado de configuração**, não ausência de funcionalidade: uma org sem equipe
   `atende_apos_julia=true` não distribui nada sozinha. → confirmar a configuração da One na Fase 0.
3. **"Destino configurável em vez de Rapha fixo" já existe.** ✅ `julia_relatorio_destino` (migration 313):
   `modo usuario` (um membro fixo, p.ex. Rapha) ou `modo responsavel` (o responsável do lead, com fallback). Sem telefone →
   relatório salvo, envio pulado, aviso no app (`sem_destino`), nunca silencioso. A proposta 🔵 do plano original ("parametrizar
   o destino") vira **usar o que existe**.
4. **No-show e reagendamento já têm modelo de dados.** ✅ `roteiros` / `visitas` (082, 184, 219, 338): resultado da visita
   `pendente | realizada | cancelada | nao_compareceu | reagendada`; reagendada é **neutra** e a nova data vive num **novo
   roteiro** (`reagendada_para_visita_id`); `perdidas = cancelada + nao_compareceu`; `consolidadas = realizada`; reabrir um
   roteiro gerado é de supervisor/owner/admin. A "pergunta pendente" da seção H do plano original fica reduzida a **quem
   dispara o próximo passo** depois de um `nao_compareceu`. → decisão D4.
5. **Gap real: a visita confirmada pela Julia não vira visita do roteiro.** ⚠️ Confirmar uma `julia_visitas` cria um
   `atendimento_agendamentos` tipo `visita`, mas a migration 082 tirou "visita" do Agendar justamente porque agendamento não
   é contável; a visita contável é `roteiros/visitas`. Neste serviço não há ligação entre os dois. Consequência provável: visitas
   marcadas via Julia ficam fora das métricas de consolidadas/perdidas e do "visita aconteceu?". ❓ confirmar se outro serviço
   faz a ponte (grep em `julia_visitas_service.py` não encontrou). → slice P3.1.
6. **Remarcar reescreve o horário no lugar.** ⚠️ `remarcar` faz `update` em `atendimento_agendamentos.quando` (e no pedido).
   A regra do plano ("reagendamento não apaga a tentativa anterior") só se cumpre se houver evento append-only com o horário
   antigo. ❓ verificar se `julia_eventos` registra de→para; se não, é violação da regra EOA do repo (ver §6). → slice P3.2.
7. **Qualificação e "quando vira oportunidade" já são computadas e configuráveis.** ✅ `julia_envio_service`: o estágio de
   qualificação é calculado no `agents`; a regra da org é um **estágio mínimo** (`julia_envio_regras.estagio_minimo`); gatilhos
   `qualificado | visita | frio | captacao | invalido | manual`; envio idempotente por telefone, cria lead + card no funil
   (`spawn_funil_card`). 🟡 A regra relatada "oportunidade só nasce com intenção de visita + disponibilidade" **se expressa como
   configuração** (gatilho `visita` / critério de visita), não como entidade nova. → decisão D2.
8. **A análise de supervisão em 5 dimensões NÃO existe.** ❓ Não há qualificação/completude/aderência/eficiência/conversão
   nem aprovação OK/não-OK versionada. O que existe: relatório da Julia no handoff/conclusão/alerta (313), métricas da
   supervisão (`modules/supervisao/metricas.py`: taxa de qualificação, TPR), ledger de handoff `emitido → assumido | expirado`
   (`modules/atendimento_blocos/handoffs.py`), eventos `supervisao_falha`. E existe o **organ de aprovações** ✅
   (`347_approvals.sql`, `apr_events`: `submitted | approved | rejected`, por versão, motivo obrigatório na rejeição,
   append-only, dupla decisão concorrente perde) — que é exatamente o "OK / não OK preservando versões" que o plano pede.
   → Fase 2.
9. **O aceite da proposta já tem caminho único.** ✅ `projects/sw-lead-to-contract/CONTRACT.md §4.4–§7`: proposta nasce da
   visita (104) → Aceitar materializa a negociação, marca `visitas.proposta_aceita_em`, inicia o contrato
   (`contrato_gerador.service.iniciar`), evento `proposta_aceita` → `pipeline/funil_eventos.mover_por_evento` →
   `pipeline/aceite.aceitar_proposta` → `processos_venda` (etapa `elaboracao_contrato`) → handoff T3 `aceite_proposta`
   (dono do funil → dono dos processos) → `pos_aceite_service.disparar` (certidões + matrícula automáticas). Idempotente.
   Boa parte das perguntas da seção 16.2 do plano original já tem resposta; sobram as **Q1/Q2 de owner** do próprio contrato (§5).
10. **O Jurídico tem mais estrutura do que o plano conhece.** ✅ além de 106 (contratos por atendimento) e 134 (envelope de
    assinatura): 151 (flag admin "processo anterior à plataforma"), 157 (modalidade de assinatura), 163 (bloqueios de
    prontidão do contrato), 177 (**uma revisão jurídica final por versão gerada** — owner 2026-09-30: revisão humana é exceção),
    190 (aditivos), 193 (partes e cláusulas), 308 (especificações).
11. **Imóvel que sai do catálogo já tem decisão de owner — e ela diverge do plano.** ⚠️ `349_imovel_historico_vista_escrita.sql`:
    owner 2026-11-04 — *"no one receives the alert, we update our database to the Vista data and history gets an action
    register"*, notificação **só in-app**; `imovel_historico` append-only; `063_imovel_registry` guarda a identidade.
    O plano original quer "notificar o responsável e exigir ciência" e "voltar a oportunidade para busca". → decisão D6.
12. **Liga/desliga por org já é o padrão da Julia.** ✅ chaves por org, desligadas por padrão: `julia_avaliacao_config.pedido_ativo`
    (354), `julia_reengajamento_config.portal_primeiro_contato_ativo` (355), horário de atendimento por org (359),
    `julia_visitas_config.<perfil>.ativo` (272), `supervisao_config.supervisao_ativa` (286/288). Mudança de configuração vira o
    evento append-only `configuracao_alterada`. A seção K do plano original = **seguir esse padrão**, não inventar outro.
13. **CPF já tem desenho LGPD.** ✅ O SW **nunca guarda o CPF em claro**: só `cpf_hash` (sha256) + `cpf_final` (3 dígitos)
    (272, `products/social-wiring/projects/julia/specs/lais-build-contract.md §17`); a identificação do lead (CPF/RG/CNH) fica no `agents`
    (`julia_lead_turn_service.py`, GUARDRAILS B8.4). Pedidos de titular (LGPD art. 18) são registrados para decisão humana,
    nunca executados pela Julia (297). `cpf_obrigatorio` é configuração por perfil. ❓ confirmar onde e como o RG é guardado no `agents`.
14. **Controle de chaves não existe no sistema vivo.** O `Chaves.tsx` citado é do `erp-imobiliario` dormente; não encontrei
    custódia de chaves no SW. A distinção do plano (custódia interna ≠ entrega ao comprador) continua válida como regra de
    desenho, mas hoje não há módulo nenhum. Fica para Finalização/pós-venda.

---

## 2 · Matriz: cada especificação do plano original → status

> Referência das seções = numeração do arquivo `.original.md`. Caminhos relativos a `products/social-wiring/` salvo indicação.

| # | Especificação candidata (plano original) | Status | Evidência / observação |
|---|---|---|---|
| S1 | Jornada ≠ processo ≠ automação (§3) | 🟡 adotar | Coerente com o modelo; nenhuma mudança no código. |
| S2 | Papéis por transação, não globais (§3.2) | ✅ / ❓ | `pessoa-mesma-cpf-multideal-CONTRACT.md`, `atendimento-partes-imoveis-CONTRACT.md`; conferir se cobre "comprador numa, vendedor noutra". |
| S3 | Cartão do funil é `atendimento`; negociação é etapa (§3.3, §6.1) | ✅ | 060, 077, 090 (`um_card_por_lead`). |
| S4 | Etapas `qualificacao → visitas → proposta_recebida → negociacao → proposta_decisao` (§6.2) | ✅ código / ❓ config | `pipeline/funil_eventos.py` move por evento só para frente; as etapas são linhas por org (`pipeline_stages`, 034) → conferir na Fase 0. |
| S5 | Agendamentos múltiplos por atendimento (§6.3) | ✅ | 061. Mas visita contável é `roteiros/visitas` (082), não agendamento. |
| S6 | Solicitada ≠ confirmada ≠ realizada (§6.3, F) | ✅ | `julia_visitas.status` (solicitada/confirmada/remarcada/cancelada) + `visitas.status` (338). São **dois objetos** — ver achado 5. |
| S7 | Reagendamento preserva histórico (§6.4) | ⚠️ | Roteiro: sim (novo roteiro). Pedido da Julia: `remarcar` reescreve o horário — achado 6. |
| S8 | Vários imóveis candidatos; o aceito vira o principal; os outros ficam no histórico (§7.1) | ✅ | 082 (N imóveis por roteiro) + 104 (proposta da visita; aceita = `atendimento_negociacao.imovel_codigo`). Ofertados pela Julia espelhados (313). |
| S9 | Imóvel indisponível → notificar, exigir ciência, voltar para busca (§7.2) | ⚠️ | Decisão de owner 2026-11-04 (349) diz o contrário (só in-app, ninguém recebe alerta). D6. |
| S10 | Catálogo volátil vs identidade histórica (§7.3) | ✅ | 063 `imovel_registry`, 349 `imovel_historico`. |
| S11 | Aceite → sai do funil → Processo de Venda, idempotente (§8) | ✅ | `pipeline/aceite.py`, `sw-lead-to-contract §4.4/§5.4/§6`. O plano citava a migration 041 do ERP dormente. |
| S12 | 8 etapas padrão do processo (§8.1) | ⚠️ / ❓ | A lista veio do `erp-imobiliario/041`. No SW as etapas de `processos_venda` são linhas configuráveis (034); só `elaboracao_contrato` aparece como entrada no contrato §5.4. Ler a config real. |
| S13 | Módulo de contratos no "ERP" (§9.1) | ⚠️ | `Contratos.tsx` é do produto dormente. O módulo vivo é o `card_hub/contrato_gerador` do SW. |
| S14 | Contratos por atendimento, versões imutáveis (§9.2) | ✅ | 106, 112, 120, 190, 193. |
| S15 | Envelope de assinatura por versão; PDF assinado = nova versão (§9.3) | ✅ | 134, 157. |
| S16 | Integração ERP↔SW de contratos (§9.4, 16.3) | ❌ some | Não há dois sistemas: o SW é a fonte. Pergunta retirada. |
| S17 | Custódia de chaves ≠ entrega ao comprador (§10) | 🟡 regra / ❌ módulo | Só existe no ERP dormente. Achado 14. |
| S18 | Timeline unificada com `ocorrido_em` real (§11) | ✅ | `backend/app/modules/card_hub/timeline_service.py`. Regra EOA do repo exige evento por mudança de estado. |
| S19 | Automação liga/desliga por empresa, etapa e automação; novas começam desligadas (§12.1, K) | ✅ padrão / 🔵 por etapa | Achado 12. O nível "por etapa da jornada" (comercial/jurídico/finalização) ainda não existe — proposta P6. |
| S20 | Idempotência de eventos/webhooks (§12.2) | ✅ | Envio por telefone, aceite, handoffs condicionais, `provider_message_id` único (318). |
| S21 | IA não afirma evento crítico sem fonte (§12.3) | ✅ | Handoff só é "assumido" por ato humano (julia-v2 G2); visita só confirma por humano; pedidos LGPD só humanos (297). |
| S22 | Tentativas, falhas, escalonamento visíveis (§12.4) | ✅ parcial | `julia_envio_entregas`, `notificacao_status`, `sem_destino`, `supervisao_falha`. |
| S23 | Consentimento, horários, preferências (§12.5) | ✅ | Horário por org (359), aviso de IA + link de privacidade obrigatório (355/359), opt-outs (297). |
| S24 | Dados mínimos por função (§12.6) | ✅ | `289_julia_db_lockdown` (julia_* só backend), CPF hash, `KB § PATTERNS/security/access-tiers.md`. |
| S25 | Dados no 1º contato: nome, telefone, e-mail (§5.2, E) | 🟡 | Conferir contra os slots coletados pelo prompt v3 — **sem alterar o prompt**. |
| S26 | CPF/RG só com intenção concreta de visita, só do titular (§5.2, D, E) | 🟡 / ✅ parcial | `cpf_obrigatorio` por perfil no pedido de visita (272). RG: ❓. |
| S27 | Julia não agenda nem confirma (§5.1, D) | ✅ | Confirmar = rota humana autenticada. Mas a Julia **reserva um slot** (`solicitada`) — D1. |
| S28 | Análise da Julia em 5 dimensões + OK/não-OK do Rapha versionado (§5.3) | ❓ não existe | Fase 2, sobre o relatório (313) + organ de aprovações (347). |
| S29 | Julia encaminha direto ao Rapha; sem fila automática (B, G) | ✅ possível por config | `julia_relatorio_destino modo=usuario` + nenhuma equipe `atende_apos_julia`. Fase 0 confirma. |
| S30 | Corretor aceita formalmente a responsabilidade (16.1) | ✅ parcial | Handoff `emitido → assumido` só por sinal humano, com prazo (`horas_para_assumir`) e expiração. |
| S31 | Jurídico recebe o processo e isso fica registrado (16.2) | ✅ | Handoff T3 `aceite_proposta` funil-owner → processos-owner (288). |
| S32 | Compra, aluguel e permuta não são idênticos (I) | 🟡 | Perfis `geral/compra/aluguel` no pré-agendamento (272); módulo `permutas` existe; mapear diferenças na Fase 5. |
| S33 | Pós-venda fora do escopo | 🟡 adotar | Pesquisa de satisfação/Google já está desligada por decisão de 2026-11-17 (354). |

---

## 3 · Decisões a ratificar com o Rapha (o que o código não decide)

> Formato pensado para `AskUserQuestion` / skill `noc-questionnaire` na sessão local. Uma rodada resolve D1–D4.

- **D1 · Disponibilidade da visita.** (a) Manter o que existe: a Julia oferece slots livres da grade e reserva **um** pedido
  `solicitada`; (b) a Julia registra **até duas** opções livres e o Rapha escolhe (exige mudar o modelo: 1 pedido com N opções,
  ou N pedidos ligados, e revisar a unicidade por slot); (c) (a) + uma segunda opção como texto livre no relatório.
  🔵 Recomendação: (a) ou (c) — a grade evita choque de horário, que é a razão da unicidade em 272.
- **D2 · Quando nasce a oportunidade (card no funil).** Confirmar que, para a One, o envio ao SW deve disparar **só** no gatilho
  `visita` (pedido de visita registrado) e não ao atingir um estágio mínimo de qualificação. Isso é configuração em
  `julia_envio_regras`, não código novo. E: leads `frio`/`captacao`/`manual` continuam gerando card?
- **D3 · Destino e distribuição.** Confirmar: `julia_relatorio_destino = usuario(Rapha)` e nenhuma equipe com
  `atende_apos_julia=true`; depois, o Rapha atribui o corretor manualmente. Quer que a atribuição manual do Rapha fique
  registrada como handoff (hoje T1 é `sdr → bloco_atual(lead)`)?
- **D4 · Depois de um `nao_compareceu`.** (a) o Rapha/corretor decide (só registro + alerta); (b) a Julia faz um contato
  automático oferecendo nova data (automação nova, **desligada por padrão**); (c) o card volta sozinho para uma etapa de
  reagendamento. Lembrete: `mover_por_evento` hoje **só move para frente**; (c) quebra essa regra e precisaria de decisão explícita.
- **D5 · Análise em 5 dimensões.** Confirmar que quer de fato o OK/não-OK do Rapha **antes** do encaminhamento ao corretor
  (o plano original tem duas versões conflitantes: seção 5.3 "Rapha valida" vs seção B "encaminha direto"). Se sim: ela trava
  o encaminhamento ou só pontua a qualidade da Julia (feedback para o refino de evals)?
- **D6 · Imóvel indisponível com oportunidade aberta.** A decisão de 2026-11-04 (349) vale também quando há lead/proposta
  em andamento naquele imóvel? Ou esse caso específico pede notificação ao responsável do card + ciência?
- **D7 · Q1/Q2 do contrato `sw-lead-to-contract §5`.** Ao aceitar uma proposta, o que acontece com as outras propostas
  abertas do mesmo atendimento? Cancelar uma proposta já aceita (hoje `409`, fora de escopo) entra agora?
- **D8 · Fim da responsabilidade do Jurídico.** Qual etapa de `processos_venda` (na config real da One) marca o fim do Jurídico
  e o início da Finalização? E quem é o dono (bloco) de cada etapa?

---

## Trigger conditions (o "quando")

| # | Gatilho | Sinal observável | Por que muda o jogo |
|---|---|---|---|
| T1 | Fase 0 concluída | Respostas registradas (config da One lida do banco) no Decision log | Sem isso, qualquer desenho pode duplicar config que já existe. |
| T2 | D1–D4 ratificadas | Linhas datadas no Decision log | Destrava a Fase 3 (visitas). |
| T3 | D5 ratificada | Linha no Decision log | Destrava a Fase 2 (análise + aprovação). |
| T4 | D7–D8 ratificadas + config de etapas lida | Decision log + lista real de `pipeline_stages` (processos_venda) | Destrava a Fase 5 (RACI do Jurídico). |
| T5 | Fase 5 fechada | Etapas do Jurídico com dono, entrada, saída, evidência | Só então desenhar automações da Julia em etapas posteriores (Fase 6). |
| T6 | Jurídico fechado e estável | Owner pede | Abre o planejamento separado de pós-venda. |

**Status hoje (2026-11-26):** nenhum disparou. Este commit só registra o plano.

> Cada slice tem DOIS roteiros: o de teste (unitário/CI) e o de verificação (estado vivo). Verde nos testes ≠ verificado em produção.

## Phase 1 — Plano avaliado e salvo (SHIPPED)

| # | Título | Arquivos | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | Plano original preservado verbatim | NEW `project-history/roadmaps/jornada-one-lead-ao-juridico-2026-11.original.md` | **shipped** | `git show origin/dev:<path>` devolve o arquivo idêntico ao upload. |
| P1.2 | Avaliação contra o código + roadmap refinado | NEW este arquivo | **shipped** | Abrir na sessão local a partir da `dev`; cada caminho citado em §1/§2 existe no tree. |

**Garantia de comportamento:** nenhuma mudança de runtime. Só documentação em `project-history/`.

## Phase 0 — Verificação read-only no ambiente (próxima, sem gatilho; pode começar já)

| # | Título | O que ler | Verify recipe |
|---|---|---|---|
| P0.1 | Config da Julia da org One | `julia_relatorio_destino`, `julia_equipes` (+ membros, `atende_apos_julia`, `modo`), `julia_envio_regras` (`estagio_minimo`, critério de visita), `julia_visitas_config`, `julia_reengajamento_config` | Uma tabela no Decision log com os valores lidos (MCP `supabase`, só `SELECT`). |
| P0.2 | Etapas reais | `pipeline_stages` da One para `funil` e `processos_venda` (chave, ordem, papel, dono do bloco) | Lista colada no Decision log. Substitui a lista de 8 etapas do ERP dormente. |
| P0.3 | Ponte julia_visitas → roteiros/visitas | grep amplo + leitura do router de confirmar + front da agenda | Resposta sim/não com o arquivo; se "não", confirma o gap da P3.1. |
| P0.4 | Remarcar guarda o horário antigo? | `julia_eventos` emitidos por `remarcar` | Um evento com de→para existe ou não. |
| P0.5 | Onde o RG fica | `products/agents` — identificação do lead | Caminho + forma de armazenamento (claro/hash/cifrado). |
| P0.6 | Dados do 1º contato | slots coletados pela Julia v3 (`agents/projects/julia-v2/content-v3*`) **só leitura** | Bate ou não com nome/telefone/e-mail. |

## Phase 2 — Análise estruturada da Julia + aprovação (DEFERRED — T1 + T3)

| # | Título | Reaproveita | Constrói | Verify recipe |
|---|---|---|---|---|
| P2.1 | Análise em 5 dimensões com evidências e próxima ação | Relatório do handoff/conclusão (`julia_relatorios`, 313); estágio calculado no `agents` | Campos estruturados (nota + justificativa + trechos por dimensão) no relatório, gerados pelo `agents` — **sem mexer no prompt da conversa**; análise é um passo separado | Card de um lead real mostra as 5 dimensões com citações da conversa. |
| P2.2 | OK / não-OK do Rapha, com versões | Organ `approvals` (347, `apr_events`, `subject_kind='julia_analise'`) | Botões no card/relatório; "não OK" exige motivo e gera nova versão da análise | Linha `rejected` com motivo + nova versão `submitted`; a antiga continua legível. |
| P2.3 | Métrica de qualidade da Julia | `modules/supervisao/metricas.py`, eval loop (skill `noc-iterate`) | Taxa de aprovação por dimensão no scorecard | Scorecard mostra a taxa do mês. |

**Por que não agora:** D5 decide se a aprovação trava o encaminhamento ou só mede qualidade — muda P2.2 inteiro.

## Phase 3 — Do pedido de visita à visita realizada (DEFERRED — T2)

| # | Título | Reaproveita | Constrói | Verify recipe |
|---|---|---|---|---|
| P3.1 | Visita confirmada pela Julia vira visita contável | `julia_visitas` (272), `roteiros/visitas` (082/338) | No Confirmar: criar/anexar `visitas` num roteiro (ou decidir que agendamento basta) — conforme P0.3 | Confirmar um pedido → aparece no roteiro → "visita aconteceu?" pergunta por ela → entra em consolidadas/perdidas. |
| P3.2 | Remarcar sem perder a tentativa | `julia_eventos`; regra EOA | Evento `visita_remarcada` com de→para (se P0.4 = não) | Timeline do card mostra as duas datas. |
| P3.3 | Política de no-show | `visitas.status = nao_compareceu` (338) | Conforme D4 (registro + alerta, ou automação desligada por padrão) | Marcar no-show num roteiro de teste → o efeito escolhido acontece, e só ele. |
| P3.4 | Disponibilidade conforme D1 | `julia_visitas_config`, `SchedulingEngine` | Só se D1 = (b)/(c) | Pedido com 2 opções visível ao Rapha; nenhuma reserva duplicada de slot. |

## Phase 4 — Imóvel indisponível com oportunidade aberta (DEFERRED — D6)

| # | Título | Reaproveita | Constrói | Verify recipe |
|---|---|---|---|---|
| P4.1 | Detectar card/proposta aberta num imóvel que saiu do Vista | `imovel_historico` (349), `imovel_registry` (063), espelho de ofertados (313) | Conforme D6: aviso in-app ao responsável do card + ciência, sem mover a etapa sozinho | Desativar um imóvel de teste com card aberto → aviso com imóvel, motivo, card, etapa e ação esperada. |

## Phase 5 — Aceite → Processo de Venda → Jurídico (DEFERRED — T4)

| # | Título | Reaproveita | Constrói | Verify recipe |
|---|---|---|---|---|
| P5.1 | RACI por etapa de `processos_venda` | Etapas reais (P0.2), donos de bloco (maya-blocks), handoff T3 | Tabela: etapa → executa / aprova / consultado / informado → entrada → saída → evidência → prazo | Revisada pelo Rapha; cada evidência aponta para um evento/registro que existe. |
| P5.2 | Dados mínimos para abrir o processo | `stage_gate.py`, bloqueios do contrato (163), revisão jurídica (177) | Só documentar o que já é bloqueio vs o que falta | Lista com origem de cada exigência. |
| P5.3 | Exceções do Jurídico | 151 (processo legado), 190 (aditivos), 134 (assinatura `expirado`), `permutas` | Tratamento de: proposta retirada, documentação incompleta, divergência de partes, financiamento recusado, assinatura expirada, cartório | Cada exceção tem dono e destino definidos. |
| P5.4 | Compra × aluguel × permuta | Perfis 272, módulo `permutas`, contratos por modalidade | Mapa de diferenças antes de regras universais | Revisado pelo Rapha. |
| P5.5 | Indicadores operacionais | `supervisao`, timeline | Tempo por etapa, pendências por responsável, contratos aguardando revisão, assinaturas pendentes, processos parados | Painel com dados reais da One. |

## Phase 6 — Julia em etapas posteriores (DEFERRED — T5)

| # | Título | Reaproveita | Constrói | Verify recipe |
|---|---|---|---|---|
| P6.1 | Chave por etapa da jornada (comercial / jurídico / finalização) | Padrão de chaves por org (achado 12), `configuracao_alterada` | Um nível de chave por etapa, tudo desligado por padrão, sem tocar o SDR | Ligar/desligar uma etapa gera evento; religar não dispara mensagem antiga. |
| P6.2 | Comunicações de acompanhamento | Envio WAHA, horário 359, opt-outs 297 | Só avisos baseados em eventos com fonte confiável (S21) | Cada mensagem tem o evento de origem citado. |

## Phase 7 — Finalização e pós-venda (DEFERRED — T6)

Fora do escopo. Inclui: confirmação formal de entrega de chaves (não existe módulo no SW), registro, pagamento, posse,
satisfação (hoje desligada por decisão de 2026-11-17).

---

## Anti-goals

- ❌ Reescrever, reconstruir ou mexer no prompt/SDR da Julia. O SDR está praticamente pronto (🟡 relatado; o prompt v3 e o
  eval loop vivem em `products/agents`). Toda mudança de comportamento da Julia passa pelo eval loop (`noc-iterate`), nunca direto.
- ❌ Criar uma segunda timeline, uma segunda tabela de histórico escrita à mão, ou um "módulo de contratos" novo. Existem.
- ❌ Criar distribuição/fila/destino de encaminhamento novos. Existem (`julia_equipes`, `julia_relatorio_destino`) — configurar.
- ❌ Usar `products/erp-imobiliario` como referência ou destino. Está dormente.
- ❌ Deixar a IA decidir estado comercial/jurídico (aceite, assinatura, conclusão de etapa).
- ❌ Mover card para trás automaticamente sem decisão explícita (D4) — `mover_por_evento` é só-para-frente por desenho.
- ❌ Guardar CPF em claro no SW.
- ❌ Desenhar pós-venda nesta rodada.

## Open questions (além de D1–D8)

- **Q1** Quem é dono de cada bloco do funil e dos processos na One hoje (maya-blocks)? Responde-se na P0.2.
- **Q2** O "aceite formal do corretor" precisa ser um botão, ou o handoff assumido por ato humano (S30) basta?
- **Q3** Retenção dos dados de identificação no `agents` (prazo, base legal) — documentar junto da P0.5.
- **Q4** Quando o Social Wiring virar white label para outros mercados, quais partes desta jornada são do seed vertical
  (`crm-cms-erp-vertical-seeds-2026-11`) e quais são só da One? Não decidir agora; só não hardcodar nada da One.

## Decision log

- **2026-11-26:** Plano original recebido; owner: não é fonte de verdade, é especificação a validar.
- **2026-11-26:** Owner: o "ERP" do plano = Social Wiring (CRM+CMS+ERP imobiliário, white label futuro). `erp-imobiliario` dormente.
- **2026-11-26:** Owner: o CMS do SW, neste momento, é o CoreStudio.
- **2026-11-26:** Avaliação contra `dev@ed04390` registrada neste arquivo; nada implementado.

## Retrospective (preencher quando a Fase 0 fechar)

*Quais achados se confirmaram no banco? Quais especificações do plano original sobreviveram? Lições → KB/MEMORY.*

## Composes with

- `KB § PATTERNS/architect/event-oriented-architecture.md` — toda mudança de estado nova (visita, aprovação, no-show) emite evento na mesma transação.
- `KB § PATTERNS/architect/measurement-by-design.md` — estados como enums, eventos append-only, métricas declaradas no contrato.
- `KB § PATTERNS/security/access-tiers.md` — rota/tabela nova declara o tier.
- `products/social-wiring/projects/sw-lead-to-contract/CONTRACT.md` — caminho do lead ao contrato (fonte das respostas da §16.2).
- `products/social-wiring/projects/roteiro-ciclo-CONTRACT.md` — ciclo do roteiro e vocabulário de resultado da visita.
- `products/social-wiring/projects/julia/` + `products/agents/projects/julia-v2/CONTRACT.md` — contrato da Julia.
- `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.md` — o SW como base do white label.

## Como retomar numa sessão local

Na sessão local, a partir da `dev` atualizada:

> "Tem um plano na `dev` em `project-history/roadmaps/jornada-one-lead-ao-juridico-2026-11.md`. Lê ele inteiro (o `.original.md`
> é só referência, não é verdade), roda a Fase 0 só em leitura e depois me faz as perguntas D1–D8."

## Evidência consultada (dev @ `ed04390`)

Migrations SW (`products/social-wiring/backend/migrations/`): 034, 060, 061, 063, 077, 082, 104, 106, 134, 151, 163, 177,
184, 219, 272, 287, 288, 297, 313, 318, 338, 347, 349, 354, 355, 359. Código SW: `app/services/julia_visitas_service.py`,
`app/routers/julia_visitas_router.py`, `app/services/julia_envio_service.py`, `app/services/julia_equipes_service.py`,
`app/services/julia_ferramentas_service.py`, `app/modules/atendimento_blocos/handoffs.py`, `app/modules/supervisao/`,
`app/modules/pipeline/{aceite,funil_eventos,stage_gate}.py`. Contratos: `projects/sw-lead-to-contract/CONTRACT.md`.
Catálogo: `deploy/fleet/active-scope.txt`. Esta é uma leitura dirigida, não uma auditoria completa.

## File trail

- `project-history/roadmaps/jornada-one-lead-ao-juridico-2026-11.original.md` (plano original, verbatim)
- Este documento.
