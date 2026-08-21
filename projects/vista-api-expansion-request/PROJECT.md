# vista-api-expansion-request — Project Document

> **Filed 2026-08-05** as a **class-1 external-blocker** track, same shape as
> `projects/meta-app-review-publish-scopes/`. No code work is blocked; this
> project tracks an operational request to a vendor and the evaluation of
> their reply.
>
> **Self-contained by design (durable-docs rule).** A future clean-context
> agent must be able to evaluate Vista's response from THIS FILE ALONE,
> without re-running the probe or reading the conversation that produced it.
> Every number below was measured live — none is inferred.

- **Created:** 2026-08-05
- **Last updated:** 2026-08-21
- **Status:** 🟡 **PARTIALLY SATISFIED — Tier 1 is 2-of-3 granted and probe-verified.** Vista re-applied the permissions on key `…644c` and cleared their cache; re-probed live 2026-08-21 in a fresh process: `clientes/listar` → **200** (42,960 clients) and `clientes/detalhes` → **200**. `corretores/listar` is **still 401** and is the one open Tier-1 item. § 10's "which key did they grant?" question is **closed** — the same `…644c` key works, no rotation needed. Remaining: the corretores re-ask (§ 10a, drafted), the Tier-2 version question (now much better evidenced), and **the LGPD intake, which is what actually gates consuming any of this**.
- **Owner / stakeholders:** USER (joaoraphaelsst) sends + owns the vendor relationship · tech-lead evaluates the reply
- **Related docs:**
  - `KB § INTEGRATIONS/vista.md` — the authoritative Vista reference. § 3 (credential echo), § 4.2/4.5/4.6 (re-probed endpoint tables), § 5.3 (seed-canonical probe baseline), § 9 (the tiered ask + rationale)
  - `seed/lib/backend/noctusai_lib/integrations/vista/` — the canonical client + adapter
  - `mcp/vista/` — the MCP server exposing Vista to agents
  - `project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md` — the consuming initiative
- **Project slug:** `vista-api-expansion-request` (root `projects/` — the integration is seed-level, consumed by `erp-imobiliario` + `social-wiring`)

---

## 1. Context & Purpose

**Who Vista is.** Vista Software (vista.imobi / vistahost) is the real-estate
CRM used by ONE Consultoria Imobiliária. We integrate with their REST API to
read property listings and agency data. Our tenant is `oneconsu`, base URL
`https://oneconsu-rest.vistahost.com.br`.

**How auth works.** A single API key per tenant, passed as a `?key=` **query
parameter** on every request. No OAuth, no scopes, no per-user tokens. The
key lives in the root `.env` as `VISTA_API_KEY` (never `VITE_`-prefixed — the
browser must never see it; the ERP backend proxies).

**Why this project exists.** On 2026-08-05 we ran a full capability audit of
the Vista surface — 24 routes probed live — to answer "what can we actually
reach, and what would we have to ask Vista for?". The audit found real gaps
that block product work, and separated them into gaps a support request can
fix versus gaps it cannot. This project carries that ask to Vista and
evaluates what comes back.

---

## 2. The measured baseline (live probe, 2026-08-05)

**This is the evidence the whole request rests on.** If Vista's reply
contradicts something here, re-probe before conceding — but do not discard
these numbers casually; they were measured, not assumed.

> **⚠️ HISTORICAL as of 2026-08-21 — kept because it is what the request was
> built on.** Three things below have since changed; § 10 and § 11 hold
> current state:
> 1. **§ 2.2 is obsolete** — `clientes/listar` + `clientes/detalhes` were
>    granted and now return 200. Only `corretores/listar` still 401s.
> 2. **§ 2.3 contains two of OUR OWN typos.** `pesquisar` is not a documented
>    Vista method at all, and history is published singular (`historico`, not
>    `historicos`). Both were re-probed under the correct published names on
>    2026-08-21 and are still 404 — so the conclusion holds, but the evidence
>    for two rows did not, and "404 on a name the vendor never published"
>    proves nothing. `alterar` is likewise published as `update`.
> 3. **Counts moved** — 1,943 imóveis (not 1,928), and `clientes` turns out
>    to hold **42,960** rows.

