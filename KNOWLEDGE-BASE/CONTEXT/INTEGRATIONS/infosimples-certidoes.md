# InfoSimples certidões — what the docs say vs. what we observe (social-wiring)

> **Purpose.** Reference for the InfoSimples certidão integration
> (`products/social-wiring/backend/app/modules/certidoes/`): the contract we rely on, the Receita
> "positiva com efeitos de negativa" (PCEN) 2ª-via rule, and a **living** section of behaviour we
> measured ourselves — so our docs can become better than the vendor's.
>
> **Owner directive (2026-10-01).** "Implement a watcher on this process to catch signals so we find
> value regarding 'positiva com efeitos de negativa', so we can improve our own docs and be better
> than their official docs and API … deal well with the process itself and learn and improve/increase
> our repertoire." Reporting is not the goal — the learned classification feeds back into runtime
> behaviour (§3) and into this doc + the artifact's knowledge sidecar (§5).

## 1 · Receita / PGFN (`receita-federal/pgfn`) — documented contract

Source: `https://api.infosimples.com/consultas/docs/receita-federal/pgfn.md`.

- For a person/company holding a PCEN certidão the PGFN portal **cannot issue a new one**. The vendor's
  recipe is `preferencia_emissao=2via`: the API retrieves the still-valid previously issued certidão
  ("o efeito prático para uso da certidão é o mesmo de emitir uma nova certidão"). Vendor suggestion:
  always prefer 2ª via.
- `preferencia_emissao`: `nova` (default) | `2via`. `birthdate` required for CPF.
- Response `data[0]` carries (among others): `tipo` ("Positiva com efeitos de negativa" / "Negativa" …),
  `situacao`, `emissao_data`, `validade` / `validade_data` / `validade_prorrogada`,
  `conseguiu_emitir_certidao_negativa`, `certidao_codigo`. `header.price` + `header.billable` give the cost.
- Failure range: `code in range(600, 799)`. **The docs give NO code or message for "nova refused because a
  PCEN is in force"** — that is the gap the watcher measures.

## 2 · How the integration behaves (code, not docs)

- `service._fetch_certidao` — every HTTP call is turned into an observation row
  (`aprendizado.montar_observacao`), success or failure, **every tipo** (not only Receita).
- Receita (`segunda_via_fallback`): `nova` refused in the 600–798 range ⇒ ONE `2via` retry (no backoff),
  unless the failure signature is **confirmed transitória** (§3). The result is stamped
  `api_response.noctus_segunda_via` and the visible note "2ª via — data de emissão original".
- Per-documento shortcut: when this exact documento's latest successful Receita emission was a PCEN 2ª via
  whose printed validity still covers today, the first call is `2via` (a `nova` would be a billed call that
  must fail); if that `2via` is itself refused, one `nova` follows.
- `resultado` is set deterministically to `positiva_com_efeito_de_negativa` from the source's own printed
  `data[0].tipo` (Receita only) — no AI guess.
- LGPD: observations store **no token, birthdate, name or full CPF/CNPJ**. `params` is an allowlist
  (`tipo`, `abrangencia`, `modelo`, `preferencia_emissao`) plus the *names* of the keys sent; the documento is
  an org-scoped HMAC (`documento_hash`, salt env `CERTIDAO_OBS_SALT`).
- Recording is best-effort: a failure is logged at ERROR and never breaks the emission.
- **Pre-call requirements (F112/F113).** `registry.pendencia_pre_chamada` runs before every paid call: a
  tipo's `requer_credencial` (org GOV.BR login) or `requer_campos` (`{tipo_documento: (consulta field,…)}` —
  `cnd_federal` declares `{"cpf": ("data_nascimento",)}`) unmet ⇒ InfoSimples is NOT called; the cell parks
  `pendente` with a pt-BR message (`credencial_govbr` | `dados_parte` pendência, `tipo_de_pendencia`). Class
  guards for undeclared requirements: a login-naming failure (`e_erro_login_govbr`, 606 and 604) or a
  "parâmetro obrigatório" failure (`e_erro_parametro_obrigatorio`) parks the same pendência + logs a WARNING.
  A 606 is never retried nor 2ª-via'd (the same request fails the same way). Observed: `trf3` once answered
  606 "são necessários os seguintes parâmetros adicionais: nome_mae, birthdate, tipo_documento, documento"
  (1 of 73 calls, 29 successes) — conditional, so not declared pre-call; the guard catches it.
- **Account/vendor-level refusals are not retried (2026-11-07).** `registry.falha_de_conta_ou_fonte`: 603
  (sem saldo / token recusado), 615 whose text says "API pausada" and 608 (excesso de tentativas do TRF)
  end the fetch at once — no backoff retries, no 2ª via — and the row carries a pt-BR reason
  (`MSG_SEM_SALDO`, `MSG_API_PAUSADA`, …) with the raw answer kept in `api_response`. Prod saw 257 CENPROT
  calls answered "API pausada" and 19 "sem saldo" (vendor/account side: owner action, not a code fix). A plain
  615 without "pausada" (source momentarily down) keeps the retry loop.

