"""Parties service -- CRUD, roles, search, archive, delete-when-unreferenced, LGPD masking.

* **Document.** `doc` is a CPF (PF) or CNPJ (PJ, numeric or alphanumeric) with VALID check digits,
  stored without punctuation (the seed's `cpf_dv_valido` / `cnpj_dv_valido`). Unique per org when present.
* **LGPD.** `doc` is masked (`_organ_common.mask_doc`) in every read for a non-admin; staff
  cannot probe documents by prefix either: a non-admin doc search only matches a COMPLETE document.
* **Archive, don't delete.** `is_active=false` is the normal retirement. A hard delete is refused
  (409 `parceiro_em_uso`) while any `cfg.reference_tables` row points at the party.
* **Search at scale.** Plain listing is DB-paged. The role filter lives in a second table, so that
  path intersects in memory (paged past the 1 000-row cap) -- correct totals, bounded by an org's
  party count, never an unbatched `IN (...)` URL.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from noctusai_lib.domain._organ_common import mask_doc
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows
from noctusai_lib.primitives.identificador import cnpj_dv_valido, cpf_dv_valido
from noctusai_lib.primitives.phone import normalize_phone
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, like_term, new_id, now_iso
from .errors import (
    DOCUMENTO_DUPLICADO,
    DOCUMENTO_INVALIDO,
    EMAIL_INVALIDO,
    PAPEL_INVALIDO,
    PARCEIRO_EM_USO,
    TELEFONE_INVALIDO,
    conflict,
    invalid,
)
from .schemas import ADDRESS_FIELDS, MAX_PHONES
from .types import PartyKind, PartyRole, values

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
_TEXT_FIELDS = ("legal_name", "trade_name", "state_registration", "municipal_registration", "notes")
_ROLES = "party_roles"


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def _blank(value: Any) -> Optional[str]:
    text = None if value is None else str(value).strip()
    return text or None


# ─── field normalisation ─────────────────────────────────────────────────────


def normalize_doc(kind: str, raw: Optional[str]) -> Optional[str]:
    """CPF (PF, 11 digits) or CNPJ (PJ, 14 numeric/alphanumeric) with valid check digits; `None` for blank."""
    if raw is None or not str(raw).strip():
        return None
    cleaned = "".join(ch for ch in str(raw).upper() if ch.isalnum())
    if kind == PartyKind.PF.value and len(cleaned) == 11 and cleaned.isdigit() and cpf_dv_valido(cleaned):
        return cleaned
    if kind == PartyKind.PJ.value and len(cleaned) == 14 and cnpj_dv_valido(cleaned):
        return cleaned
    label = "CPF" if kind == PartyKind.PF.value else "CNPJ"
    raise invalid("doc", f"{label} inválido para uma pessoa {'física' if label == 'CPF' else 'jurídica'}.", code=DOCUMENTO_INVALIDO)


def normalize_email(raw: Optional[str]) -> Optional[str]:
    email = _blank(raw)
    if email is None:
        return None
    email = email.lower()
    if not _EMAIL.match(email):
        raise invalid("email", "E-mail inválido.", code=EMAIL_INVALIDO)
    return email


def normalize_phones(raw: Optional[list]) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        if _blank(item) is None:
            continue
        phone = normalize_phone(str(item))
        if phone is None:
            raise invalid("phones", f"Telefone inválido: {item}.", code=TELEFONE_INVALIDO)
        if phone not in out:
            out.append(phone)
    if len(out) > MAX_PHONES:
        raise invalid("phones", f"No máximo {MAX_PHONES} telefones.", code=TELEFONE_INVALIDO)
    return out


def normalize_address(raw: Any) -> dict:
    if not raw:
        return {}
    data = raw if isinstance(raw, Mapping) else dict(raw)
    out = {k: _blank(data.get(k)) for k in ADDRESS_FIELDS}
    if out.get("state"):
        out["state"] = out["state"].upper()
    return {k: v for k, v in out.items() if v is not None}


def normalize_roles(raw: Any) -> list[str]:
    roles = sorted({str(_plain(r)) for r in (raw or [])})
    bad = [r for r in roles if r not in values(PartyRole)]
    if bad:
        raise invalid("roles", f"Papel inválido: {bad[0]}.", code=PAPEL_INVALIDO)
    return roles


# ─── LGPD presentation ───────────────────────────────────────────────────────


def present_party(row: dict, *, is_admin: bool, roles: Optional[list[str]] = None) -> dict:
    """The wire shape of a party: `doc` masked for non-admins, `roles` attached."""
    out = dict(row)
    if not is_admin:
        out["doc"] = mask_doc(out.get("doc"))
    if roles is not None:
        out["roles"] = roles
    return out


def _roles_by_party(s: Scope, party_ids: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {pid: [] for pid in party_ids}
    for row in in_batched_rows(s.db, s.cfg.table(_ROLES), s.org_id, "party_id", party_ids):
        grouped.setdefault(str(row["party_id"]), []).append(row["role"])
    return {pid: sorted(rs) for pid, rs in grouped.items()}


def with_roles(s: Scope, rows: list[dict]) -> list[dict]:
    """Attach `roles` (sorted) to every row."""
    by_party = _roles_by_party(s, [str(r["id"]) for r in rows])
    return [{**r, "roles": by_party.get(str(r["id"]), [])} for r in rows]


# ─── read ────────────────────────────────────────────────────────────────────


def get_party(s: Scope, party_id: Any) -> dict:
    """The raw (unmasked) party + its roles; callers present it."""
    return with_roles(s, [s.get("parties", party_id, what="Cadastro")])[0]


def find_by_doc(s: Scope, doc: str) -> Optional[dict]:
    resp = s.tbl("parties").select("*").eq("org_id", s.org_id).eq("doc", doc).limit(1).execute()
    return first(resp)


def _search_refine(q: Optional[str], kind: Optional[str], active: Optional[bool], is_admin: bool):
    term = like_term(q) if q and q.strip() else None
    alnum = "".join(ch for ch in (q or "").upper() if ch.isalnum())

    def refine(query):
        if kind:
            query = query.eq("kind", kind)
        if active is not None:
            query = query.eq("is_active", active)
        if term:
            clauses = [f'legal_name.ilike."{term}"', f'trade_name.ilike."{term}"', f'email.ilike."{term}"']
            if is_admin and len(alnum) >= 3:
                clauses.append(f'doc.ilike."%{alnum}%"')
            elif not is_admin and len(alnum) in (11, 14):
                clauses.append(f"doc.eq.{alnum}")  # a COMPLETE document only: no prefix probing by staff
            query = query.or_(",".join(clauses))
        return query

    return refine


def _check_filters(kind: Optional[str], role: Optional[str]) -> None:
    if kind is not None and kind not in values(PartyKind):
        raise invalid("kind", "Tipo inválido.")
    if role is not None and role not in values(PartyRole):
        raise invalid("role", "Papel inválido.", code=PAPEL_INVALIDO)


def _sort_key(row: dict) -> tuple[str, str]:
    return (str(row.get("legal_name", "")).lower(), str(row["id"]))


def list_all(
    s: Scope, *, q: Optional[str] = None, kind: Optional[str] = None, role: Optional[str] = None,
    active: Optional[bool] = None, is_admin: bool = False,
) -> list[dict]:
    """EVERY matching party (raw, sorted), roles attached -- the export/role-filter source."""
    _check_filters(kind, role)
    rows = s.rows("parties", refine=_search_refine(q, kind, active, is_admin))
    if role is not None:
        in_role = {str(r["party_id"]) for r in s.rows(_ROLES, eq={"role": role})}
        rows = [r for r in rows if str(r["id"]) in in_role]
    rows.sort(key=_sort_key)
    return with_roles(s, rows)


def list_parties(
    s: Scope, *, q: Optional[str] = None, kind: Optional[str] = None, role: Optional[str] = None,
    active: Optional[bool] = None, page: int = 1, page_size: int = 20, is_admin: bool = False,
) -> tuple[list[dict], int, int, int]:
    """One page of parties (raw rows + `roles`) and the exact total: `(rows, total, page, page_size)`."""
    _check_filters(kind, role)
    if role is None:
        rows, total, page, size = s.page(
            "parties", page=page, page_size=page_size, refine=_search_refine(q, kind, active, is_admin),
            order=(("legal_name", False), ("id", False)),
        )
        return with_roles(s, rows), total, page, size
    from noctusai_lib.primitives.responses import calculate_pagination

    everything = list_all(s, q=q, kind=kind, role=role, active=active, is_admin=is_admin)
    page, size, offset = calculate_pagination(page, page_size)
    return everything[offset : offset + size], len(everything), page, size


# ─── write ───────────────────────────────────────────────────────────────────

_DUP = "Já existe um cadastro com este CPF/CNPJ."


def _clean(s: Scope, data: Mapping[str, Any], *, kind: str, existing: Optional[dict] = None) -> dict:
    """Normalised columns for the keys present in `data` (+ re-validated doc when kind/doc change)."""
    out: dict[str, Any] = {}
    for key in _TEXT_FIELDS:
        if key in data:
            out[key] = _blank(data[key])
    if "legal_name" in out and out["legal_name"] is None:
        raise invalid("legal_name", "Informe o nome / razão social.")
    if "email" in data:
        out["email"] = normalize_email(data["email"])
    if "phones" in data:
        out["phones"] = normalize_phones(data["phones"])
    if "address" in data:
        out["address"] = normalize_address(data["address"])
    doc_in = data["doc"] if "doc" in data else (existing or {}).get("doc")
    if "doc" in data or "kind" in data:
        out["doc"] = normalize_doc(kind, doc_in)
        if out["doc"]:
            dup = find_by_doc(s, out["doc"])
            if dup is not None and (existing is None or str(dup["id"]) != str(existing["id"])):
                raise conflict(DOCUMENTO_DUPLICADO, _DUP)
    if "kind" in data:
        out["kind"] = kind
    return out


def set_roles(s: Scope, party_id: Any, roles: Any) -> list[str]:
    """Make the party's role set EXACTLY `roles` (add the missing, drop the removed)."""
    wanted = set(normalize_roles(roles))
    pid = str(party_id)
    have = {r["role"] for r in s.rows(_ROLES, eq={"party_id": pid})}
    now = now_iso()
    adds = [{"id": new_id(), "org_id": s.org_id, "party_id": pid, "role": r, "created_at": now} for r in sorted(wanted - have)]
    if adds:
        s.tbl(_ROLES).insert(adds).execute()
    for role in sorted(have - wanted):
        s.tbl(_ROLES).delete().eq("org_id", s.org_id).eq("party_id", pid).eq("role", role).execute()
    return sorted(wanted)


