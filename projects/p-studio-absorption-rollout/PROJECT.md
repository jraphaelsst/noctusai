# P Studio — absorção na plataforma + exposição pública — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log.
>
> **Write for a zero-context reader.** This document was authored from a session
> that happened OUTSIDE this repository (in `cadu/p-studio/`). The next agent has
> not seen that conversation. Everything needed is inlined below.

- **Created:** 2026-08-13
- **Last updated:** 2026-08-13
- **Status:** Design drafted → Phase 0 ready (não interrogado ainda — ver §7)
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `cadu/p-studio/README.md` · `cadu/p-studio/MASTER-PROMPT.md` · `cadu/_INTEGRACOES_BANCARIAS/03-ASAAS.md` (o que está provado contra a API viva) · `cadu/_INTEGRACOES_BANCARIAS/02-BANCO-DO-BRASIL.md` (destino de produção) · `cadu/_NOC_ABSORPTION/` (mapa do protótipo Lovable) · skill `noc-absorb-product` · `KB § PATTERNS/devops/containerization.md §12a` · `KB § PATTERNS/devops/prod-exposure-consent.md` · `KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md`
- **Project slug:** `p-studio-absorption-rollout` — em `projects/` porque P Studio **ainda não é um produto** da plataforma (é o caso "not-yet-a-product" da regra de escopo→localização).

---

## 1. Context & Purpose

**P Studio** é um ERP de produtora de fotografia e audiovisual imobiliário
(clientes, imóveis, CRM, agenda de captação, produção, financeiro). Ele foi
construído **fora deste repositório**, em
`~/Documents/repository/NoctusAI/cadu/p-studio/`, como workspace standalone nos
moldes do produto `dilidu` — backend FastAPI + frontend React/Vite, schema
`p_studio` no Postgres compartilhado, RLS por organização.

**Ele já está funcionando e já fala com banco de verdade.** O módulo financeiro
foi ligado ao Asaas: emite boleto, concilia pagamento e dá baixa no lançamento.
O ciclo inteiro foi exercitado contra o Postgres real e a API real do Asaas.

**O que falta, e é por isso que este projeto existe:** o webhook do Asaas só
pode ser entregue numa **URL pública**. Todo o comportamento da rota está
provado contra o banco real com corpos montados no formato documentado, mas o
**envelope real nunca passou por aqui** — porque tudo rodou em `localhost`.

Fechar isso exige exatamente o que a plataforma já sabe fazer: absorver o
produto no modelo de container da casa, publicar, e registrar a superfície. Daí
o projeto ser de absorção, não de "configurar um túnel".

**Como fica o ganho:** P Studio vira produto de primeira classe da plataforma
(catálogo, SSO, deploy, ingress), e a conciliação bancária deixa de depender de
alguém apertar "sincronizar" na tela.

---

## 2. Confirmed constraints

- **Produção será Banco do Brasil; Asaas é a casca.** *(Citação do usuário: "we're gonna use Banco do Brasil in production. Asaas is gonna be the shell of it, for later migration to BB system." Isso já moldou a arquitetura: existe uma camada `ProvedorCobranca` (Protocol) e o adapter do Asaas é o único arquivo autorizado a conhecer o vocabulário do Asaas. Um teste — `tests/providers/test_vazamento.py` — falha se `billingType`/`externalReference`/`PAYMENT_*`/`access_token` aparecerem em service ou router.)*
- **`cadu/realty-lens-pro/` é CONGELADO — somente leitura.** *(É o protótipo Lovable, sincronizado com o editor do usuário: escrever nele sincroniza de volta e pode sobrescrever trabalho. Ler à vontade. `cadu/_NOC_ABSORPTION/` é o mapa já extraído dele — use esse.)*
- **Chave do Asaas: existem DUAS, e a diferença move dinheiro.** *(A de produção (`$aact_prod_…`) emite boleto real, com tarifa, notificando um pagador real. A de sandbox (`$aact_hmlg_…`) é a única com simulação de pagamento. O `.env` local aponta para sandbox de propósito; produção está comentada logo abaixo.)*
- **Idioma:** conversa em inglês, **código e documentação em PT-BR** (padrão da casa no p-studio). *(Citação: "i sent u this in portuguese, but from now on let's keep in english".)*
- **O usuário quer velocidade.** *(Citação: "I gotta keep building, i cant keep getting gated by my own methodology." Traduzindo para este projeto: não filar sub-projetos, não parar para perguntar o que dá para decidir com evidência. A exceção é §7-Q1, que é consentimento e não pode ser decidido por agente.)*