### 2.1 What works today ✅

| Endpoint | Result |
|---|---|
| `/imoveis/listar` | 200 — **1,928 properties**, 964 pages (server caps `quantidade` at 50) |
| `/imoveis/detalhes` | 200 — full detail + `Caracteristicas` dict |
| `/imoveis/listarConteudo` | 200 with `pesquisa` — filter enums: 3 Status, 20 Categorias, 18 Cidades, ~370 Bairros |
| `/usuarios/listar` | 200 — **10 internal users** (name, email, sector, photo) |
| `/agencias/listar` | 200 — 1 row, "ONE CONSULTORIA IMOBILIARIA" |

Per-property fields: code, title, category, status, city/neighborhood/
address/CEP/state, sale + rental value, three area measures, bedrooms/suites/
parking, featured photo URL, listing broker (name + email), registration +
update dates.

**Two gaps inside the green zone that are NOT Vista's fault:**
- `Latitude`/`Longitude` are returned but **empty on every row** — a
  data-entry gap at the agency, not an API limitation. Do not put this in a
  support request; it is fixed inside Vista's UI by ONE's own staff.
- `banheiros` normalizes to null because Vista exposes only `BanheiroSocial`
  as a `"Sim"`/`"Não"` string, not a count.

### 2.2 Permission-gated — 401 🔒 (a request CAN unlock these)

```
/clientes/listar     401  Permissão Negada: "<key>" Método: clientes/listar
/clientes/detalhes   401  Permissão Negada: "<key>" Método: clientes/detalhes
/corretores/listar   401  Permissão Negada: "<key>" Método: corretores/listar
```

**The error format is the single most important finding in this project.**
Vista's authorization is **per method** — the 401 body literally names
`Método: clientes/listar`. That is why the request (§ 6) names methods
individually instead of asking for "access to clients". A method-named ask
is a one-line config change on their side; a resource-named ask is ambiguous
and invites a slow round-trip.

### 2.3 Absent — 404 ❌ (a request CANNOT unlock these)

Every route below returns `404 No route found`, **not** 401:

- **Client sub-routes:** `pesquisar`, `campos`, `porcorretor`, `poragencia`,
  `historicos`, `favoritos`, `cadastrar`, `alterar`, `cadhis`, `cadcor`,
  `lead`
- **Whole families:** `/leads`, `/atendimentos`, `/agendamentos`,
  `/negociacoes`, `/propostas`, `/vendas`, `/empreendimentos`,
  `/condominios`, `/tarefas`, `/reservas`, `/campanhas`, `/portais`,
  `/buscas`

**How the write routes were probed without issuing a write.** Vista's router
returns **405** for a route that exists but rejects the method, and **404**
when no route exists at all. `/imoveis/fotos` answers GET with 405, proving
the distinction is real. So a *read-only* GET separates "exists, needs POST"
from "absent" at zero risk to a live production CRM. Every write route above
answered 404 → genuinely absent, not merely method-mismatched.

**⚠️ Never POST to a live CRM to discover a route.** If a future agent needs
to re-verify the write surface, use the GET/405 technique. This constraint is
not negotiable regardless of how a Vista reply is worded.

### 2.4 The honest ambiguity

A 404 **cannot** distinguish "not provisioned for this tenant" from "not
built in this version of Vista's REST API". Only Vista can answer that. This
is precisely why § 6 Tier 2 is phrased as a *question* rather than a demand —
asking them to "enable" a route that does not exist would be a category error
and would cost credibility on the asks that are real.

---

## 3. Why each ask exists (product rationale)

