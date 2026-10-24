# Silent refusal — a failure is never "nothing found", an upload refusal is always on screen

> **Rule.** When the server (or the client) says no, the screen says so — with the reason, and for an upload with the file's name — until the next attempt. Two shapes are forbidden:
>
> 1. **Empty over error.** A query's empty branch ("Nenhum … encontrado", "Cadastrar novo", `isEmpty=`) must not be reachable while the query is in error. Decide the error first: `q.isError && !q.data ? <QueryErrorState query={q} /> : rows.length === 0 ? <Empty/> : …`, or put `!q.isError` in the empty predicate.
> 2. **An upload nobody watches.** Every upload goes through the seed organ, whose contract is that the caller renders the refusal:
>
> ```tsx
> import { UploadErro } from "@noctusai/lib/components";
> import { useUploadDocumento } from "@noctusai/lib/upload-refusal";
>
> // props.onUpload: (file: File, tipo: string) => Promise<unknown>   ← the container returns mutateAsync
> const envio = useUploadDocumento((file: File, tipo: string) => onUpload(file, tipo), {
>   aceitos: ["application/pdf"],            // optional client-side type check (F75b-safe)
> });
> <input type="file" onChange={(e) => { const f = e.target.files?.[0]; if (f) void envio.enviar(f, tipo); }} />
> <UploadErro erro={envio.erro} onDismiss={envio.limpar} />
> ```
>
> Keeper `check_silent_refusal` (`--check-silent-refusal`, high, pre-commit blocking, AST via ts-morph) is the backstop for both.

## Why — four instances in one replay

On 2026-10-24 a single social-wiring replay hit the same class four times:

| | what the user saw | what happened |
|---|---|---|
| F76 | "Nenhum imóvel encontrado" + "Cadastrar … como imóvel novo" | the search returned 502/401 mid-deploy; the picker read `busca.data?.items ?? []` and fell through to empty + create — an invitation to register a duplicate of an existing property |
| F78 | nothing | a 400 on an anexo upload (a reserved `tipo_documento`) |
| F86 | nothing | a 422 on a certidão cell upload; 10 uploads were lost before anyone noticed |
| F75b | nothing | a client-side type check refused a valid WhatsApp/Drive file (no extension ⇒ `application/octet-stream`) |

Each was fixed where it was found (`0ff32d488`, `80119858e`, `5bc0c43a4`, `7b76a3ed8`). The class stayed: at N=4 the recurrence rule says formalize. The construction side and the keeper landed together (gate↔methodology sync).

## Why the old shapes lose the refusal

- **`?? []` turns "unknown" into "empty".** `const rows = q.data?.items ?? []` is the same value for "the server said there are none" and "the request failed". Any branch keyed on `rows.length === 0` cannot tell them apart. (`q.data?.length === 0` is *false* on error — `undefined === 0` — so the undefaulted form is safe; `!q.data?.length` is *true* on error, so it is not.)
- **`onUpload: (file) => void` is where a rejection goes to die.** The container calls `mutation.mutate(...)`; the hook's `onError` (if any) fires a toast that vanishes; the slot that the user is looking at never learns the upload failed. The promise was the only channel back, and the `void` signature threw it away.

## The construction (what makes the right shape the easy one)

- **`useUploadDocumento(enviarFn, options)`** (`seed/lib/frontend/src/upload-refusal.ts`):
  - `enviarFn` is typed `(file, ...args) => Promise<unknown>`. A fire-and-forget callback does not compile.
  - `enviar(file, ...args)` never rejects. It resolves `{ ok: true, valor } | { ok: false, recusa }`, and a refusal becomes `erro` until the next attempt or `limpar()`.
  - A failed `useRetryableAction().run` outcome (`run` never rejects) counts as a refusal.
  - `enviarEm(chave, …)` tags the refusal for per-row rendering (certidão cells, checklist rows).
  - `recusar(file, msg)` records a caller-side refusal (no tipo picked).
  - `options.aceitos` checks the type through `tipoArquivoAceito`: `""` and `application/octet-stream` always go to the server sniff (F75b). `options.maxBytes` adds a size ceiling.
- **The message** (`motivoDaRecusa`):
  - a 4xx shows the **server's own words**, because they say what is wrong with *this file*: size, type, a reserved tipo. The body's `error.message` / `detail` is used and the `[NNN] ` prefix is stripped.
  - a 5xx or transport failure shows `describeFailure`'s reason class, never the raw text. Same rule as `RetryableError`.