> **Não interrogado.** Este documento foi redigido a partir de uma sessão em
> outro repositório, sem a interrogação que o template exige. As respostas acima
> são citações reais; **§7 lista o que falta perguntar** — a Fase 0 fecha isso.

---

## 3. Design principles

1. **Absorver antes de expor.** A URL pública é consequência do deploy no modelo
   da casa, não um túnel apontado para um `uvicorn` local. Um túnel para
   `localhost` capturaria o envelope e deixaria a dívida de absorção inteira.
2. **O webhook não pode ser exposto sem o segredo.** A rota já exige o header
   `asaas-access-token` comparado com `secrets.compare_digest`. Publicar antes de
   configurar `ASAAS_WEBHOOK_TOKEN` no ambiente de produção abre uma rota de
   escrita anônima.
3. **Sandbox primeiro na URL pública.** O primeiro webhook real que chegar deve
   vir do sandbox. Só depois de o envelope estar capturado e a fixture gravada é
   que a chave de produção entra.
4. **Nada de "adaptar o p-studio ao seed" neste projeto.** Absorção é porte do
   que existe para o modelo de container da casa. Refatorar para consumir órgãos
   canônicos é projeto seguinte, e a regra §1 "Products consume canonical organs"
   vai cobrá-lo — mas depois, com o produto de pé.

---

## 3a. Seed-first analysis (REQUIRED)

1. **O contrato é idêntico para todo produto?** **NÃO** para o domínio (ERP de
   produtora é específico). **SIM** para o que este projeto realmente entrega:
   containerização, ingress e registro de superfície pública já são mecanismos
   da casa e não devem ganhar variante p-studio.
2. **A fonte de dados é específica do produto?** SIM — schema `p_studio`.
3. **A colocação é específica do produto?** SIM — produto novo no catálogo.
4. **A regra de visibilidade/permissão é a mesma?** SIM — RLS por organização via
   `public.current_org_id()`, idêntica ao resto da frota.
5. **O seam já existe no seed?** **SIM, e é o ponto central deste projeto:**
   `noc-absorb-product` + o modelo de container da casa
   (`containerization.md §12a`: um container, `serve_spa`, imagem base do seed)
   + o padrão de ingress por túnel. Nada disso se constrói aqui — se consome.
6. **Default-on ou opt-in?** N/A — é absorção de um produto, não uma capacidade.

**Litmus — linhas de código por produto que este desenho exige:**

- [x] **Uma seção pequena** — a absorção porta o produto para a forma da casa;
      o que é específico é o Dockerfile/compose do produto e a linha de roster.
      Nenhum mecanismo novo cross-product.

**Implicação no plano de fases:** as fases **não** percorrem produtos um a um.
Elas são: auditar → absorver **este** produto → publicar → capturar → registrar.
Correto pela regra.

---

## 4. Scope

**In scope:**
- Auditar o estado real do p-studio contra este repositório (Fase 0).
- Absorver `cadu/p-studio/` para `products/p-studio/` no modelo de container da casa.
- Deploy com a URL pública, via o caminho de ingress já usado pela frota.
- Registrar o webhook do Asaas (sandbox) e **capturar o envelope real**.
- Gravar a fixture do envelope e fechar a última lacuna de `03-ASAAS.md §6`.

**Out of scope (for now — com motivo):**
- **Trocar para a chave de produção do Asaas** — depende de o envelope estar
  capturado e do usuário decidir faturar de verdade. Muda dinheiro; é decisão
  dele, não do projeto.
- **Adapter do Banco do Brasil** — precisa de convênio de cobrança ativo (lead
  time de banco, não de engenharia). O roteiro está em `02-BANCO-DO-BRASIL.md §6`
  e o desenho já foi provado compatível.
- **Job de sincronização em lote** — o BB concilia por polling e vai precisar
  dele; o backend não tem agendador hoje. Só vira necessário com o BB.
- **Consumir órgãos canônicos do seed no frontend** — projeto seguinte (§3, P4).
- **Trocar a senha do `admin@pstudio.local`** — operacional, o usuário faz.

