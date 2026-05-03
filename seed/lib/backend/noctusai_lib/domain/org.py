"""Org-level platform domain helpers.

`ensure_personal_org` — idempotent personal-org bootstrap. Returns the user's
`org_id`, creating a new "personal" org and provisioning/attaching the
`public.noctus_users` row if needed. Used by products (PF first; therapy when
solo-mode formalizes) at first-product-login to ensure every authenticated
user lands in a usable org context.

**Audit-corrected mechanics.** There is no `public.org_members` join table on
this platform. Membership is `public.noctus_users.org_id NOT NULL + org_role`
(single-org-per-user FK), and `public.current_org_id()` reads the JWT claim,
not a join. Attaching a user to a new org therefore means inserting (or
updating) the noctus_users row — no join-table write.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

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