## 3 · The learned trigger

A failure is fingerprinted as a **signature** = `"<code>|<message>|<errors>"`, lowercased, accent-folded,
every digit/URL/e-mail stripped (so protocol numbers and dates do not split identical failures).

For each `nova` failure the outcome is read off the next calls:

| Outcome | Meaning |
|---|---|
| `pcen` | the immediate 2ª via succeeded **and** `data[0].tipo` is PCEN |
| `transitoria` | the 2ª via failed too, or a later `nova` for the same documento+tipo succeeded |
| `via2_outro` | the 2ª via succeeded but is not PCEN (informational) |

A signature is **confirmed** only with `LIMIAR_CONFIRMACAO = 3` conclusive observations **and** a
`MARGEM_CONFIRMACAO = 3×` lead over the opposing class; otherwise `desconhecida`. Effect on
`service._precisa_segunda_via`: confirmed **transitória** ⇒ no 2ª-via retry (saves the billed call);
confirmed **pcen** and **desconhecida** ⇒ retry exactly as before (unknown = try once, record, learn).

Every reclassification is an append-only row in `certidao_emissao_aprendizados` (when did the system learn
what) and a `WARNING` log line carrying the marker `CERTIDAO_APRENDIZADO` for the ops log review.

## 4 · Contract gate for the Receita PCEN 2ª via (owner decision A + amendment, 2026-10-01)

The 2ª via carries the ORIGINAL emission date by design, so the 30-day emission rule would reject a perfectly
valid certidão. Narrow exception (`contrato_gerador/certidao_pcen.py` — ONE rule shared by the contract gate,
the per-party cell and the party summary): `resultado = PCEN ∧ came via 2ª via ∧ validade parsed` ⇒ judged by
the **printed validity** (`validade_ate ≥ data de assinatura`). All other tipos/cases keep the 30-day rule.

It is never a silent pass: the readiness report gets a `confirmacoes` entry and the contract is **not
`pronto`** until the operator acknowledges it ("Entendi — seguir com esta certidão") or asks support
("Tenho dúvida — falar com o suporte"). The acknowledgment is stored per resultado
(`certidao_resultados.pcen_ciente_por/_em/_validade`), is valid only for the printed validity it was given for,
and is cleared whenever the row is re-processed. `POST …/gerar` re-checks it.
"Tenho dúvida" routes to the office's **support contact** — `org_dados_cadastrais.suporte_*` (migration 189,
Configurações → Imobiliária → Contato de suporte). It is deliberately separate from the lead-notification
recipients (owner decision 2026-10-02) and never falls back to them: unset ⇒ the UI says none is configured.

## 5 · Comportamento observado (vs documentação oficial)

Regenerate with the MCP tool (dev-side; commit the result):

```
noctus.dev.certidoes_emissao_aprendizado mode=report   # read-only: stats, signatures, novos aprendizados
noctus.dev.certidoes_emissao_aprendizado mode=sync     # idempotent: rewrites the region below + the sidecar
```

The same run updates the artifact's knowledge sidecar
`products/social-wiring/backend/app/modules/certidoes/infosimples.knowledge.yaml` (`[observado]` entries of
known_facts / errors_encountered / drifts_surfaced — hand-written entries are preserved). Output is derived
only from the data, so re-running on unchanged data writes nothing.

<!-- BEGIN observed-behaviour (generated by noctus.dev.certidoes_emissao_aprendizado) -->
Gerado a partir de `certidao_emissao_observacoes` / `certidao_emissao_aprendizados` (`noctus.dev.certidoes_emissao_aprendizado mode=sync`). Não editar à mão.

Observações analisadas: **1206** (limiar de confirmação: 3, margem: 3×).

### `cenprot`