def create_party(s: Scope, data: Mapping[str, Any]) -> dict:
    """Create a party (and its roles). Returns the raw row + `roles`."""
    kind = str(_plain(data["kind"]))
    if kind not in values(PartyKind):
        raise invalid("kind", "Tipo inválido.")
    roles = normalize_roles(data.get("roles"))
    row = _clean(s, {**data, "kind": kind}, kind=kind)
    now = now_iso()
    row = {
        "phones": [], "address": {}, "is_active": True,
        **row, "id": new_id(), "org_id": s.org_id, "created_at": now, "updated_at": now,
    }
    try:
        saved = first(s.tbl("parties").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(DOCUMENTO_DUPLICADO, _DUP) from exc
        raise
    try:
        set_roles(s, saved["id"], roles)
    except Exception:
        logger.error("parties: roles insert failed, rolling the new party back", exc_info=True)
        s.tbl("parties").delete().eq("org_id", s.org_id).eq("id", str(saved["id"])).execute()
        raise
    return {**saved, "roles": roles}


def update_party(s: Scope, party_id: Any, data: Mapping[str, Any]) -> dict:
    """Patch a party. `roles`, when present, REPLACES the role set. Returns the raw row + `roles`."""
    current = get_party(s, party_id)
    kind = str(_plain(data["kind"])) if data.get("kind") is not None else current["kind"]
    patch = {k: v for k, v in data.items() if k != "roles"}
    if patch.get("kind") is None:
        patch.pop("kind", None)
    for key in ("legal_name",):
        if key in patch and patch[key] is None:
            raise invalid(key, "Este campo não pode ficar vazio.")
    # a kind change re-validates the stored doc against the new kind even when `doc` is not sent
    cleaned = _clean(s, patch, kind=kind, existing=current)
    roles = current["roles"]
    if data.get("roles") is not None:
        roles = set_roles(s, party_id, data["roles"])
    if cleaned:
        cleaned["updated_at"] = now_iso()
        try:
            s.tbl("parties").update(cleaned).eq("org_id", s.org_id).eq("id", str(party_id)).execute()
        except Exception as exc:
            if is_unique_violation(exc):
                raise conflict(DOCUMENTO_DUPLICADO, _DUP) from exc
            raise
    return {**current, **cleaned, "roles": roles}


def set_active(s: Scope, party_id: Any, active: bool) -> dict:
    """Archive (`active=False`) or restore a party. Idempotent."""
    current = get_party(s, party_id)
    if bool(current.get("is_active", True)) == active:
        return current
    patch = {"is_active": active, "updated_at": now_iso()}
    s.tbl("parties").update(patch).eq("org_id", s.org_id).eq("id", str(party_id)).execute()
    return {**current, **patch}


def is_referenced(s: Scope, party_id: Any) -> bool:
    """True when any configured `reference_tables` row (this org) points at the party."""
    for table, column in s.cfg.reference_tables:
        resp = s.db.table(table).select(column).eq("org_id", s.org_id).eq(column, str(party_id)).limit(1).execute()
        if resp.data:
            return True
    return False


def delete_party(s: Scope, party_id: Any) -> None:
    """Hard delete, ONLY while nothing references the party; otherwise 409 (archive instead)."""
    s.get("parties", party_id, what="Cadastro")
    if is_referenced(s, party_id):
        raise conflict(PARCEIRO_EM_USO, "O cadastro é usado em outros registros; arquive-o em vez de excluir.", hint="archive")
    pid = str(party_id)
    s.tbl(_ROLES).delete().eq("org_id", s.org_id).eq("party_id", pid).execute()
    s.tbl("parties").delete().eq("org_id", s.org_id).eq("id", pid).execute()


__all__ = [
    "create_party",
    "delete_party",
    "find_by_doc",
    "get_party",
    "is_referenced",
    "list_all",
    "list_parties",
    "normalize_address",
    "normalize_doc",
    "normalize_email",
    "normalize_phones",
    "normalize_roles",
    "present_party",
    "set_active",
    "set_roles",
    "update_party",
    "with_roles",
]
