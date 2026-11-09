# cloud-work — manifesto do steward da cloud (2026-11-09)

Sessão cloud (claude.ai/code) atuando como steward **só do trabalho antigo e acumulado**.
O noc-0 (local) continua dono de `dev`, da fila de merge, de deploy e de prod. Nada aqui
foi enfileirado, nenhuma branch remota foi apagada e nenhum PR foi fechado. As listas abaixo
são **propostas** para o noc-0/owner decidir.

- Branch de entrega: `cloud-work` (base `origin/dev`). O noc-0 enfileira quando quiser.
- Fora do escopo, por acordo com o noc-0: tudo de 2026-11-07 em diante, `mq/*`, `mq-candidate/*`,
  `feat/nosnolimiar-rename*` (cutover em andamento, noc-0/noc-02), `feat/julia-v3-sw-catalogo`,
  `feat/sw-imovel-overlay-crud`, `feat/sw-certidoes-fail-fast-vendor`.
- Método: `git cherry` + comparação de conteúdo contra `origin/dev@5aae0e44b` (diffs de
  arquivo, `range-diff`, `merge-tree` dry-run). Patch-id diferente ≠ trabalho faltando: quase
  sempre só arquivos derivados (kb-counts, `02-LANDSCAPE.md`, `APPLIED.md`) foram re-renderizados.

## 1 · Entregue em `cloud-work`

| Commit (muda a cada rebase; buscar pelo assunto) | O quê | Origem | Verificação |
|---|---|---|---|
| `9ca71b42b` | `deploy_verify`: corte de 20/5 arquivos deixa de ser silencioso (`build_relevant_file_count`, `…_truncated`, "… +N more") | `fix/deploy-verify-truncation-explicit-r2` (cherry-pick `-x`) | `test_deploy_verify.py` + `test_deploy_pull.py`: 60 passed |
| `9b5d0fc76` | PyJWT 2.14.0 → **2.15.1** em root + 5 backends ativos | substitui dependabot #319 (2.15.0, só root) | seed/lib 427 + seed/framework 10 passed; `pip check` limpo. 2.15.1 porque `livekit-api` 1.2.2 exige `pyjwt>=2.15.1` |
| `b8ab42f92` | npm minors/patches: seed/lib, seed/framework, products seed/social-wiring/core/agents/monica + transitivos undici/postcss-selector-parser/brace-expansion/source-map-js | absorve os PRs listados em §3 "absorvido" | `npm ci` + `check` + `vitest` + `build` por pacote |

## 2 · Branches antigas — veredito

### Já estão em `dev` (outro commit, mesmo conteúdo) → podem ser apagadas

| Branch | Commit da branch → commit em dev |
|---|---|
| feat/noc-security-audit-skill | ba8ce7f1e → c9bf1aa40 (+ d99e00739, fb6a42f16) |
| feat/sw-julia-allowlist-fe | cc4eec3d5 → 27febbec4; b001f1a30 → f33b325ef; depois retrabalhado por 4acfc7db4 |
| feat/agents-prompt-exposure-fixes | 5980454ed → 7631dabbd (`test_julia_v2_vazamento_deltas.py` presente) — **o noc-02 não precisa retomar** |
| feat/core-host-tooling-refs | → dd70a6923 |
| fix/extrator-autoridade | 35dd57a88 → c9b94f921 (migration 254 idêntica) |
| feat/sw-certidoes-partes-imovel-link | ee04ac37c → 933f13506 (migration 186) |
| feat/sw-api-receita-watcher | idem (mesmo commit) |
| feat/contract-f6-termos-fe | 51e03c8b1 → 8f8629660 (estendido depois em dev) |
| feat/product-state-actions-hook | 1cfda8bdc → dffe79b32 |
| feat/ci-speed | 451c8e8c7 → 1b18c65a0 |
| feat/tech-lead-session-wrap | c266633eb → 194e8884c |

### Duplicadas / substituídas → podem ser apagadas

| Branch | Substituída por |
|---|---|
| fix/deploy-verify-truncation-explicit | `-r2` (mesmo diff, base mais antiga) — agora em `cloud-work` |
| fix/deploy-verify-truncation-explicit-r2 | entregue em `cloud-work` (`9ca71b42b`) — apagar quando `cloud-work` landar |
| feat/core-sidebar-modules | `-v2` (handover 1d87865a) |
| feat/vertical-seeds-plan | landou em 138255532 |

### Salvage / backup — conteúdo já está em dev → podem ser apagadas