---

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice / Phase | Lens | Files (ou globs) | Time-box | Dispatched as |
|---|---|---|---|---|
| Fase 0 — auditoria | architect-inline | `cadu/p-studio/**` (leitura), `KB § PATTERNS/devops/*` | 30 min | inline-empersonation |
| Fase 1 — absorção | devops-engineer | `products/p-studio/**`, `KNOWLEDGE-BASE/02-LANDSCAPE.md` | 3-4 h | Agent dispatch (worktree) |
| Fase 2 — deploy + ingress | devops-engineer | infra de ingress/túnel, compose | 2 h | Agent dispatch (worktree) |
| Fase 3 — webhook + captura | backend-engineer | `products/p-studio/backend/{scripts,tests/fixtures}` | 1-2 h | Agent dispatch |
| Fase 4 — fechamento | architect-inline | docs + KB | 1 h | inline-empersonation |

### 4a.2 Codification expectations per slice

| Slice | s1 | s2 | s3 | s4 | Why |
|---|---|---|---|---|---|
| Fase 0 | sim | não | não | não | auditoria revela deriva; vira §11 |
| Fase 1 | sim | sim | talvez | não | absorção de arquitetura divergente — N-ésima ocorrência; se N≥3, promover |
| Fase 2 | sim | sim | não | não | primeira exposição pública de produto vindo de workspace externo |
| Fase 3 | sim | sim | **sim** | **sim** | ver §4a.2-nota |
| Fase 4 | não | não | sim | não | consolidação |

**§4a.2-nota — a candidata forte a keeper (s4).** A sessão do p-studio bateu
**duas vezes** na mesma classe de bug: *um fake de teste mais permissivo que o
Postgres esconde um bug real*. Primeiro a constraint UNIQUE (o fake aceitava
duplicata; o webhook "deduplicava" contra um banco que aceitava tudo). Depois o
tipo UUID (o fake comparava strings em Python e devolvia "não achei"; o Postgres
**levanta** 22P02, e o evento estacionava na fila de retry para sempre). N=2 ⇒
triagem; se aparecer uma terceira, é `MUST formalize` e provavelmente um
`check_fake_db_fidelity`. Registrar em Fase 3 independentemente do desfecho.

### 4a.3 Routes-not-taken (pré-rejeitadas)

| Route | Why rejected |
|---|---|
| Túnel (ngrok/cloudflared) apontando para o `uvicorn` local só para capturar o envelope | Capturaria o envelope e deixaria a absorção inteira por fazer; o produto continuaria fora do catálogo, sem deploy, sem SSO. A dívida sobreviveria à "solução". |
| Deixar o p-studio em `cadu/` e só publicá-lo de lá | Contraria "seed first" e o modelo de container da casa; nasceria uma frota paralela sem os keepers da plataforma. |
| Simular o envelope a partir da documentação e fechar a lacuna como "coberta" | É exatamente a mentira que a suíte de replay pode contar. `03-ASAAS.md` marca isso como *a confirmar* de propósito — não se fecha com suposição. |
| Registrar a chave de PRODUÇÃO no webhook já no primeiro deploy | O primeiro webhook real deve ser de sandbox. Produção emite boleto real, com tarifa, para um pagador real. |

### 4a.4 Notes — surface + delivery

Padrão da casa. Cada slice fecha com delivery note via
`noctus.dev.file_proposal kind="delivery" project="p-studio-absorption-rollout"`.

---

## 5. Architecture / Data Model

**Onde o código está hoje** (workspace externo, não neste repo):

```
cadu/p-studio/
  backend/          FastAPI · zero `async def` · supabase-py · schema p_studio
    app/providers/  a camada ProvedorCobranca (Protocol, não ABC)
      tipos.py      StatusCobranca, ClienteCobranca, PedidoCobranca, Cobranca
      asaas.py      ÚNICO arquivo que pode conhecer o vocabulário do Asaas
      fake.py       ProvedorFake (implementação de referência)
      http.py       ClienteHTTP (httpx.Client síncrono, timeouts, tradução de erro)
    app/routers/integracoes_router.py   webhook + eventos + reprocessar
    app/services/integracao_service.py  grava-primeiro / processa-depois / 200
    migrations/     001 schema · 002 plataforma+seeds · 003 integração bancária
  frontend/         React 18 + Vite 6 + Tailwind v3 + TanStack Query
```

**Estado do banco** (JÁ APLICADO — não reaplicar):
- Projeto Supabase `NoctusAI` / `nyplttplcoyiiqjrvtiw` (o Postgres compartilhado).
- Schema `p_studio`: 13 tabelas, 47 policies, RLS por org.
- Org `p-studio` = `cb78914a-a3d6-4485-af3c-2d9d53e4f6c0`.
- Login `admin@pstudio.local` (senha forte gerada na aplicação da 002 — **não** é
  o `senha123` que está no arquivo da migration; aquele é só bootstrap local).