| Ask | Blocks what |
|---|---|
| `clientes/listar` + `clientes/detalhes` | Any CRM-side client view in the ERP. Today the clients tab can only render a "permission pending" placeholder. |
| `corretores/listar` | Broker roster. **Partially substitutable** — `/usuarios/listar` already returns brokers with `Setor: "Corretores"`, and `/imoveis/listar` embeds the listing broker per property. Spend a request on it, but do not treat a refusal as blocking. |
| `clientes/lead` (POST) | **The architecturally significant one.** Without it there is no API path to write a captured lead back into Vista, so any lead-capture flow we build terminates in our own database and the agency has to check two systems. If Vista cannot offer this, it is a product decision to surface to the user — not a technical detail to absorb silently. |
| `negociacoes`/`propostas`/`vendas` | The deal pipeline. Currently invisible to us entirely. |
| Page-size / delta sync | At 1,928 properties and a 50-row cap, a full sync is 39 requests. Tolerable now; a delta filter (`advFilter`, whose spec is not in the public docs) would make it cheap. |

---

## 4. Security finding — the credential echo 🔴

**Vista returns our API key verbatim in 401 response bodies.** Confirmed by
string-matching the live 401 body against `VISTA_API_KEY`:

```json
{"status":401,"message":"Permissão Negada: \"<OUR API KEY IN PLAINTEXT>\" Método: clientes/listar"}
```

The key also rides in the `?key=` query string that httpx renders inside any
transport error.

**Our side is fixed** (commit `d3cb3c26`, 2026-08-05): `redact_api_key()` is
applied at both HTTP boundaries — `VistaClient._redact` and the independent
`VistaRESTAdapter` path in `real.py`. Regression guards
(`test_401_body_reaches_the_caller_redacted`,
`test_transport_error_url_reaches_the_caller_redacted`) were verified to go
**red** when the redaction is removed at source. The ERP HTTP router was
never a leak path — it maps typed errors to fixed Portuguese strings rather
than `str(exc)` — so the blast radius was agent contexts and application
logs, not end-user responses.

**Two things remain open:**
1. **Report it upstream** — included as Tier 4 in § 6. Any Vista customer
   logging error bodies is persisting a valid credential.
2. **🔴 Key rotation is a pending USER decision.** Redaction stops *future*
   exposure; it cannot un-expose what already leaked. Tracked in
   `project-history/auto-improvement.ndjson`
   (`target: .env — VISTA_API_KEY rotation after confirmed exposure`).

---

## 5. Constraints a future agent must respect

- **LGPD gate before the first `clientes` call.** `clientes` carries CPF,
  addresses and phones — third-party personal data. The data-category intake
  (`KB § PATTERNS/security/lgpd.md`) must land **before** the first
  successful call, not after. A granted permission is NOT authorization to
  start ingesting.
- **No write probes against the live CRM** (§ 2.3).
- **The key is never `VITE_`-prefixed** and never reaches the browser.
- **Re-probing is cheap and safe** — `vista.diagnostics.probe` +
  `vista.diagnostics.list_known_endpoints` are read-only. Read the
  `unexpected` field, not `status`: several endpoints answer a bare GET with
  400/401/405 **by design**, so a non-200 is not itself a fault.

---

## 6. The email as drafted (send-ready, PT-BR)

> **Why Portuguese:** Vista is a Brazilian vendor and this goes to their
> support desk.
>
> **Why the security defect is LAST:** leading a ticket with "you have a
> vulnerability" tends to route it to a slower security queue. Leading with
> "please enable three methods" keeps the cheap win on the fast path. This
> ordering is deliberate — preserve it if you re-draft.

---

**Assunto:** Solicitação de liberação de métodos na API REST + duas questões técnicas — tenant `oneconsu`

Prezada equipe Vista,

Somos responsáveis pela integração técnica da ONE Consultoria Imobiliária (tenant `oneconsu`) com a API REST de vocês. Fizemos um levantamento completo dos endpoints em 05/08/2026 e gostaríamos de tratar quatro pontos, do mais simples ao mais complexo.