- **`<UploadErro erro chave? onDismiss?>`** (`@noctusai/lib/components`) renders `"x.pdf" não foi enviado: <motivo>` as `role="alert"`, and renders nothing otherwise, so it is always safe to mount.
- **The slot contract.** Every seed and social-wiring upload slot types its upload prop as `Promise<unknown>`:
  - seed: `AnexosSection.onUpload`, `ChecklistExtrasSection.onUploadDocumento`;
  - social-wiring: `DocumentoTipoSlot` and `CertidaoCasamentoSlot.onUpload`, `IdentidadeChecklistRow` / `DocumentoChecklistSection.onUploadDocumento`, `ImovelDocumentosCard` and `ImovelCertidoesCard.onUpload`, `FinanciamentoPanel`, `ClienteCardDialog`.

  Because of the type, `tsc` lists every container still passing `mutate` — that is how the migration was driven.
- **For a failed query** the seed already ships `QueryErrorState` / `RetryableError` (`KB § PATTERNS/frontend/lying-loading-state.md` for the two-signal skeleton). It renders only when the query is in error with no data.

## The keeper — `check_silent_refusal`

`mcp/noctusai/node/silent_refusal_scan.mjs` (ts-morph, one program per batch) is driven from `compliance.py`. It scans ACTIVE products' `frontend/src` and `seed/{lib,framework}/frontend/src`, skipping tests. There is no baseline: every live hit was fixed when the keeper landed (13 empty-over-error sites in social-wiring, agents and the seed; 6 upload sites in social-wiring; the first draft's other 15 hits were precision bugs in the scan — skeleton gates, an `if/else` error test, a sibling `error=` prop — fixed in the scan and pinned by tests).

| rule | flags | not flagged |
|---|---|---|
| `empty_over_error` | an empty predicate over a query's data reaching a render gate: `?:` test, `&& <JSX>`, `if (…) return <JSX>`, or `empty=`/`isEmpty=`. The predicate is `E.length === 0` on a DEFAULTED `E` (`?? []`, `\|\| []`, destructuring default), or `!E.length`. Data aliases are followed up to 3 hops, boolean aliases 1 hop, by symbol | an `&&` sibling, an enclosing `?:`/`&&`/`if` test, or an earlier `if (…) return` that references the query's error (`isError`/`error`/`status`/`isSuccess`, destructured or aliased) or its data's truthiness; a sibling `error=` attribute on the same element; a two-signal SKELETON gate (`q.isPending && rows.length === 0 ? <Skeleton/>`); `useSuspenseQuery` (errors go to the boundary) |
| `upload_mutate_unhandled` | `X.mutate/mutateAsync(<carries a file>)` in a component | `onError` in the call, `X.error`/`X.isError` read in the file, `mutateAsync` returned / `.catch`ed / awaited in a non-empty `try` |
| `upload_void_callback` | `onUpload…={(…) => X.mutate(…)}` | `mutateAsync`, or `mutate(…, { onError })` |
| `upload_raw_unhandled` | `api.upload(…)` / `uploadMultipart(…)` in a component with no catch | inside a `mutationFn`, or inside the `useUploadDocumento` send fn |
| `upload_organ_erro_unread` | `useUploadDocumento(…)` whose `erro` is never read in the file | — |

**Out of scope, stated honestly.** The scan is single-file:
- a list handed to a child component through props;
- a hook-level `onError` toast seen from the component that calls `mutate` (that site is flagged; return the promise instead);
- a `.length` read through a second function call.

**Escape** (per finding, with a reason, on the line or up to 3 lines above): `// noc-allow: silent-refusal — <why>`.

## Anti-patterns

- Hiding the error with `?? []` and adding a toast "so the user knows". The toast vanishes; the "Nenhum" stays.
- `onUpload={(file) => upload.mutate({ file })}`. Return `upload.mutateAsync({ file })`.
- Rendering the server's raw 5xx body as the reason. Show the class; only a 4xx explains the file.
- A per-slot `useState<string | null>` error built by hand. That is the fork the organ replaces (AnexosSection had one; it now uses the organ).

## Composes with

- `KB § PATTERNS/frontend/lying-loading-state.md` — the read side's other lie: skeleton/empty over data that exists.
- `KB § PATTERNS/frontend/mutation-cache-writes.md` — hooks keep `useCacheWriteMutation`; the organ wraps their `mutateAsync`.
- `KB § PATTERNS/common/server-state-family-index.md` — the §1 family this rule belongs to.
- `KB § 01-PHILOSOPHY.md` — no silent errors.