- `p_studio` já está na lista `pgrst.db_schemas` do PostgREST.

**A rota que motiva o projeto:**

```
POST /api/integracoes/asaas/webhook     (pública, autenticada por segredo no header)
  → 401 sem `asaas-access-token`
  → grava o evento cru em p_studio.provedor_eventos ANTES de processar
  → 200 em quase tudo o mais
```

O **200-quase-sempre** não é frouxidão: o Asaas **interrompe a fila de entrega
após 15 respostas não-2xx consecutivas**, e só volta com reativação manual no
painel. Um evento envenenado devolvendo 500 custaria a conciliação de todos os
outros pagamentos. A tabela `provedor_eventos` **é** a fila de retry, drenada por
`POST /api/integracoes/reprocessar` (autenticada).

---

## 6. Implementation phases

### Fase 0 — Auditoria (antes de qualquer código)

- [x] Ler `cadu/p-studio/README.md` + `MASTER-PROMPT.md` (todo produto tem os dois).
- [x] Auditoria estrutural completa do workspace (árvore, deps, env, DB/auth, migrations, suíte, acoplamentos de plataforma) — delegada a um agente read-only.
- [x] Ler `KB § PATTERNS/devops/containerization.md §12a` (modelo da casa para absorção de arquitetura divergente) e a skill `noc-absorb-product`.
- [x] Ler `KB § PATTERNS/devops/prod-exposure-consent.md` — §7-Q1 depende disso. **Frase canônica solicitada ao usuário 2026-08-13; pendente.**
- [x] Ler `KB § PATTERNS/architect/product-working-scope.md` + o catálogo: `ativo`+`deploy_scope` vivem em `public.products` (DB), não em arquivo. Decisão §7-Q3 → `live`.
- [x] Confirmar o gate do pre-commit: linha de roster em `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` — adicionada (commit `d4a354a0`).
- [x] `git fetch origin` + verificar agentes paralelos em ingress: nenhum.
- [x] **Isolar em worktree a partir de `origin/dev`** — `feat/p-studio-absorption` @ `47d34f189`, worktree `.claude/worktrees/p-studio-absorption`.
- [x] Revisar §6 em-lugar conforme a auditoria — ver §11 (entrada 2026-08-13 nº2).
- [ ] Rodar a suíte do p-studio e confirmar o baseline. **O número da §6 original (`331 backend + 115 frontend`) estava errado**: a auditoria conta `~311 backend` (18 arquivos) + `~116 frontend` (6 arquivos). Baseline real a ratificar na Fase 1.
- [ ] `KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md` — adiado para a Fase 2 (é onde o ingress entra; ler antes de tocar no snapshot).

**Improvements:** ver §11 — três keepers pegaram dívida de absorção que nenhuma leitura manual tinha pego (`check_override_is_range`, `check_dependabot_product_coverage`, `check_ci_test_matrix_coverage`). É exatamente o *epoch delta* que `absorb-seed-workspace.md` prevê: a medida de quanto a metodologia da plataforma andou enquanto este produto crescia fora dela.

### Fase 1 — Absorção para `products/p-studio/`

- [ ] Rodar a skill `noc-absorb-product` (é o caminho canônico — não inventar um).
- [ ] Portar backend + frontend para o modelo de um container (`serve_spa`, imagem base do seed).
- [ ] `README.md` + `MASTER-PROMPT.md` no destino (obrigatórios desde o dia um).
- [ ] Linha de roster em `KNOWLEDGE-BASE/02-LANDSCAPE.md` (o hook bloqueia sem ela).
- [ ] Registrar no catálogo de produtos com `ativo` + `deploy_scope`.
- [ ] Porta da casa atribuída (ver `noctus.dev.available_ports`).
- [ ] Suíte verde no novo lar: mesmo baseline da Fase 0, mais nada quebrado na frota.
- [ ] Decidir o destino de `cadu/p-studio/` (arquivar? apontar para o novo lar?) — não deixar duas cópias vivas.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Fase 2 — Deploy e URL pública 🅿️ (bloqueada em §7-Q1)