| Branch | Evidência |
|---|---|
| salvage/stash-autostash-sidebar-2026-09 | fatos do `Sidebar.organ.yaml` já em dev (29d26cd32); resto é regen |
| feat/salvage-stash-sidebar-2026-09 | mesmo stash 528e11953 como `.orig` |
| salvage/primary-dev-2026-09-16c | só linhas de ledger, já em dev |
| backup/w8-wip-2 | W8 landou como 6bbcd50f3 |
| backup/primary-dev-divergence-20260601 | 3 linhas de `vector-costs.ndjson`, já em dev |
| chore/ledger-consolidation-20260818 | 0 commits únicos |

### Manter

- `ledgers` — branch órfã de propósito (`KB § PATTERNS/common/ledger-store.md`, owner 2026-09-24).

### Precisa de decisão do owner

- `claude/nifty-dijkstra-vgi6p6` — o domínio `.eco` já está em dev (24f9fbcc4). A outra metade
  (remover o link público "Entrar" da academia) **não** está, e o plano
  `project-history/plans/sso-session-lifecycle-2026-11.md` assume que o link fica (vira redirect
  pro core). Recomendação: manter o link ⇒ apagar a branch.

### 100% mergeadas (0 commits únicos, último commit < 2026-11-06) → podem ser apagadas

feat/academia-landing-content-polish, feat/agent-studio-integration, feat/agent-studio-isaia,
feat/cardhub-c-seed-fe, feat/cost-ledger-fold-into-commit, feat/dormant-scope,
feat/feat-tailwind-factory-theme-seam, feat/fix-embedding-refresh-retry-storm,
feat/fix-leads-query-in-filter-batching, feat/fix-scaffold-overlay-env-leak,
feat/fix-vps-ssh-circuit-breaker-hang, feat/julia-iter3-rebased,
feat/lch-p1-clientes-backfill-steady-state, feat/llm-vision-provider-switch,
feat/olx-portal-leads-mcp, feat/sw-api-be-certidoes, feat/sw-api-be-imoveis,
feat/sw-api-be-partes, feat/sw-api-be-roteiro, feat/sw-api-fe-certidoes-tab,
feat/sw-api-fe-leads-partes, feat/sw-api-fe-pessoa, feat/sw-api-identificadores,
feat/sw-api-identificadores-wire, feat/sw-identificador-search-path, feat/sw-julia-golive-rules,
feat/sw-s1-campanha-intake, feat/webhook-secret-inventory, fix/av-citavel-nao-selecionada,
fix/cache-pull-real-driver-types, fix/cache-pull-schema-drift,
fix/pdf-provenance-stamp-classification, salvage/primary-dev-2026-09-16,
salvage/primary-dev-2026-09-16b, chore/ledger-consolidation-20260818.

Confirmar com o tooling antes de apagar (podem ser refs do release/merge-queue):
`release/20260923-1113`, `release/20260923-1158`, `mq-candidate/bootstrap-1`, `mq-candidate/bootstrap-2`.

## 3 · Dependabot (45 PRs abertos)

### Fechar — produto inativo (19; inativo dorme, ninguém mexe)

