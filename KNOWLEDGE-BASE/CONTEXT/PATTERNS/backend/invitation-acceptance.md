# Invitation acceptance — a success screen is not a membership

> Formalized 2026-08-07. The seed team router's `POST /api/team/accept` flipped
> the invitation row to `accepted`, returned 200, and did nothing else — for all
> nine products mounting it. Invitees saw a success screen and could not log in
> anywhere. Self-contained.

## The rule

**Accepting an invitation is three writes, not one.** Marking the invitation
`accepted` is the *last* and least important of them:

1. **Identity** — an `auth.users` row (created, or an existing one linked).
2. **Membership** — a `public.noctus_users` row with `org_id` + `org_role`.
3. **Invitation** — `status='accepted'`, `accepted_by`, `accepted_at`.

Do only (3) and every gate downstream still says "no such user." The endpoint
returns 200 the whole time, which is why this survived three months.

## Why the membership row is load-bearing

`public.noctus_users` is not a profile nicety — it is the platform's membership
table. There is **no `org_members` join table**: membership *is*
`noctus_users.org_id NOT NULL + org_role`, a single-org-per-user FK.

Core's `GET /api/sso/launch/{product_slug}` reads it directly:

```python
profile = db.table("noctus_users").select("org_id, role, org_role").eq("id", user.id).single().execute()
if not profile.data:
    raise HTTPException(status_code=404, detail="Perfil não encontrado")
```

An identity with no profile row therefore cannot open **any** product — the SSO
token is never minted. That is the exact state a status-only accept leaves
people in: a real account, a real password, and a 404 at every door.

## The three places org context has to land

| Surface | Reads | Consequence if absent |
|---|---|---|
| Core SSO launch | `noctus_users.org_id / role / org_role` | 404 "Perfil não encontrado" — no product opens |
| Product backend | `user_metadata["org_id"]` (`deps.get_org_id`) | 403 "Usuario sem organizacao associada" |
| Product frontend | `user_metadata.org_role` (`resolveSSOContext`) | admin UI hidden from an admin |

`noctus_users` is the source of truth; `user_metadata` is a **mirror** that core's
SSO bridge re-syncs on every launch. Write both at accept time anyway — the
mirror is what covers the window *before* the first launch, and without it a
freshly-accepted member 403s against the very product that invited them.

## Decisions that are not obvious

**Existing identity: link it, never reset its password.** An invitation link is
not proof of control over an existing account. If accepting one could set that
account's password, "invite someone" becomes "take over their login" — send an
invite to a known address, click your own link, choose a password, and you are
in. Look the identity up *before* creating (`find_auth_user_id_by_email`), and
if it exists, join it to the org using the credentials it already has.

**Already in a different org: 409, don't move them.** Membership is a single-org
FK, so "joining" a second org overwrites the first. That silently evicts the
user from their current org and every product licensed to it. Refusing is the
only non-destructive answer; transferring an account is a deliberate admin
action, not a side effect of clicking a link.

**The invited email wins over the request body.** Take the address from the
invitation row, never from the payload. Otherwise a leaked token enrolls an
attacker's address instead of the one that was actually invited.

**`email_confirm: True` on create.** The invitation email already proved the
address receives mail. A second confirmation round-trip strands the user
mid-flow with no way back.

**`role` stays `"user"`.** `org_role` is authority inside one org; `role` is
platform-wide. An org admin inviting someone must not be able to mint a platform
admin.

**Compensating delete on partial failure.** If the identity was created *by this
call* and the membership write then fails, delete it. An identity with no
membership is unreachable **and** blocks the retry — its email is now taken, so
the next attempt reports "already registered" forever. A transient failure
becomes permanent. An identity that already existed is never deleted; it is not
ours. And leave the invitation `pending` — burning the token on a failure
strands the invite too.

## Why unit tests did not catch the empty implementation

Nothing asserted on the *effects*. The suite checked that `/accept` returned 200
and that the invitation row flipped — both true of the empty version. No test
asked "is there now a member?"

The generalizable form: **for an endpoint whose job is a side effect, asserting
the status code tests almost nothing.** Assert the writes — the profile row, the
metadata mirror, the identity call — because those are the deliverable.

## Prerequisite: the table has to exist

`standard_routers=[…, "team", …]` in a product's `main.py` mounts endpoints that
read `<schema>.invitations`. Three products mounted the router with no such
table (adconnect, dev-team, knowledge-extractor); erp had the table but not
`accepted_at`/`accepted_by`. Both classes were masked by the schema-qualified
table bug (`§ CONTEXT/PATTERNS/backend/postgrest-schema-targeting.md`), which
produced a near-identical "could not find the table" error fleet-wide.

**Mounting a standard router is a schema commitment.** When adding one, verify
the tables it addresses exist in that product's schema — the canonical shape
lives in `products/seed/backend/migrations/001_seed.sql` (+ `002` for the
accepted columns) and must be copied byte-identically, because the router is
shared code reading those exact columns for every mounting product.

## Where this lives

- `noctusai_lib.domain.org` — `provision_invited_identity` · `attach_user_to_org`
  · `sync_org_metadata` · `find_auth_user_id_by_email`
- `noctusai_lib.domain.invitations` — token lifecycle (BARE table names only:
  `§ CONTEXT/PATTERNS/backend/postgrest-schema-targeting.md`)
- `noctusai_seed.routers::_create_team_router` — the composing endpoint
- Tests: `seed/lib/backend/tests/domain/test_org_membership.py` ·
  `seed/framework/backend/tests/routers/test_team_router_accept.py`

`products/core` and `products/therapy-platform` have their own invitation
routers predating the seed's. Core's `aceitar_convite` was the reference for the
authenticated branch; therapy's `accept_invitation_endpoint` for identity
creation. Both remain product-owned — folding them into the seed is a separate
consolidation, and both are noted in the N=5 `auth.admin.create_user` recurrence.

## See also

`§ CONTEXT/PATTERNS/backend/postgrest-schema-targeting.md` (the bug that masked
the missing tables) · `§ CONTEXT/PATTERNS/backend/database-rls.md` ·
`§ CONTEXT/PATTERNS/backend/boundary-contract-tests.md` (each side tested, the
contract between them untested) · `§ CONTEXT/PATTERNS/compliance/testing.md`.