- [ ] **Obter o consentimento de exposição do usuário** (§7-Q1) — sem isso, para aqui.
- [ ] `predeploy_check` + CI verde (🔴 MANDATÓRIOS: prod é primeiro contato para imagem rodando).
- [ ] Variáveis de ambiente em produção: `SUPABASE_*`, `ORG_ID`, **`ASAAS_WEBHOOK_TOKEN`**, `ASAAS_API_KEY` (**sandbox nesta fase**), `ASAAS_BASE_URL`.
- [ ] Deploy pelo caminho da casa (`deploy_image`, auto-rollback é a rede).
- [ ] Ingress/túnel registrado na fonte de verdade (não editar o snapshot na mão — o keeper acusa).
- [ ] Verificar de fora: `GET https://<url-publica>/api/health` → `{"status":"ok","product":"p-studio"}`.
- [ ] Verificar que o webhook responde **401** sem o header. *(Se responder 200, o segredo não subiu — pare e corrija antes de cadastrar no Asaas.)*

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Fase 3 — Webhook real e captura do envelope

- [ ] Cadastrar no painel **sandbox** do Asaas (`sandbox.asaas.com` → Integrações → Webhooks): URL `https://<url-publica>/api/integracoes/asaas/webhook`, e o campo *Token de autenticação* = `ASAAS_WEBHOOK_TOKEN`.
- [ ] Emitir cobrança pelo app, pagar no sandbox (o sandbox tem simulação de pagamento).
- [ ] **Capturar o corpo real** e gravar em `tests/fixtures/asaas/webhook_liquidada.json`, com o campo `_procedencia` dizendo que foi capturado (o teste `test_toda_fixture_declara_procedencia` exige).
- [ ] Comparar o envelope real com o formato documentado `{"id","event","payment":{…}}`. **Se divergir, é achado de primeira grandeza** — `interpretar_evento` em `app/providers/asaas.py` é quem traduz.
- [ ] Teste de replay do envelope real (offline, `httpx.MockTransport`).
- [ ] Conferir no banco: `provedor_eventos.efeito='recebido'`, lançamento em `status='recebido'`, `pago_em` correto.
- [ ] Reenviar o mesmo evento pelo painel → `duplicado`, **nenhuma** segunda linha.
- [ ] Atualizar `cadu/_INTEGRACOES_BANCARIAS/03-ASAAS.md §6` — sai de *a confirmar*, entra em *provado*.
- [ ] Registrar o achado da §4a.2-nota (fidelidade do FakeDB, N=2) via `phase_learning_log`.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

### Fase 4 — Fechamento

- [ ] Eight-way sync do que foi aprendido.
- [ ] Delivery notes das quatro fases.
- [ ] `--improvements` + proposta empacotada por fase.
- [ ] Learn-before-archive e `noctus.dev.archive`.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`._

---

## 7. Open questions

1. **🅿️ Consentimento de exposição pública — quem responde: o USUÁRIO, e só ele.**
   Publicar o p-studio numa URL pública **é** a decisão de promoção, e
   `KB § PATTERNS/devops/prod-exposure-consent.md` é explícito: registrar a
   superfície de exposição é decisão do usuário, **nunca de um agente**. Um
   agente pode REGISTRAR a decisão (frase canônica, conferida contra o
   transcript escrito pelo harness), jamais inventá-la.
   *Recomendação:* pedir a frase canônica antes da Fase 2. **Necessário antes da
   Fase 2 — é o bloqueio 🅿️ do projeto.**
2. **`cadu/p-studio/` continua existindo depois da absorção?**
   *Recomendação (evidência):* arquivar e deixar um ponteiro. Duas cópias vivas
   do mesmo produto é a forma mais confiável de a correção ir para a errada.
   *Decidir na Fase 1.*
3. **`deploy_scope` do p-studio: `live` ou `dev`?**
   *Recomendação:* como a frota dev está dormente (regra §1, 2026-08-11) e o
   objetivo é justamente uma URL pública, `live` é o único caminho coerente —
   o que reforça a Q1. *Decidir na Fase 0.*
4. **O envelope do Asaas bate com a documentação?**
   *A descobrir na Fase 3* — é literalmente o que o projeto existe para
   responder. Sem recomendação: qualquer palpite aqui seria a suposição que o
   projeto quer eliminar.

---

## 8. Dependencies & blockers

- **Consentimento do usuário para exposição pública** — 🅿️ bloqueia a Fase 2. Ver §7-Q1.
- **Conta sandbox do Asaas** — já existe, chave em mãos. *(A de produção também, mas não entra neste projeto.)*
- **Supabase `nyplttplcoyiiqjrvtiw`** — já provisionado, migrations aplicadas. **Não reaplicar.**
- **`SUPABASE_SERVICE_ROLE_KEY` no ambiente de produção** — o webhook escreve sem JWT e não funciona sem ela. Está no `.env` compartilhado da raiz deste repo.
- **Capacidade de ingress** — porta da casa livre + entrada no túnel. Confirmar na Fase 0.

---

## 9. Success criteria

- `GET https://<url-publica>/api/health` responde **200** da internet pública com o corpo do seed:
  `{"status":"ok","version":"0.1.0","product":"P Studio","startup_hook_error":null}`.
  *(Corrigido 2026-08-13. O critério original dizia `{"status":"ok","product":"p-studio"}` — a rota
  local que o workspace declarava à mão. Ao passar para `create_product_app()` a rota passou a ser a
  do seed, que é o contrato de toda a frota: traz `version` + `startup_hook_error`, e `product` é o
  nome de exibição (`name=` da factory), não o slug. Movemos o critério, não a rota: re-declarar um
  `/api/health` local sombrearia o do seed em um produto só. Quem quiser o slug tem `/_version`.)*
