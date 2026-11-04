# S10a notes — CONTRACT §C implementation record (SW Agente page)

Companion to `CONTRACT.md` (kept in a separate file so it merges without touching the contract's own commits). Fold into
§C when the contract lands on the integration branch. 2026-11-04.

## What shipped (frontend, `products/social-wiring/frontend/src`)

- **C1** `components/julia/WhatsAppJuliaCard.tsx` (`id="whatsapp"`): seed `ConnectionPairingPanel` inside a `ConfirmProvider`, bound by `hooks/useJuliaLinhaWhatsapp.ts` (`createWhatsAppConnectionsHooks(api)`). The line is `roteamento.linhas[0]`; "Criar linha" (seed `CreateConnectionDialog`, admin) only while there is none; link to `/julia/conversas`. No "add another connection".
- **C2** the Conversas and Roteamento empty states already point at `/julia/agente#whatsapp` (S10b).
- **C3** `AgentsLinkCard` is now "Conexão com a plataforma" (read-only). `agents_url` / `urlConfigurarJulia` / the paste-token mutation are gone; `useJuliaAgente` messages never name the agents app; the guard also scans `hooks/useJulia*` and forbids "One Chat". One Chat copy removed from the Equipe role text. `JuliaLigadaCard` no longer gates on `numeros_autorizados`.
- **Platform connection** `components/julia/ConexaoPlataforma.tsx`: status badge, masked token (no input, `select-none`), times, pt-BR help per status/motivo, "Testar conexão" -> `POST /api/julia/agente/conexao-plataforma/verificar`, answer written into the `["sw","julia","agente"]` cache. Configurações: `ApiKeyStatus.read_only` renders `ManagedReadOnlyRow` (the `agents` key = the same card; any other read-only key = masked hint, no input).
- **C4** `components/julia/EspecificacoesCard.tsx` + `hooks/useJuliaEspecificacoes.ts`: fields per `tipo` from the declarations (rotulo / descricao / exemplo), PUT sends EVERY declared key (blank clears), `aviso_privacidade_url` read-only, draft flagged "não salvas" until the server accepts, 422 `violacoes` per field (draft kept), report-mode `invalidas` per field, 409 `agente_nao_conectado` -> link to `#conexao-plataforma`, 502/503 named.

## Assumptions to confirm against S9's backend (built to the dispatch contract)

- The specs GET/PUT body is accepted both bare and inside `{data: …}`.
- A refusal's `code` / `violacoes` are read from the body root, `body.error` or `body.detail`.
- "Testar conexão" is shown to org admins only; the server enforces.
- `modo_validacao` is displayed nowhere (the UI branches on the response, not on the mode).

## Deferred (S12)

`useSetAutoReply` (`hooks/useWhatsAppChats.ts`) and `auto_reply_enabled` / `authorized_numbers` in the connection hooks/types are dead; removed with S12.
- Each spec value may carry `updated_by_nome`; the card shows "Alterado por <nome> em <data>" only when present (name to reconcile with S9).
