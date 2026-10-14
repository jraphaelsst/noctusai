# Invoices — NF-e, NFS-e, NFS-e Nacional (consume-side reference)

> Seed organ: `noctusai_lib.integrations.invoices`. Shipped 2026-10-13
> (commerce P4 slice E, decisions D36–D38). Built Fake-first and tested against
> Focus **homologação** only — no provider contract until P6 validation.
> **Replication-to-seed lift** from `products/adconnect/.../nfe_service.py`
> (asleep product, untouched; it can migrate onto the organ later).

## What ships

- `InvoiceProvider` Protocol · `FakeInvoiceProvider` · `FocusNFeInvoiceProvider`
  (httpx, Basic auth) · `make_invoice_provider` (fake-or-refuse via
  `integrations.fake_or_refuse`, production-guarded).
- Surface: `verify_credentials` · `ensure_company` · `upload_certificate` ·
  `set_nfse_mode` · `issue` (idempotent on `ref`) · `get(kind, ref)` ·
  `cancel(kind, ref, reason=)` · `fetch_document(url)` · `parse_webhook`.
- `types.py` owns `InvoiceKind` (`nfe`·`nfse`) · `InvoiceStatus`
  (`processing`·`authorized`·`rejected`·`cancelled`·`error`) · `NfseMode`
  (`nacional`·`municipal`) and every DTO. Money is integer cents; the adapter
  converts to reais only at the wire.
- `inspect_pkcs12(pfx, password) -> CertificateInfo` — local A1 inspection
  (expiry + CNPJ from ICP-Brasil OID `2.16.76.1.3.3`, CN `:cnpj` fallback). One
  generic `InvoiceCertificateError` for bad file AND wrong password. The host
  calls it BEFORE forwarding (CNPJ ≠ store CNPJ ⇒ 422 before anything is sent).
- `CompanyTokenStore` — per-company Focus tokens, encrypted at rest through the
  seed `CredentialStore` (`security.token_store`, Fernet), keyed
  `(org_id, "invoices_focusnfe:<company_ref>")`, environment + CNPJ as metadata;
  refuses a token read for another environment; a CNPJ change rotates.

## Defects of the adconnect adapter, fixed

| adconnect | organ |
|---|---|
| `cancel`/`status` keyed on the access key (`chave`) | everything keyed on OUR `ref` |
| unknown status / 404 ⇒ silent `pendente` | unknown ⇒ `InvoiceProviderError(code="unknown_status")`; 404 ⇒ `InvoiceNotFound` |
| `logger.error("... (%s)", exc)` (lines 293/352/374) | no exception or provider body is ever logged or placed in a message |

## Production guard (D36)

`producao` needs BOTH env `FOCUSNFE_ALLOW_PRODUCTION=1` (literal `1`) AND the
platform credential `focusnfe_environment=producao`; environment is config,
never a request. Credential `producao` without the env switch is **refused**
(`production_not_allowed`), never silently downgraded. Token tier: platform
credential `focusnfe_token_environment` declares which environment the account
token belongs to; a mismatch is refused and `producao` requires it declared.

## Focus facts — verified vs unverified (doc.focusnfe.com.br, 2026-10-13)

Verified (official reference + OpenAPI embedded in the pages): hosts
`api.focusnfe.com.br` / `homologacao.focusnfe.com.br`, prefix `/v2`
([ambiente](https://doc.focusnfe.com.br/reference/ambiente)); Basic auth, token
as user + blank password ([autenticacao](https://doc.focusnfe.com.br/reference/autenticacao));
companies [criar](https://doc.focusnfe.com.br/reference/criar_empresa) ·
[atualizar](https://doc.focusnfe.com.br/reference/atualizar_empresa) ·
[consultar](https://doc.focusnfe.com.br/reference/consultar_empresa_por_id)
(`habilita_nfse` ⟂ `habilita_nfsen_producao`; `habilita_nfsen_homologacao`;
`arquivo_certificado_base64` + `senha_certificado` + `certificado_especifico`;
response `id`, `token_producao`, `token_homologacao`); NF-e
[emitir](https://doc.focusnfe.com.br/reference/emitir_nfe) ·
[consultar](https://doc.focusnfe.com.br/reference/consultar_nfe) ·
[cancelar](https://doc.focusnfe.com.br/reference/cancelar_nfe) (201 sync / 202
async, `ref` query param, item schema, 422 codes `already_processed` /
`pending_operation` / `permissao_negada`); municipal NFS-e
[emitir](https://doc.focusnfe.com.br/reference/emitir_nfse) ·
[consultar](https://doc.focusnfe.com.br/reference/consultar_nfse) ·
[cancelar](https://doc.focusnfe.com.br/reference/cancelar_nfse) (prestador /
tomador / servico incl. RT `codigo_nbs`, `ibs_cbs_*`); NFS-e Nacional
[emitir](https://doc.focusnfe.com.br/reference/emitir_dps_nacional) ·
[consultar](https://doc.focusnfe.com.br/reference/consultar_nfse_nacional) ·
[cancelar](https://doc.focusnfe.com.br/reference/cancelar_nfse_nacional)
(`/v2/nfsen`); statuses `processando_autorizacao` / `autorizado` / `cancelado` /
`erro_autorizacao` (+ cancel `erro_cancelamento`); webhooks
([webhooks](https://doc.focusnfe.com.br/reference/webhooks) ·
[criar](https://doc.focusnfe.com.br/reference/criar_webhook)) — POST JSON, one
document per call, retries 1 min → 24 h (max 48 h), `authorization` +
`authorization_header` fields.

Unverified — marked `UNVERIFIED:` in `focus.py`, to be checked by the opt-in
live test (`FOCUSNFE_TOKEN`) before P6: `denegado` NF-e status · NF-e item
tax-situation defaults (`102`/`07`/`07`, Simples) · NFS-e Nacional fields absent
from the public field list (`razao_social_tomador`, `email_tomador`, the
`codigo_opcao_simples_nacional` / `tributacao_iss` value codes, IBS/CBS key
names on `/nfsen`) · `codigo_cancelamento` on `/nfsen` cancel · `/v2/empresas/{id}`
with a CNPJ · whether `caminho_*` downloads need auth · `regime_tributario` on the
company GET · exact webhook body (assumed = the consult response) and event type
(not in the body: `kind` is inferred, `chave_nfe` ⇒ NF-e, `cnpj_prestador` ⇒ NFS-e).

## Contract clarifications (additive)

- `get`/`cancel` take optional `company_ref` (selects the per-company token);
  `CompanyRequest.company_ref` (PUT vs POST — Focus has no documented
  lookup-by-CNPJ); `InvoiceProviderError.reasons` (provider refusal reasons, e.g.
  cancel window); `InvoiceEvent.kind` is `None` when the body cannot tell.
- NFS-e lookups probe `/v2/nfsen` then `/v2/nfse`: a store can cut over
  municipal → nacional AFTER issuing, so the current mode cannot pick the channel.
- Multi-item NFS-e collapse into one `servico` (first item's codes, joined
  `discriminacao`); NF-e keeps one line per item.

## Webhook

Header `X-Invoice-Webhook-Token` (the value the host registers as the gatilho's
`authorization_header`), constant-time, fail-closed on an unset token. The body
is a hint: the handler re-reads `get(kind, ref)`.

## Tests

`seed/lib/backend/tests/integrations/invoices/` — Fake round-trip, Focus on
`httpx.MockTransport`, production-guard matrix, webhook auth, credential store,
generated-certificate inspector, and a secrets test (caplog + exception
message/args/cause chain) across timeout / network / 5xx / 4xx / garbage paths.
