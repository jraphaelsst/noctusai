# Data in the wrong field: move it, never ask for it again

> Formalized 2026-10-15 from deal 876 (social-wiring). Self-contained.

## The class

**Information the user already typed into the system sits in the wrong field.
Downstream code needs it in the right field and blocks. The bug is to send
the person back to "fill in" what they already gave us.**

Real instance: a payee's `banco` held `"<bank> (341) Ag. <agência> CC <conta>"`,
with `agencia`/`conta` NULL. Card rows were typed that way, and the migration-251
backfill copied them into the registry. The contract readiness check blocked
with "Dados bancários … estão no campo Banco; preencha Agência e Conta".

Over several turns an agent asked the owner to "split" the fields. The owner
heard "give me the bank details" for data that was on screen. It cost a day
of a blocked contract and an angry owner.

Two things went wrong:

1. **The code** detected the shape and then refused (registry write → 400,
   readiness → blocking item). The rationale written in `banco_texto.py` was
   "store only what the document/user states, in the right field". The user
   HAD stated it. Only the field was wrong, so refusing protected nothing.
2. **The agent** treated "relocate data the owner already entered" as if it
   were "type a bank account number". The no-typing rule exists so an agent
   never authors or invents financial identifiers. Moving a value the system
   already holds, derived by the system, is a data fix.

## The rule

- **Relocate, don't re-ask.** When a required field is empty and the value
  is already present elsewhere on the same record, the system moves it. The
  person is never asked to retype it.
- **Move only when the shape is exact.** The parser is anchored end to end
  (every character accounted for). The original must round-trip:
  `nome + " Ag. " + agência + " CC " + conta == banco`. Any other shape is
  left alone and still blocks. A partial or ambiguous match is a question,
  never a guess. This keeps the "don't invent the check digit" rule intact:
  nothing is computed, only moved.
- **Never overwrite a filled field.** Split only when the target fields are
  empty.
- **Fix it at write time, in the shared helper, on every write path.**
  `card_hub/banco_texto.com_banco_separado` runs in both
  `favorecidos_service` (registry) and `negociacao_estruturada_service`
  (per-deal payee). A guard on one path and none on the other is how the
  legacy rows arrived.

## For agents: fixing existing rows in prod

1. **Count first** without printing values: select booleans and lengths
   (`agencia is null`, `banco ~* 'Ag\.?\s*\d'`, `length(...)`), never the digits.
2. **Dry-run the split in SQL** and assert the round-trip per row.
3. **Run the UPDATE in SQL**, deriving the new values from the stored column
   (`regexp_match(banco, …)`). Guard it with `agencia is null and conta is null`
   so it is idempotent. The values never pass through the agent's hands or
   the chat.
4. **Return only ids, the bank name and lengths.** Then re-check the readiness
   endpoint.
5. **Tell the owner in plain words** what was where and what moved, e.g.
   "agência and conta were inside Banco; I moved them". Never use a verb
   like "split" or "fill" that reads as "give me the data".

The `supabase_db_query` confirm gate classifies by leading keyword. A
`WITH … UPDATE` runs as read-only and fails with "cannot execute … in a
read-only transaction". Start the statement with `UPDATE`.

## Same class elsewhere

Any free-text field that absorbs structured siblings: address number inside
`logradouro`, CRECI inside `nome`, RG issuer UF missing while the RG header
names the state (`seed rg._uf_do_cabecalho`). Same rule each time: exact
shape → move; anything else → ask.
