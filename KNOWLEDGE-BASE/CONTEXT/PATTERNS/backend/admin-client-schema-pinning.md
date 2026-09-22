# Admin client schema pinning — `.schema(other)` mutates shared state, it does not scope it

> Formalized 2026-09-22 from a live prod 500: `GET /api/agents` returned
> `PGRST205: Could not find the table 'academia_de_reciclagem.
> app_integration_config' in the schema cache` — the `agents` schema's OWN
> config table, reached through a client a cross-schema token lookup had
> repointed moments earlier. The same shape was independently live in
> academia-de-reciclagem. Self-contained.

## The rule

**`supabase.Client.schema(name)` does not return an independent, scoped
client — it mutates the client's shared `postgrest` session IN PLACE
(`Accept-Profile`/`Content-Profile` headers) and returns that same object.**
Verified on supabase-py 2.9.1: `client.schema("x") is client.postgrest` →
`True`.

```python
admin = get_admin_client()          # cached ONE-per-process, built with schema="agents"

admin.schema("academia_de_reciclagem").table("api_tokens")   # deliberate cross-schema read
admin.table("app_integration_config")                        # ❌ ALSO hits academia_de_reciclagem now
```

Any caller that mints/looks up a token in ANOTHER product's schema — a real,
legitimate need (`noctusai_lib.api.auth.session.token_admin
.SupabaseProductTokenAdmin`) — permanently repoints the process's cached
admin client. The NEXT caller in the same process that does a bare
`get_admin_client().table(...)`, trusting the schema the client was
constructed with, silently hits the wrong schema. Order-dependent and
intermittent: whichever request happens to run the cross-schema call first
determines who breaks.

## Why it reads as a missing migration

Same tell as `postgrest-schema-targeting.md`'s doubled-prefix case, different
shape: the error names a table that DOES exist — just not in the schema the
error's own schema-qualified name shows. The investigation goes to
migrations and the PostgREST schema cache; both are fine. The actual bug is
in a different module entirely — whichever one last called `.schema(other)`
on the shared client.

## The fix — pin per call, not per process

`DatabaseModule.get_admin_client()` (`seed/framework/backend/noctusai_seed
/database.py`) now returns `_SchemaPinnedAdminClient`, a thin wrapper that
re-pins to the `DatabaseModule`'s own schema on **every** `.table()` /
`.rpc()` / `.from_()` call before delegating — so no caller can be poisoned
by another caller's mutation of the shared underlying client, regardless of
request interleaving. `.schema(other)` still works for a deliberate one-off
cross-schema call (passed straight through, mutating the underlying client
exactly as before) — that mutation just no longer survives past the one
call, because the next access through the wrapper re-pins first.

This closes it at the one place every product's admin client is constructed
— no per-store change needed. `_LazyAgentsTable.table()`
(`products/agents/backend/app/credentials/resolver.py`) ALSO pins
`.schema("agents")` explicitly as defense in depth at the exact call site
the outage traced to.

## Recognizing the risk in a store

Vulnerable shape: a store holds a cached/injected admin client and calls
`.table(...)`/`.rpc(...)` **bare**, trusting ambient schema state:

```python
class SomeStore:
    def __init__(self, admin_client): self._admin = admin_client
    def list(self): return self._admin.table("some_table").select("*").execute()
```

Safe shape (used throughout social-wiring): re-derive `.schema(SCHEMA)`
immediately before every use, never trust ambient state:

```python
def _table(self): return self._admin.schema(_SCHEMA).table(_TABLE)
```

Both shapes are now protected by the `DatabaseModule`-level fix when the
client came from `get_admin_client()` — but the safe shape is still the
right one to write, because it is also correct against a raw,
un-wrapped `supabase.Client` (e.g. one built directly with
`make_supabase_client()`, bypassing `DatabaseModule` entirely).

## See also

`§ CONTEXT/PATTERNS/backend/postgrest-schema-targeting.md` (the sibling bug —
qualified-name string bugs vs. ambient-state leaks; same family, different
mechanism) · `§ CONTEXT/PATTERNS/backend/database-rls.md` · `§ CONTEXT/PATTERNS/backend/seed-fake-real-adapter.md`.