**1. Liberação de permissão na chave atual** *(acreditamos ser apenas um flag de configuração)*

Estes três métodos retornam `401 Permissão Negada` com a nossa chave. Como a mensagem de erro nomeia o método explicitamente, entendemos que a autorização é por método — por isso listamos exatamente:

- `clientes/listar`
- `clientes/detalhes`
- `corretores/listar`

**2. Dúvidas sobre endpoints que retornam 404**

Os métodos abaixo estão na documentação pública, mas retornam `404 No route found` no nosso tenant — ou seja, não é questão de permissão. Poderiam esclarecer se cada um é **(a)** um módulo contratado à parte, **(b)** disponível em uma versão mais recente da API à qual não estamos apontados, ou **(c)** não ofertado?

`clientes/historicos` · `clientes/porcorretor` · `clientes/cadcor` · `clientes/lead` · `clientes/cadastrar` · `negociacoes/*` · `propostas/*` · `vendas/*` · `atendimentos/*` · `agendamentos/*`

Complementando: **existe uma URL base ou versão mais recente da API REST para este tenant?** Treze famílias documentadas retornando 404 nos parece mais compatível com uma diferença de versão/contrato do que com ausência real dos recursos.

**3. Gravação de leads** *(depende da resposta do item 2)*

O `clientes/lead` é o ponto mais crítico para nós: sem ele, não há caminho via API para gravar um lead captado de volta no CRM, o que obrigaria a corretora a consultar dois sistemas. Se houver forma de habilitá-lo, gostaríamos de priorizar.

**4. Operacional e segurança**

- **Paginação:** o parâmetro `quantidade` é limitado a 50 no servidor. Com 1.928 imóveis, uma sincronização completa exige 39 requisições. Esse limite é ajustável?
- **Sincronização incremental:** existe filtro de "alterados desde `DataAtualizacao`"? Não encontramos a especificação do `advFilter` na documentação pública.
- **⚠️ Falha de segurança:** o corpo da resposta `401` **devolve a chave de API do próprio chamador em texto puro**:
  ```json
  {"status":401,"message":"Permissão Negada: \"<CHAVE DE API>\" Método: clientes/listar"}
  ```
  Verificamos por comparação direta com a nossa credencial. Qualquer cliente que registre corpos de erro em log está persistindo uma credencial válida — inclusive em sistemas de terceiros. Já tratamos isso do nosso lado, mas a correção pertence à origem. Aproveitamos para solicitar o **procedimento de rotação de chave**, já que a nossa esteve exposta.

Ficamos à disposição para os detalhes técnicos do levantamento.

Atenciosamente,
*[assinatura]*

---

## 7. How to evaluate Vista's response

> **Read § 2 first.** Then work the tiers below. Record the verdict in § 9
> (change log) and update § 1 Status.

### 7.0 Before anything — re-probe

Vista may have changed things without telling us. One call:
`vista.diagnostics.probe`. Compare against § 2. If a 401 became a 200,
**the grant already landed** regardless of what the email says.

⚠️ **The MCP server caches modules in memory.** If a fix or a grant seems not
to have taken effect, confirm against a fresh process before concluding
anything — this exact trap cost real time on 2026-08-05.

### 7.1 Tier 1 (the three 401s) — did they grant?

| Vista says | Verdict | Next action |
|---|---|---|
| Granted | ✅ Verify by probe, not by their word | **STOP — do not start ingesting.** LGPD intake gates the first `clientes` call (§ 5). Surface to the user, then plan the consume slice. |
| Refused / needs paid module | ⚠️ Legitimate commercial answer | Surface the cost to the user. Do not re-ask. |
| Silence / deflection | ⚠️ | Re-ask naming ONLY the three methods verbatim. Ambiguity is the usual cause. |
| "Use `/clientes/pesquisar` instead" | ❌ **Push back with evidence** | That route is 404 on our tenant (§ 2.3). Ask them to confirm it is live for `oneconsu` — likely they are reading generic docs. |