academia-de-reciclagem (#404), commerce (#408, #353, #354), community (#347), igig (#400),
orbity (#406, #396, #383), p-studio (#343), store (#349, #329, #390, #398),
therapy-platform (#318, #337, #382, #385).

### Fechar — substituído (2)

vite 8.3.4 em seed/framework (#369) e seed/lib (#368): cobertos pelos grupos "all" (vite 8.3.5).

### Fechar — absorvido em `cloud-work` (quando landar)

#319 (PyJWT), #402 (products/seed all), #403 (social-wiring all), #411 (core all),
#405 (agents all — **só** rhf/autoprefixer/postcss; ver majors), #407 (monica all — idem),
#410 (seed/framework all), #409 (seed/lib all), #384/#392 (products/seed undici, postcss-selector-parser),
#386/#397 (social-wiring), #393/#395 (monica), #394/#336 (seed/lib postcss-selector-parser, source-map-js),
#317/#339 (seed/framework brace-expansion, source-map-js).
Os lockfiles foram regenerados a partir do `dev` atual (não a partir das branches do dependabot,
que estão até 3559 commits atrás); por isso algumas versões saíram um patch acima do PR
(ex.: vite 8.3.6, undici 7.30.2) — o lockfile é o freeze, os ranges continuam caret.

### Fechar — sem efeito

starlette #334 (seed/lib `<1.8`) e #399 (seed/framework `<1.11`): o cap não muda nada enquanto
`fastapi==0.121.0` exige `starlette<0.50`. Além disso os dois PRs divergem entre si, o que o
comentário do pyproject proíbe. Destino: um upgrade deliberado de fastapi+starlette juntos.

### Decisão do owner — majors (Gate 3 do noc-dep-update)

| PR | Salto | Recomendação |
|---|---|---|
| #405/#407 (parte) | `@hookform/resolvers` 5 → 7 (agents, monica) | migração própria, medida (Gate 3) |
| #311 | `lucide-react` 0.462 → 1.47 (seed/lib, fan-out pra frota) | projeto próprio; fechar PR |
| #335 | `tailwindcss` 3.4 → 4.3 (seed/lib; muda config/PostCSS da frota) | projeto próprio; fechar PR |
| #413/#412 | `actions/cache` e `cache/restore` 4 → 6.1 | fazer os dois juntos + `cache/save` (hoje restore v6 com save v4 = majors diferentes) |
| #388 | `google-genai` cap `<2.25` → `<2.34` | exige re-teste de resolve em venv limpo (comentário do pyproject) |

### Observado, não alterado

`vitest: ">=4.1.11 <4.1.12"` em seed/lib e seed/framework parece pin exato, mas é hold
deliberado com marcador `NOC-REMEDIATE[vitest-4112-hold]` (fbabda687): 4.1.12 é publish
quebrado e ainda é a última 4.1.x (2026-11-09). Fica até sair 4.1.13.

---

## 4 · Leva 2 — `cloud-work-2` (empilhada em `cloud-work`; entrega única)

Pedido do owner (2026-11-09): terminar tudo antes de entregar. Base: `origin/cloud-work`
(os lockfiles da leva 1 são a base dos bumps daqui). Quando `cloud-work` landar, rebase em
`origin/dev` descarta os 4 commits dela (patch-idênticos) e sobra só esta leva.

| Commit (assunto) | O quê | Verificação |
|---|---|---|
| feat(academia): drop the public "Entrar" link | owner 2026-11-09 (redo da metade FE de `claude/nifty-dijkstra-vgi6p6`); academia dorme | vitest 24, tsc, build |
| ci(deps): actions/cache … v6.1.0 (all 7 uses) | substitui #413/#412; inclui `cache/save` e o composite que o dependabot esqueceu | SHA = tag upstream; YAML ok; actionlint fica com o CI |
| chore(deps): @hookform/resolvers 5.9 -> 7.0 | parte major de #405/#407; só `zodResolver` é usado | SW tsc + vitest 1212 |
| chore(deps): google-genai cap <2.25 -> <2.34 | substitui #388; re-teste pedido pelo pyproject | venv limpo 34s → 2.33.0, `pip check` ok, 286 testes |
| feat(seed-lib)!: lucide-react 0.462 -> 1.70 | substitui #311; 236 nomes medidos, só Facebook/Instagram/Youtube sumiram → `@noctusai/lib/brand-icons` | frota inteira: ci/check/tsc/build/vitest |
| feat(seed-framework)!: Tailwind 3.4 -> 4.3 | substitui #335; migração no seed (entrada CSS única), visual pinado na v3 | diff de computed-style por classe (0 diferenças visuais), e2e core 46 + pixel diff, frota inteira verde |
| docs(deps): record @tailwindcss/postcss | Gate 0 (`dependency-additions.json`) | keeper warn-first resolvido |

### Para o owner / noc-0 saberem

- **Navegadores:** o Tailwind 4 exige Safari 16.4+, Chrome 111+, Firefox 128+. Abaixo disso o
  CSS degrada (cores/`@property`). Para o público atual (Brasil, mobile) é o ponto a pesar.
- **Paleta v3 pinada:** `seed/framework/frontend/src/tailwind-v3-palette.css`. Apagar o arquivo
  adota a paleta nova da v4 (mais saturada) — decisão visual, não técnica.
- **Produtos dormindo** (p-studio, dev-team, academia, …) ficam no setup v3/lucide 0.462 próprio.
  Ao acordar: `@config` no `src/index.css`, deps v4, codemod de classes (o script do
  commit Tailwind) e `brand-icons` se usarem ícones de marca. p-studio usa o seam `ownTheme`
  (OKLCH) — validar o seam com v4 antes de acordar.
- **CSS ~3 KB gzip maior** por produto (camada `@property`/theme da v4 + paleta pinada).