- O webhook devolve **401** sem o header e **200** com ele.
- Um pagamento feito no sandbox chega **sozinho**, sem ninguém clicar em sincronizar, e o lançamento vira `recebido` com o `pago_em` certo.
- O envelope real está gravado como fixture com procedência, e um teste offline o reproduz.
- Reentrega do mesmo evento não cria segunda linha nem mexe em `pago_em`.
- P Studio aparece no catálogo com `ativo` + `deploy_scope`, com linha de roster, e a suíte da frota segue verde.
- `03-ASAAS.md §6` não tem mais nada em *a confirmar*.

---

## 10. How to use this plan

- **Fonte única de verdade do progresso.** Atualize enquanto trabalha.
- **Tique na hora** (`- [ ]` → `- [x]`), não em lote — o usuário lê isto como painel.
- **Fase a fase por padrão.** Pare e espere "continue" entre fases.
- **Interrogue antes de redesenhar.** §2 tem citações reais mas a interrogação
  formal não aconteceu; a Fase 0 fecha isso e §7 diz o que perguntar.
- **Revise o plano quando entender melhor** — plano velho engana.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-08-13 | **Fase 0 fechada + Gate 1 (importar in-home) executado.** Correções ao plano, todas por evidência: (a) o baseline da §6 estava errado — não é `331+115`, a auditoria conta `~311 backend` + `~116 frontend`; (b) `cadu/p-studio/` **não é um repositório git** (nem `cadu/`), logo não há histórico a preservar e o Gate 0 "snapshot do repo de origem" não se aplica — a absorção é cópia de arquivos; (c) portas da casa reservadas 8014/8180 (o workspace usava 8020/5176, escolhidas contra um snapshot de julho do registry); (d) `KB § …` resolve sob `KNOWLEDGE-BASE/CONTEXT/`, não `KNOWLEDGE-BASE/`. Três keepers bloquearam o commit de importação e cada um apontou dívida real: `check_override_is_range` (pin exato `react-router: "6.30.4"` — congela a frota inteira, o seed copia `overrides` para 12 produtos), `check_dependabot_product_coverage` (nenhum bloco npm ⇒ Dependabot nunca olharia este produto) e `check_ci_test_matrix_coverage` (ausente das duas matrizes de teste). Todos corrigidos na origem, nenhum contornado. Riscos registrados e ainda **abertos**: a migration 002 semeia `admin@pstudio.local`/`senha123` e grava `url_base='http://localhost:5176'` em `public.products` (tabela compartilhada) — nenhuma das duas pode ir para produção como está; e `backend/.env` carrega chave Asaas de **produção** + service-role, por isso ficou fora da cópia. | Claude Opus 5 |
| 2026-08-13 | Redigido a partir de `templates/PROJECT-TEMPLATE.md` após a sessão de integração bancária do p-studio (repo externo `cadu/`). **Sem interrogação formal** — §2 traz citações reais da sessão e §7 lista o que falta perguntar. Achados que moldaram o plano: (a) o envelope do webhook é a única lacuna que `localhost` não fecha; (b) migrations já aplicadas no Supabase compartilhado; (c) duas armadilhas corrigidas nas migrations — a 002 reescrevia a lista inteira de `pgrst.db_schemas` (teria removido `igig` do PostgREST) e a 001 fazia `CREATE OR REPLACE` em `public.current_org_id()`, função do Core de que toda RLS de todo produto depende. | Claude Opus 5 |