### 7.2 Tier 2 (the 404s) — which of (a)/(b)/(c)?

- **(a) separate contracted module** → a pricing decision. Surface to the
  user with the § 3 blocking table so they can judge value. Do not commit.
- **(b) newer API version / different base URL** → 🎯 **the highest-value
  outcome.** Get the new base URL, then **re-probe everything in § 2 against
  it** before believing any of it. A version bump could change response
  shapes, so treat it as a new integration surface: re-run calibration, and
  expect `KB § INTEGRATIONS/vista.md` § 4 to need a full rewrite.
- **(c) not offered** → close the question permanently. Record it in
  `vista.md` § 4.6 so nobody re-asks. Then tell the user plainly that the
  deal pipeline and lead write-back are **not reachable via API**, which is
  a product-shape constraint, not a task to work around.

### 7.3 Tier 3 (`clientes/lead`) — the decision that changes architecture

If **unavailable**, do not quietly build a parallel lead store and call it
done. Surface the consequence explicitly: *leads captured by our funnel will
live only in our database; the agency must check two systems.* The user
decides whether that is acceptable, whether to pursue a non-API path
(CSV/manual/webhook), or whether to reconsider the feature. **This is a
user-facing product decision, not an engineering detail.**

### 7.4 Tier 4 (operational + security)

- **Page-size raised** → update `DEFAULT_PAGE_SIZE` in
  `noctusai_lib.integrations.vista.client` and re-check the 50-cap claims in
  `vista.md` § 2.
- **Delta-sync / `advFilter` spec provided** → high value; fold the spec into
  `vista.md` § 2 and revisit the sync loop, which currently full-crawls.
- **Security acknowledged** → note it in `vista.md` § 3. **Keep our redaction
  regardless** — never remove a defensive layer because a vendor promises a
  fix.
- **Rotation procedure provided** → hand to the user. Rotation itself is
  theirs to authorize; it touches the root `.env` **and** the prod env
  together, so an uncoordinated rotation breaks production.

### 7.5 If the reply is vague or contradicts § 2

Re-probe (§ 7.0) and reply with the concrete evidence: the exact path, the
exact HTTP status, the exact error body (**with the key redacted** — do not
paste our credential back to them). Vendor support frequently answers from
generic documentation rather than the tenant's actual provisioning; a
measured counter-example resolves it fastest.

---

## 8. Success criteria

1. A definitive (a)/(b)/(c) answer for every Tier-2 family — no open ❓.
2. Tier 1 either granted-and-probe-verified, or refused with a reason the
   user has seen.
3. `clientes/lead` availability answered **yes or no**, with the product
   consequence surfaced to the user either way.
4. `KB § INTEGRATIONS/vista.md` § 4 + § 9 updated to match the outcome, so
   the next agent inherits truth rather than this project's assumptions.
5. This project flipped to ✅ SHIPPED or ❌ CLOSED with the verdict recorded,
   then archived per `noc-archive-absorb` (absorb learnings → KB **before**
   deleting).

---

## 9. Change log