- Chamadas: 303 · sucesso: 0 (0%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `615|o site ou aplicativo de origem parece estar indisponivel|a api foi pausada temporariamente o motivo mais provavel para isso ter sido feito e instabilidade na fonte de origem se voce notou que a fonte de origem esta se comportando normalmente entre em contato com o suporte via email` | 282 | desconhecida |
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 21 | transitoria |

### `cnd_fazenda_sp`

- Chamadas: 120 · sucesso: 6 (5%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `615|o site ou aplicativo de origem parece estar indisponivel|a api foi pausada temporariamente o motivo mais provavel para isso ter sido feito e instabilidade na fonte de origem se voce notou que a fonte de origem esta se comportando normalmente entre em contato com o suporte via email` | 48 | desconhecida |
| `606|parametros obrigatorios nao foram enviados por favor verifique a documentacao de uso do servico|um dos pares de parametros deve ser informado para login no gov br login cpf login senha ou pkcs cert pkcs pass` | 30 | desconhecida |
| `604|a consulta nao foi validada antes de pesquisar a fonte de origem|o portal de origem da consulta sefaz sp certidao negativa de debitos passou a exigir autenticacao via gov br para realizar a consulta passe a informar os parametros login cpf e login senha ou pkcs cert e pkcs pass para autenticacao` | 18 | desconhecida |
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 18 | transitoria |

### `cnd_federal`

- Chamadas: 146 · sucesso: 65 (45%) · emissões PCEN: 0
- Retentativas 2ª via: 18 (sem sucesso: 16) · custo: R$ 2.4000 (sem sucesso: R$ 1.8000)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|` | 20 | transitoria |
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 19 | transitoria |
| `611|os dados estao incompletos no site ou aplicativo de origem e nao puderam ser retornados|as informacoes disponiveis na receita federal sobre o contribuinte sao insuficientes para emitir a certidao pela internet` | 18 | transitoria |
| `620|o site ou aplicativo de origem emitiu um erro que provavelmente nao mudara em breve para esta consulta leia o para saber mais|inscricao no cnpj inapta omissao de declaracoes emissao de certidao nao permitida` | 9 | transitoria |
| `615|o site ou aplicativo de origem parece estar indisponivel|` | 6 | desconhecida |
| `|readtimeout|` | 3 | desconhecida |
| `606|parametros obrigatorios nao foram enviados por favor verifique a documentacao de uso do servico|o parametro birthdate e obrigatorio para a consulta por cpf deve estar no formato aaaa mm dd` | 3 | desconhecida |
| `611|os dados estao incompletos no site ou aplicativo de origem e nao puderam ser retornados|as informacoes disponiveis na receita federal e na procuradoria geral da fazenda nacional sobre o contribuinte sao insuficientes para emitir a certidao pela internet` | 2 | desconhecida |
| `615|o site ou aplicativo de origem parece estar indisponivel|nao foi possivel emitir a certidao tente novamente em alguns minutos` | 1 | desconhecida |

### `cnd_trabalhista_tst`

- Chamadas: 100 · sucesso: 82 (82%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 18 | transitoria |

### `trf3`

- Chamadas: 170 · sucesso: 67 (39%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|` | 44 | transitoria |
| `|readtimeout|` | 36 | desconhecida |
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 19 | transitoria |
| `608|os parametros foram recusados pelo site ou aplicativo de origem que processou esta consulta|os dados enviados foram recusados pelo site do trf devido ao envio de muitas tentativas em pouco tempo desse mesmo cpf cnpj tente novamente mais tarde` | 2 | desconhecida |
| `606|parametros obrigatorios nao foram enviados por favor verifique a documentacao de uso do servico|sao necessarios os seguintes parametros adicionais para solicitar esta certidao nome mae birthdate tipo documento e documento` | 1 | desconhecida |
| `|remoteprotocolerror server disconnected without sending a response|` | 1 | desconhecida |

### `trf3_sp`

- Chamadas: 164 · sucesso: 66 (40%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|` | 41 | transitoria |
| `|readtimeout|` | 38 | desconhecida |
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 19 | transitoria |

### `trt2_digital`

- Chamadas: 104 · sucesso: 81 (78%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 18 | transitoria |
| `600|um erro inesperado ocorreu e sera analisado|` | 3 | desconhecida |
| `609|tentativas de consultar o site ou aplicativo de origem excedidas|` | 2 | desconhecida |

### `trt2_fisico`

- Chamadas: 99 · sucesso: 81 (82%) · emissões PCEN: 0
- Retentativas 2ª via: 0 (sem sucesso: 0) · custo: R$ 0 (sem sucesso: R$ 0)

| Assinatura da falha | Ocorrências | Classe |
|---|---:|---|
| `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` | 18 | transitoria |

### Aprendizados em vigor

- `cnd_federal` · `603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api` → **transitoria** (desde 2026-10-23)
- `cnd_federal` · `611|os dados estao incompletos no site ou aplicativo de origem e nao puderam ser retornados|as informacoes disponiveis na receita federal sobre o contribuinte sao insuficientes para emitir a certidao pela internet` → **transitoria** (desde 2026-10-23)
- `cnd_federal` · `618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|` → **transitoria** (desde 2026-10-23)
- `cnd_federal` · `620|o site ou aplicativo de origem emitiu um erro que provavelmente nao mudara em breve para esta consulta leia o para saber mais|inscricao no cnpj inapta omissao de declaracoes emissao de certidao nao permitida` → **transitoria** (desde 2026-11-03)

### Sugestões

- cenprot: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- cnd_fazenda_sp: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- cnd_federal: a assinatura '618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|' é transitória (5 casos) — o gatilho já NÃO pede 2ª via para ela.
- cnd_federal: a assinatura '615|o site ou aplicativo de origem parece estar indisponivel|' ainda é desconhecida (faltam ~2 observações conclusivas).
- cnd_federal: a assinatura '611|os dados estao incompletos no site ou aplicativo de origem e nao puderam ser retornados|as informacoes disponiveis na receita federal sobre o contribuinte sao insuficientes para emitir a certidao pela internet' é transitória (3 casos) — o gatilho já NÃO pede 2ª via para ela.
- cnd_federal: a assinatura '|readtimeout|' ainda é desconhecida (faltam ~3 observações conclusivas).
- cnd_federal: a assinatura '620|o site ou aplicativo de origem emitiu um erro que provavelmente nao mudara em breve para esta consulta leia o para saber mais|inscricao no cnpj inapta omissao de declaracoes emissao de certidao nao permitida' é transitória (3 casos) — o gatilho já NÃO pede 2ª via para ela.
- cnd_federal: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- cnd_federal: a assinatura '606|parametros obrigatorios nao foram enviados por favor verifique a documentacao de uso do servico|o parametro birthdate e obrigatorio para a consulta por cpf deve estar no formato aaaa mm dd' ainda é desconhecida (faltam ~2 observações conclusivas).
- cnd_federal: a assinatura '611|os dados estao incompletos no site ou aplicativo de origem e nao puderam ser retornados|as informacoes disponiveis na receita federal e na procuradoria geral da fazenda nacional sobre o contribuinte sao insuficientes para emitir a certidao pela internet' ainda é desconhecida (faltam ~2 observações conclusivas).
- cnd_federal: a assinatura '615|o site ou aplicativo de origem parece estar indisponivel|nao foi possivel emitir a certidao tente novamente em alguns minutos' ainda é desconhecida (faltam ~2 observações conclusivas).
- cnd_trabalhista_tst: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- trf3: a assinatura '618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|' é transitória (5 casos) — o gatilho já NÃO pede 2ª via para ela.
- trf3: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- trf3: a assinatura '|readtimeout|' ainda é desconhecida (faltam ~3 observações conclusivas).
- trf3_sp: a assinatura '|readtimeout|' ainda é desconhecida (faltam ~3 observações conclusivas).
- trf3_sp: a assinatura '618|o site ou aplicativo de origem esta sobrecarregado tente novamente em alguns instantes|' é transitória (5 casos) — o gatilho já NÃO pede 2ª via para ela.
- trf3_sp: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- trt2_digital: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
- trt2_fisico: a assinatura '603|o token informado nao tem autorizacao de acesso ao servico verifique se ele continua ativo e se ele nao possui algum limite de uso especificado|a conta esta sem saldo adicione saldo para conseguir usar a api' é transitória (6 casos) — o gatilho já NÃO pede 2ª via para ela.
<!-- END observed-behaviour -->

## 5b · Live probe — 2026-11-07 (owner-requested, 6 tipos, real One Consultoria consultas)

Run inside the prod `noctus-social-wiring` container through the app's own `_fetch_certidao` and credential chain; every call is recorded in `certidao_emissao_observacoes` with `resultado_id IS NULL`. Cost R$0.84; failed calls weren't billed.

| tipo | doc | result | what it settles |
|---|---|---|---|
| `cnd_trabalhista_tst` | CPF | 200, 3.0 s | Working. |
| `trf3_sp` | CNPJ | 200, 21 s | Working; well under the 240 s cap today. The 14-day p95 of 241 s is source-side slowness, not our timeout being wrong. |
| `trf3` | CPF | 200, 20 s | Working. |
| `trt2_digital` | CNPJ | 600 "erro inesperado" ×3, free | The full 14-digit CNPJ sent as `cnpj_raiz` IS accepted: 38 CNPJ successes all-time, 3 more on 2026-11-07 from real use. The 600 is specific to this one company (vendor-side "será analisado"), not a format bug. |
| `cnd_federal` | CPF + birthdate | 615 "indisponível" ×3, free | Receita source momentarily down (44 s, then fast 615s). Transient; the same day's real use emitted fine. |
| `cenprot` | CNPJ | 615 "API pausada" ×3, free | The vendor pause is STILL in effect. Owner support ticket needed; until then CENPROT stays manual upload. |

Not probed: `cnd_fazenda_sp` / `divida_ativa_sp` (need the org's gov.br login, which isn't configured; the registry parks them as `pendente` without a billed call) and `tjsp`.

## 6 · Composes with

`KB § PATTERNS/common/build-learn-cache-mindset.md` (the sidecar) · `KB § PATTERNS/backend/seed-fake-real-adapter.md` ·
`KB § PATTERNS/common/remediation-markers.md`.
