"""Org-level platform domain helpers — how a person becomes a member of an org.

`ensure_personal_org` — idempotent personal-org bootstrap. Returns the user's
`org_id`, creating a new "personal" org and provisioning/attaching the
`public.noctus_users` row if needed. Used by products (PF first; therapy when
solo-mode formalizes) at first-product-login to ensure every authenticated
user lands in a usable org context.

`provision_invited_identity` + `attach_user_to_org` — the two halves of
accepting an invitation. The first gets an `auth.users` identity for an
invitee's email (creating it, or returning the existing one); the second makes
that identity a member of the inviting org. They are separate because the
authenticated-accept path already HAS an identity and only needs the second.

**Mechanics (multi-org).** Membership is `public.org_memberships` (one row per person per
org, `status` active/suspended/removed/invited); `public.noctus_users.org_id` is only the
person's LAST-ACTIVE org (it follows the org picker), and core's 079 trigger mirrors every
profile org into an ACTIVE membership. Attaching a person who has NO profile creates it in the
inviting org; attaching one who HAS a profile adds a membership and leaves the profile where it
is (`noctusai_lib.domain.org_memberships.join_org`) -- the new org is reached through the picker.

**Why the noctus_users row is load-bearing, not bookkeeping.** Core's
`/api/sso/launch/{slug}` reads `noctus_users` (`org_id, role, org_role`) to
mint the SSO token, and 404s "Perfil não encontrado" without it. A user with an
auth identity but no profile row therefore cannot open ANY product — which is
exactly the state the seed team router's accept endpoint used to leave invitees
in. → `KB § PATTERNS/backend/invitation-acceptance.md`
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from fastapi import HTTPException

from noctusai_lib.domain.org_memberships import MembershipSuspended, join_org

logger = logging.getLogger(__name__)

DEFAULT_NAME_TEMPLATE = "Pessoal — {email}"


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "pessoal"


async def ensure_personal_org(
    db: Any,
    user_id: str,
    *,
    email: str,
    nome: Optional[str] = None,
    name_template: str = DEFAULT_NAME_TEMPLATE,
    is_personal: bool = True,
    owner_role: str = "owner",
) -> str:
    """Return the user's org_id; create a personal org if they don't have one.

    Idempotent: if `noctus_users.org_id` is already set for `user_id`, returns
    it unchanged. Otherwise:
      1. INSERT `public.organizations` (`is_personal=is_personal`, owner=user_id).
      2. INSERT or UPDATE `public.noctus_users` so its `org_id` points at the
         new org and `org_role` is `owner_role`.

    Race window: two concurrent first-logins for the same `user_id` could both
    pass the SELECT and create two orgs. Acceptable today (single-user sessions
    don't race themselves); promote to a Postgres function with advisory-lock
    semantics if the race is observed.

    Args:
        db: Supabase client.
        user_id: `auth.users.id` (uuid string).
        email: user's email; substituted into `name_template` and stored on
            `noctus_users.email` if the row is being created.
        nome: display name for `noctus_users.nome`. Defaults to email's local
            part (`alice@example.com` → `alice`).
        name_template: format string for `organizations.nome`. Substitutes
            `{email}`. Default: ``"Pessoal — {email}"``.
        is_personal: value for `public.organizations.is_personal`. Default
            `True` (this helper is the personal-org bootstrap path).
        owner_role: value for `noctus_users.org_role`. Default `"owner"`.

    Returns:
        The user's `org_id` (uuid string).
    """
    existing = (
        db.table("noctus_users").select("id, email, org_id").eq("id", user_id).execute()
    )
    rows = existing.data or []
    if rows and rows[0].get("org_id"):
        org_id = rows[0]["org_id"]
        logger.debug("ensure_personal_org: user_id=%s already attached to org_id=%s", user_id, org_id)
        return org_id

    org_name = name_template.format(email=email)
    org_payload = {
        "nome": org_name,
        "slug": f"{_slugify(org_name)}-{user_id[:8]}",
        "owner_id": user_id,
        "category": "normal",
        "is_personal": is_personal,
    }
    org_resp = db.table("organizations").insert(org_payload).execute()
    if not org_resp.data:
        raise RuntimeError("ensure_personal_org: organizations insert returned empty data")
    new_org_id = org_resp.data[0]["id"]

    user_nome = nome or email.split("@", 1)[0]
    if rows:
        db.table("noctus_users").update(
            {"org_id": new_org_id, "org_role": owner_role}
        ).eq("id", user_id).execute()
    else:
        db.table("noctus_users").insert(
            {
                "id": user_id,
                "email": email,
                "nome": user_nome,
                "org_id": new_org_id,
                "role": "user",
                "org_role": owner_role,
            }
        ).execute()

    logger.info(
        "ensure_personal_org: provisioned org_id=%s for user_id=%s (email=%s)",
        new_org_id,
        user_id,
        email,
    )
    return new_org_id


# ---------------------------------------------------------------------------
# Invitation acceptance — identity, then membership
# ---------------------------------------------------------------------------


def find_auth_user_id_by_email(db: Any, email: str) -> Optional[str]:
    """Return the `auth.users.id` for `email`, or None.

    Checked BEFORE attempting to create, because "this email already has an
    identity" is a normal case, not an error: someone can sign up on core (or
    be a member of another product) long before they are invited here.

    Two lookups, cheapest first:

    1. `public.noctus_users` by email — one indexed row read, and it is our own
       record of the identity. Covers everyone who has ever completed a signup.
    2. `auth.admin.list_users()` — the authoritative fallback for an identity
       that exists in `auth.users` with no profile row yet (a core signup that
       never joined an org). Paged scan, so it runs only when (1) misses.

    Returns None when neither finds the email, which is the create path.
    """
    try:
        existing = (
            db.table("noctus_users").select("id").eq("email", email).limit(1).execute()
        )
        rows = existing.data or []
        if rows and rows[0].get("id"):
            return str(rows[0]["id"])
    except Exception as exc:  # pragma: no cover — defensive; falls through to (2)
        logger.debug("find_auth_user_id_by_email: profile lookup failed (%s)", exc)

    try:
        listed = db.auth.admin.list_users()
    except Exception as exc:
        logger.warning("find_auth_user_id_by_email: list_users failed (%s)", exc)
        return None

    # supabase-py has returned either a bare list or an object with `.users`
    # across versions; accept both rather than pinning to one shape.
    users = getattr(listed, "users", listed) or []
    target = email.strip().lower()
    for u in users:
        u_email = getattr(u, "email", None)
        if u_email and str(u_email).strip().lower() == target:
            return str(getattr(u, "id", "")) or None
    return None


def provision_invited_identity(
    db: Any,
    *,
    email: str,
    password: str,
    nome: str,
    user_metadata: Optional[dict] = None,
) -> tuple[str, bool]:
    """Return `(user_id, created)` for an invitee's email.

    If the email already has an `auth.users` identity, returns it with
    `created=False` and **does not touch the password** — an invitation link is
    not proof of control over an existing account, so letting it set a password
    would turn "invite someone" into "take over their login". They accept with
    the credentials they already have.

    Otherwise creates the identity with `email_confirm=True` — the invite email
    already proved the address receives mail, and a second confirmation round
    trip would strand the user mid-flow with no way back.

    Raises HTTPException(500) if creation reports no user.
    """
    existing_id = find_auth_user_id_by_email(db, email)
    if existing_id:
        logger.info(
            "provision_invited_identity: email=%s already has identity %s — linking",
            email, existing_id,
        )
        return existing_id, False

    metadata = {"nome": nome, **(user_metadata or {})}
    try:
        response = db.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": metadata,
        })
    except Exception as exc:
        # A create that races another accept (or an identity the lookup could
        # not see) lands here. Re-check before failing: if the identity now
        # exists, the caller's intent is satisfied.
        logger.warning("provision_invited_identity: create_user failed for %s (%s)", email, exc)
        raced_id = find_auth_user_id_by_email(db, email)
        if raced_id:
            return raced_id, False
        raise HTTPException(status_code=500, detail="Erro ao criar usuario") from exc

    new_user = getattr(response, "user", None)
    if not new_user or not getattr(new_user, "id", None):
        raise HTTPException(status_code=500, detail="Erro ao criar usuario")

    user_id = str(new_user.id)
    logger.info("provision_invited_identity: created identity %s for %s", user_id, email)
    return user_id, True


def attach_user_to_org(
    db: Any,
    user_id: str,
    *,
    org_id: str,
    email: str,
    nome: Optional[str] = None,
    org_role: str = "member",
    platform_role: str = "user",
    invited_by: Optional[str] = None,
) -> dict:
    """Make `user_id` an ACTIVE member of `org_id`. Idempotent.

    - **No profile, or a profile with no org** -- the profile is created/updated IN `org_id`
      with `org_role` (core's 079 trigger mirrors it into an ACTIVE membership).
      `"joined": True`, `"new_profile"` says which.
    - **A profile elsewhere or here** -- membership only (`org_memberships.join_org`); the
      profile is not moved (multi-org: belonging to another org is no reason to refuse).
      Already ACTIVE here returns that membership untouched (`"joined": False`, its OWN role --
      the caller decides what a different invited role means); re-activates a `removed` one.
    - **Suspended here** -- HTTPException(403): an org decision an invitation must not lift.

    Args:
        db: Supabase client bound to `public` (the CORE client -- `noctus_users` and
            `org_memberships` are platform tables, not product ones).
        user_id: `auth.users.id`.
        org_id: the inviting organization.
        email / nome: written when the profile is created. `nome` defaults to the
            email's local part; the column is NOT NULL.
        org_role: the role in `org_id` (the invite's role).
        platform_role: `noctus_users.role` of a NEW profile. Stays `"user"`: an org-level
            invite never confers platform admin.
        invited_by: the inviter's user id, recorded on a membership this call creates.

    Returns:
        The profile fields (when known) overlaid with the membership in `org_id`:
        `{..., "org_id", "org_role", "joined", "new_profile", "profile_org_id"}` --
        `profile_org_id` is where the profile (last-active org) points after the call.
    """
    existing = (
        db.table("noctus_users")
        .select("id, email, nome, org_id, org_role")
        .eq("id", user_id)
        .execute()
    )
    rows = existing.data or []

    if rows and rows[0].get("org_id"):
        try:
            membership = join_org(db, user_id, org_id, org_role, invited_by=invited_by)
        except MembershipSuspended as exc:
            raise HTTPException(
                status_code=403,
                detail="Sua participação nesta organização está suspensa",
            ) from exc
        return {
            **rows[0],
            "org_id": str(org_id),
            "org_role": membership.get("org_role"),
            "joined": membership.get("joined", False),
            "new_profile": False,
            "profile_org_id": str(rows[0]["org_id"]),
        }

    payload = {
        "org_id": str(org_id),
        "org_role": org_role,
    }
    if rows:
        db.table("noctus_users").update(payload).eq("id", user_id).execute()
        logger.info(
            "attach_user_to_org: placed org-less profile user_id=%s in org_id=%s (%s)",
            user_id, org_id, org_role,
        )
        return {**rows[0], **payload, "joined": True, "new_profile": False, "profile_org_id": str(org_id)}

    row = {
        "id": str(user_id),
        "email": email,
        "nome": nome or email.split("@", 1)[0],
        "role": platform_role,
        **payload,
    }
    db.table("noctus_users").insert(row).execute()
    if invited_by:
        # The 079 trigger created the ACTIVE membership; record who invited (core's accept does
        # the same for its own invitations).
        (
            db.table("org_memberships").update({"invited_by": str(invited_by)})
            .eq("org_id", str(org_id)).eq("user_id", str(user_id)).eq("status", "active")
            .execute()
        )
    logger.info(
        "attach_user_to_org: created profile user_id=%s in org_id=%s (%s)",
        user_id, org_id, org_role,
    )
    return {**row, "joined": True, "new_profile": True, "profile_org_id": str(org_id)}


def sync_org_metadata(
    db: Any,
    user_id: str,
    *,
    org_id: str,
    org_role: str,
    nome: Optional[str] = None,
) -> bool:
    """Mirror the membership into `user_metadata`. Returns True on success.

    Required for the member to actually work: the seed's `get_org_id(user)`
    reads `user_metadata["org_id"]` and 403s without it, and the frontend's
    `resolveSSOContext` reads `user_metadata.org_role` to gate admin UI. Core's
    SSO bridge re-syncs both on every product launch, so this write is what
    covers the window BEFORE the first launch.

    Best-effort by design: the membership row is the source of truth and core
    will re-sync from it, so a metadata write failure must not fail an accept
    that has already succeeded. Logged at warning rather than swallowed.
    """
    metadata = {"org_id": str(org_id), "org_role": org_role}
    if nome:
        metadata["nome"] = nome
    try:
        db.auth.admin.update_user_by_id(user_id, {"user_metadata": metadata})
        return True
    except Exception as exc:
        logger.warning(
            "sync_org_metadata: could not mirror org context onto user_id=%s (%s); "
            "core's SSO bridge will re-sync from noctus_users at next launch",
            user_id, exc,
        )
        return False