| Date | Change | Author |
|---|---|---|
| 2026-08-21 | **✅ The grant LANDED — Tier 1 is 2-of-3.** Vista replied that they had re-adjusted the endpoint permissions on `…644c` and cleared their system cache. Verified per § 7.0 (probe, not their word), twice: `vista.diagnostics.probe` and raw HTTP in a fresh process. `clientes/listar` 401 → **200** (42,960 clients); `clientes/detalhes` 401 → **200**; `corretores/listar` **still 401** → § 10a re-ask drafted. § 10's key question is closed: same key, no rotation. Also landed, all live-measured: the `clientes` field set mapped **without reading any client record** (11 of 32 candidates accepted — and the old guess omitted 7 fields the tenant does expose, which matters because calibration narrows and never widens); LGPD categories corrected (no CPF/address/email, but DataNascimento/Sexo/EstadoCivil/Profissao/Celular); `/imoveis` **delta sync solved** via `filter` on `DataAtualizacao`, closing a Tier-4 ask with no vendor involvement, while `/clientes` has no such field (860-request full crawl); `/clientes/listarConteudo`'s PHP crash fixed upstream; two § 2.3 route names exposed as **our own typos** (`pesquisar` is not a Vista method; history is `historico`, not `historicos`). Code: endpoint baseline re-graded so a future 401 reads as a ROLLBACK, and calibration now drops every rejected field per pass — **13 round-trips → 2**, measured live. `vista.md` § 2/4.2/4.5/8/9 updated. | Claude Opus 5 |
| 2026-08-19 | **Re-probe: the grant has NOT landed.** Verified twice (MCP probe + raw HTTP, fresh process, well-formed payloads) — `clientes/listar`, `clientes/detalhes`, `corretores/listar` all still 401. Full § 2.3 404 surface re-swept: nothing moved. Two new endpoint facts: `/corretores/detalhes` + `/corretores/listarConteudo` are 404; `/clientes/listarConteudo` exists ungated but crashes (raw PHP `in_array()` error) — not a partial grant. Separately, refined the gated MCP surface to parity with the working one (silent pagination drop, dead candidate-field constant, **401 poisoning the calibration cache**, missing `vista.clientes.get`, unenforced Fake↔Real parity) so a grant lands on working code instead of stubs. `vista.md` § 4.2/4.5/5.3/8/9 updated. Status → BLOCKED-EXTERNAL, awaiting the key question in § 10. | Claude Opus 5 |
| 2026-08-05 | Project filed. Live audit of 24 Vista routes established the § 2 baseline; the 401-vs-404 split and the read-only 405/404 write-probe technique were the two enabling findings. Email drafted (§ 6). Related same-day fix `d3cb3c26` shipped the credential redaction, corrected the endpoint tables in `vista.md`, and lifted `PROBE_ENDPOINTS` to a seed-canonical baseline after finding it forked at N=2. **Status: awaiting user send.** | Claude Opus 5 |


---

## 10. ✅ RESOLVED — the grant landed on our existing key

> **Closed 2026-08-21.** This section asked which key Vista had granted,
> because the ask was reportedly approved on 2026-08-05 yet all three methods
> still 401'd on 2026-08-19. The answer turned out to be the least dramatic
> of the three possibilities the table listed: **it was acknowledged but not
> actually applied.** Vista then re-applied it and cleared their system
> cache, and it took effect on the *same* key, `…644c`.
>
> **No key rotation is needed to use the grant** — which decouples the
> § 4 credential-echo rotation from this project. That rotation is still
> worth doing on its own merits, and is still the user's call (§ 7.4).

**What the 2026-08-19 investigation got right, and why it still mattered.**
It refused to record the ask as satisfied on the vendor's word, and it
excluded both false negatives (MCP module cache, malformed request) before
concluding. That was correct: the grant genuinely was not in effect. Had we
recorded "granted" from the reply, the 2026-08-21 flip would have looked like
a regression instead of the fix it was. **Keep verifying vendor claims by
probe** (§ 7.0) — this cycle is the argument for it, not against it.

**Live state after the grant** (all measured 2026-08-21, fresh process):

| Method | Before | After |
|---|---|---|
| `/clientes/listar` | 401 | ✅ **200** — 42,960 clients |
| `/clientes/detalhes` | 401 | ✅ **200** — with `?cliente=<id>` |
| `/corretores/listar` | 401 | 🔒 **401 — unchanged** |

---

## 10a. The one open Tier-1 item — `corretores/listar`

Vista's reply asked us to send the request details if the error persisted:
*"nos encaminhem a requisição realizada (preferencialmente com a URL, método
e retorno recebido)"*. It does persist, for exactly one method. Send this.

