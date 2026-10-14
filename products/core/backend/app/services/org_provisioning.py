"""Creating an organization owned by a user -- the ONE implementation (signup, OAuth signup,
and the personal org a removed member keeps their profile in).

Slug rule (core 039): ``indv_<base>`` for an individual org, ``comp_<base>`` for a company; a
taken slug gets ``-<6 hex>`` appended. Every org-creating path goes through
:func:`create_owned_org`, so the rule cannot drift between them (it had been copied into
``auth.py`` and ``oauth.py``).

Personal org (owner decision D4, 2026-10-14): removing a user whose ONLY active membership is the
org they are removed from keeps their profile -- its audit history is append-only -- in a personal
org of their own (individual, ``is_personal``). :func:`create_personal_org` makes it through the
same path; the move itself happens inside the ``team_member_remove`` transaction, which validates
the org (owned by the user, ``is_personal``, no members yet).

KB § PATTERNS/backend/tenancy-license-gate.md § Members
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_SLUG_PREFIX = {"individual": "indv", "company": "comp"}

#: Name of a removed member's personal org (D4).
PERSONAL_ORG_NAME = "Pessoal — {nome}"


def slugify(text: str) -> str:
    """URL-safe slug (max 44 chars, leaving room for ``prefix_``)."""
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:44]


def make_org_slug(base_name: str, org_type: str = "individual") -> str:
    """``indv_<base>`` / ``comp_<base>`` (an unknown type is an individual)."""
    prefix = _SLUG_PREFIX.get(org_type, "indv")
    return f"{prefix}_{slugify(base_name)}"


def available_org_slug(db: Any, base_name: str, org_type: str = "individual") -> str:
    """:func:`make_org_slug`, suffixed ``-<6 hex>`` when the slug is already taken."""
    slug = make_org_slug(base_name, org_type)
    existing = db.table("organizations").select("id").eq("slug", slug).execute()
    if existing.data:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"
    return slug


def create_owned_org(
    db: Any, *, owner_id: str, nome: str, slug_base: str, org_type: str = "individual", **fields: Any
) -> dict:
    """INSERT an organization owned by ``owner_id`` (free plan) and return the row.

    ``fields`` are the caller's extra columns (``category``, ``number_of_users``, onboarding
    state, ``is_personal``...). 500 when the insert returns nothing -- never a half-made org."""
    payload = {
        "nome": nome,
        "slug": available_org_slug(db, slug_base, org_type),
        "plano": "free",
        "owner_id": owner_id,
        "org_type": org_type,
        **fields,
    }
    result = db.table("organizations").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar organização")
    return result.data[0]


def create_personal_org(db: Any, *, owner_id: str, nome: str) -> dict:
    """The personal org a removed sole-org member keeps their profile in (D4)."""
    return create_owned_org(
        db, owner_id=owner_id, nome=PERSONAL_ORG_NAME.format(nome=nome), slug_base=nome,
        org_type="individual", category="normal", number_of_users=1, is_personal=True,
    )


def discard_unused_org(db: Any, org_id: str) -> None:
    """Delete an org created for a removal that did not use it (the removal failed, or another
    membership took the profile). It is brand new and empty. A failure is logged loudly with the
    id -- an orphan empty org is recoverable, a silent one is not."""
    try:
        db.table("organizations").delete().eq("id", org_id).execute()
    except Exception:
        logger.critical("org_provisioning: could not discard unused personal org %s -- delete it by hand",
                        org_id, exc_info=True)
