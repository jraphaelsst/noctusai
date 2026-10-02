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
_Ainda não gerado — rode `mode=sync` depois que a migration 186 estiver aplicada e houver observações._
<!-- END observed-behaviour -->

## 6 · Composes with

`KB § PATTERNS/common/build-learn-cache-mindset.md` (the sidecar) · `KB § PATTERNS/backend/seed-fake-real-adapter.md` ·
`KB § PATTERNS/common/remediation-markers.md`.