**🔴 Redaction rule: the `key=` value below MUST stay redacted.** Vista
echoes our key in 401 bodies (§ 4) — pasting the real one back into a
support ticket re-exposes the credential we already had to defend against.

---

**Assunto:** Re: liberação de métodos — `corretores/listar` ainda retorna 401 (tenant `oneconsu`)

Prezada equipe Vista,

Obrigado pelo retorno e pelo ajuste. Confirmamos que **dois dos três métodos
foram liberados com sucesso** na chave terminada em `644c`:

- `clientes/listar` → **200 OK**
- `clientes/detalhes` → **200 OK**

Resta **um** método ainda retornando `401`. Segue a requisição conforme
solicitado:

- **Método HTTP:** `GET`
- **URL:** `https://oneconsu-rest.vistahost.com.br/corretores/listar?key=<CHAVE_644c>&pesquisa={"fields":["Codigo","Nome"],"paginacao":{"pagina":1,"quantidade":1}}`
- **Header:** `Accept: application/json`
- **Retorno (HTTP 401):**
  ```json
  {"status":401,"message":"Permissão Negada: \"<CHAVE_644c>\" Método: corretores/listar"}
  ```

Observação que talvez ajude no diagnóstico: os três métodos foram
solicitados no mesmo chamado e para a mesma chave, e dois deles foram
liberados — portanto não parece ser propagação pendente, e sim que
`corretores/listar` não entrou no ajuste.

Aproveitamos para duas questões técnicas:

1. **Versão da API deste tenant.** Vários métodos da documentação pública
   retornam `404 No route found` aqui (`imoveis/campos`, `imoveis/listas`,
   `imoveis/historico`, `imoveis/docs`, `imoveis/porcorretor`,
   `clientes/campos`, `clientes/historico`, entre outros), enquanto métodos
   que **não constam na documentação** funcionam normalmente
   (`imoveis/listarConteudo`, `clientes/listarConteudo`, `usuarios/listar`,
   `agencias/listar`). Qual versão da API REST o tenant `oneconsu` utiliza,
   existe URL base mais recente, e onde encontramos a documentação
   correspondente a essa versão?

2. **`DataAtualizacao` em `clientes`.** Em `imoveis/listar` conseguimos
   sincronização incremental via `filter` sobre `DataAtualizacao`, o que
   funciona muito bem. Em `clientes/listar` esse campo não está disponível —
   com 42.960 registros e o limite de 50 por página, qualquer atualização
   exige 860 requisições. É possível expor `DataAtualizacao` em `clientes`
   (ou elevar o limite de `quantidade`)?

Ficamos à disposição.

Atenciosamente,
*[assinatura]*

---

## 11. What is NOT unblocked by this grant

Recorded so the next agent does not over-read the win.

- **🔴 LGPD gates consumption, and the grant does not touch it.** Permission
  from Vista is not authorization to ingest third-party personal data. The
  data-category intake (`KB § PATTERNS/security/lgpd.md`) must land before
  any bulk `clientes` pull — and it must be written against the **real**
  field set (§ 4.2 of `vista.md`), not the old "CPF, addresses and phones"
  assumption, which was wrong. Actual: no CPF, no address, no email; but
  `Celular`, `DataNascimento`, `Sexo`, `EstadoCivil`, `Profissao`.
- **Lead write-back is still impossible.** `/clientes/lead` is 404, not 401 —
  no permission unlocks it. A lead-capture flow still terminates in our own
  database and the agency still has two systems to check. This remains a
  **product decision to surface to the user** (§ 7.3), unchanged.
- **The deal pipeline is still invisible.** `negociacoes` / `propostas` /
  `vendas` are 404 — pending the Tier-2 version answer.
- **`clientes` cannot be delta-synced.** No `DataAtualizacao` on that family;
  860 requests per full refresh. Design no sync loop over it until § 10a's
  question is answered.
