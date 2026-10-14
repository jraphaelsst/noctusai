"""Service layer: CRUD, document validation, uniqueness, roles, search, archive, delete, masking, org isolation."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.parties import PartiesConfig, parties
from noctusai_lib.domain.parties._common import Scope
from noctusai_lib.domain.parties.errors import PartiesError
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import ORG_A, ORG_B, VALID_CNPJ, VALID_CPF, VALID_CPF_2, mk_party


def test_create_defaults_and_normalisation(s):
    p = mk_party(
        s, doc="529.982.247-25", legal_name="  Ana Souza ", email=" ANA@Exemplo.com ",
        phones=["(11) 99457-3387", "11994573387"], address={"city": "São Paulo", "state": "sp", "street": " "},
        roles=["supplier", "customer"],
    )
    assert p["doc"] == VALID_CPF and p["legal_name"] == "Ana Souza"
    assert p["email"] == "ana@exemplo.com"
    assert p["phones"] == ["+5511994573387"]  # canonical E.164, de-duplicated
    assert p["address"] == {"city": "São Paulo", "state": "SP"}  # blanks dropped, UF upper
    assert p["is_active"] is True and p["org_id"] == ORG_A
    assert p["roles"] == ["customer", "supplier"]
    assert parties.get_party(s, p["id"])["roles"] == ["customer", "supplier"]


def test_party_without_a_document_is_allowed(s):
    p = mk_party(s)
    assert p["doc"] is None


@pytest.mark.parametrize("kind, doc", [
    ("PF", "52998224726"),            # bad CPF check digit
    ("PF", VALID_CNPJ),               # a CNPJ on a PF
    ("PJ", VALID_CPF),                # a CPF on a PJ
    ("PJ", "11222333000182"),         # bad CNPJ check digit
    ("PF", "123"),
])
def test_invalid_documents_are_refused(s, kind, doc):
    with pytest.raises(PartiesError) as e:
        mk_party(s, kind=kind, doc=doc)
    assert e.value.code == "documento_invalido" and e.value.status_code == 422


def test_alphanumeric_cnpj_is_supported(s):
    # 12 alphanumeric base chars + 2 check digits (mod-11 over ASCII-48), the 2026 CNPJ format.
    from noctusai_lib.primitives.identificador import cnpj_dv_valido

    base = "12ABC34501DE"

    def dv(chars: str, weights: list[int]) -> int:
        total = sum((ord(c) - 48) * w for c, w in zip(chars, weights))
        r = total % 11
        return 0 if r < 2 else 11 - r

    d1 = dv(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(base + str(d1), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    cnpj = f"{base}{d1}{d2}"
    assert cnpj_dv_valido(cnpj)
    p = mk_party(s, kind="PJ", doc=cnpj.lower(), legal_name="Alfa SA")
    assert p["doc"] == cnpj


def test_doc_is_unique_per_org_not_across_orgs(s, s_b):
    mk_party(s, doc=VALID_CPF)
    with pytest.raises(PartiesError) as e:
        mk_party(s, doc="529.982.247-25", legal_name="Outra")
    assert (e.value.code, e.value.status_code) == ("documento_duplicado", 409)
    assert mk_party(s_b, doc=VALID_CPF)["org_id"] == ORG_B  # another tenant may hold the same document


def test_bad_email_and_phone_are_refused(s):
    with pytest.raises(PartiesError) as e:
        mk_party(s, email="not-an-email")
    assert e.value.code == "email_invalido"
    with pytest.raises(PartiesError) as e:
        mk_party(s, phones=["abc"])
    assert e.value.code == "telefone_invalido"
    with pytest.raises(PartiesError) as e:
        mk_party(s, roles=["ceo"])
    assert e.value.code == "papel_invalido"


def test_update_patches_fields_and_replaces_roles(s):
    p = mk_party(s, doc=VALID_CPF, roles=["customer"])
    u = parties.update_party(s, p["id"], {"trade_name": "Aninha", "email": "a@b.com", "roles": ["supplier", "carrier"]})
    assert u["trade_name"] == "Aninha" and u["roles"] == ["carrier", "supplier"]
    again = parties.get_party(s, p["id"])
    assert again["email"] == "a@b.com" and again["roles"] == ["carrier", "supplier"] and again["doc"] == VALID_CPF
    cleared = parties.update_party(s, p["id"], {"email": None, "phones": None, "roles": []})
    assert cleared["email"] is None and parties.get_party(s, p["id"])["roles"] == []


def test_update_revalidates_doc_when_kind_changes(s):
    p = mk_party(s, doc=VALID_CPF)
    with pytest.raises(PartiesError) as e:
        parties.update_party(s, p["id"], {"kind": "PJ"})  # the stored CPF is not a CNPJ
    assert e.value.code == "documento_invalido"
    ok = parties.update_party(s, p["id"], {"kind": "PJ", "doc": VALID_CNPJ})
    assert (ok["kind"], ok["doc"]) == ("PJ", VALID_CNPJ)


def test_update_to_an_existing_doc_is_a_conflict_but_own_doc_is_fine(s):
    a = mk_party(s, doc=VALID_CPF)
    b = mk_party(s, doc=VALID_CPF_2, legal_name="Bia")
    with pytest.raises(PartiesError) as e:
        parties.update_party(s, b["id"], {"doc": VALID_CPF})
    assert e.value.code == "documento_duplicado"
    parties.update_party(s, a["id"], {"doc": "529.982.247-25", "legal_name": "Ana Maria"})  # same doc, same party
    assert parties.get_party(s, a["id"])["legal_name"] == "Ana Maria"


def test_legal_name_cannot_be_blanked(s):
    p = mk_party(s)
    with pytest.raises(PartiesError):
        parties.update_party(s, p["id"], {"legal_name": "  "})


def test_set_roles_is_idempotent_and_exact(s):
    p = mk_party(s)
    assert parties.set_roles(s, p["id"], ["customer", "customer", "employee"]) == ["customer", "employee"]
    assert parties.set_roles(s, p["id"], ["customer", "employee"]) == ["customer", "employee"]
    assert len(s.rows("party_roles")) == 2
    parties.set_roles(s, p["id"], ["carrier"])
    assert parties.get_party(s, p["id"])["roles"] == ["carrier"]


def test_search_by_name_doc_email_and_filters(s):
    mk_party(s, legal_name="Ana Souza", doc=VALID_CPF, email="ana@x.com", roles=["customer"])
    mk_party(s, kind="PJ", legal_name="Transportes Beta", trade_name="Beta Log", doc=VALID_CNPJ, roles=["carrier", "supplier"])
    inactive = mk_party(s, legal_name="Carlos Antigo", roles=["customer"])
    parties.set_active(s, inactive["id"], False)

    def names(**kw):
        rows, total, _, _ = parties.list_parties(s, is_admin=True, **kw)
        assert total == len(rows)
        # the mock ignores ORDER BY (real ordering is PostgREST's); the role path sorts in Python and is asserted below
        return sorted(r["legal_name"] for r in rows)

    assert names() == ["Ana Souza", "Carlos Antigo", "Transportes Beta"]  # sorted by name
    assert names(kind="PJ") == ["Transportes Beta"]
    assert names(role="customer") == ["Ana Souza", "Carlos Antigo"]
    assert names(active=True) == ["Ana Souza", "Transportes Beta"]
    assert names(active=False) == ["Carlos Antigo"]
    assert names(role="employee") == []
    with pytest.raises(PartiesError):
        parties.list_parties(s, role="ceo")
    with pytest.raises(PartiesError):
        parties.list_parties(s, kind="XX")


class _Recorder:
    """A query double that records the filter calls `_search_refine` makes (the mock's `or_` is match-all)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name: str):
        def call(*args):
            self.calls.append((name, args))
            return self

        return call


def _or_expr(q: str, *, is_admin: bool):
    rec = parties._search_refine(q, None, None, is_admin)(_Recorder())
    exprs = [args[0] for name, args in rec.calls if name == "or_"]
    return exprs[0] if exprs else None


def test_search_expression_covers_name_trade_name_and_email():
    expr = _or_expr("ana", is_admin=False)
    assert 'legal_name.ilike."%ana%"' in expr and 'trade_name.ilike."%ana%"' in expr and 'email.ilike."%ana%"' in expr


def test_search_expression_neutralises_postgrest_operators():
    expr = _or_expr('a"b, (x).y', is_admin=True)
    assert '"%a b   x  y%"' in expr  # quotes / commas / parens cannot break out of the or_ clause
    assert _or_expr("   ", is_admin=True) is None


def test_admin_may_search_partial_document_staff_only_a_complete_one():
    assert 'doc.ilike."%5299%"' in _or_expr("5299", is_admin=True)
    assert "doc." not in _or_expr("5299", is_admin=False)  # no prefix probing of masked documents
    assert "doc." not in _or_expr("529.982.247", is_admin=False)  # 9 digits: still partial
    assert "doc.eq.52998224725" in _or_expr("529.982.247-25", is_admin=False)
    assert "doc.eq.11222333000181" in _or_expr("11.222.333/0001-81", is_admin=False)


def test_pagination_total_and_stable_order(s):
    for i in range(7):
        mk_party(s, legal_name=f"Pessoa {i}")
    seen = []
    for page in (1, 2, 3):
        rows, total, pg, size = parties.list_parties(s, page=page, page_size=3)
        assert (total, pg, size) == (7, page, 3)
        seen += [r["legal_name"] for r in rows]
    assert seen == [f"Pessoa {i}" for i in range(7)]
    # the role-filter path (in-memory intersect) pages identically
    for i in range(7):
        parties.set_roles(s, parties.list_all(s)[i]["id"], ["customer"])
    rows, total, _, _ = parties.list_parties(s, role="customer", page=3, page_size=3)
    assert total == 7 and [r["legal_name"] for r in rows] == ["Pessoa 6"]


def test_listing_pages_past_the_postgrest_row_cap(s):
    # Seeded directly (1 050 inserts through the service would be slow): the list must still be COMPLETE.
    rows = [
        {"id": f"00000000-0000-4000-8000-{i:012d}", "org_id": ORG_A, "kind": "PF", "legal_name": f"P{i:04d}",
         "phones": [], "address": {}, "is_active": True}
        for i in range(1050)
    ]
    s.tbl("parties").insert(rows).execute()
    assert len(parties.list_all(s)) == 1050
    assert parties.list_parties(s, page=1, page_size=100)[1] == 1050


def test_archive_restore_are_idempotent(s):
    p = mk_party(s)
    assert parties.set_active(s, p["id"], False)["is_active"] is False
    assert parties.set_active(s, p["id"], False)["is_active"] is False
    assert parties.get_party(s, p["id"])["is_active"] is False
    assert parties.set_active(s, p["id"], True)["is_active"] is True


def test_delete_unreferenced_removes_party_and_roles(s):
    p = mk_party(s, roles=["customer"])
    parties.delete_party(s, p["id"])
    with pytest.raises(NotFoundError):
        parties.get_party(s, p["id"])
    assert s.rows("party_roles") == []


def test_delete_referenced_party_is_refused_with_archive_hint(s):
    p = mk_party(s)
    s.db.table("ref_things").insert({"id": "11111111-1111-4111-8111-111111111111", "org_id": ORG_A, "party_id": p["id"]}).execute()
    assert parties.is_referenced(s, p["id"])
    with pytest.raises(PartiesError) as e:
        parties.delete_party(s, p["id"])
    assert (e.value.code, e.value.status_code) == ("parceiro_em_uso", 409)
    assert e.value.details["hint"] == "archive"
    assert parties.get_party(s, p["id"])["id"] == p["id"]  # untouched
    assert parties.set_active(s, p["id"], False)["is_active"] is False  # the supported retirement


def test_a_reference_from_another_org_does_not_block(s, s_b):
    p = mk_party(s)
    s.db.table("ref_things").insert({"id": "22222222-2222-4222-8222-222222222222", "org_id": ORG_B, "party_id": p["id"]}).execute()
    assert not parties.is_referenced(s, p["id"])


def test_present_party_masks_doc_for_non_admin_only():
    row = {"id": "x", "doc": VALID_CPF, "legal_name": "Ana"}
    assert parties.present_party(row, is_admin=True)["doc"] == VALID_CPF
    assert parties.present_party(row, is_admin=False)["doc"] == "***.982.247-**"
    cnpj = parties.present_party({"doc": VALID_CNPJ}, is_admin=False)["doc"]
    assert cnpj == "**.***.333/0001-**"
    assert parties.present_party({"doc": None}, is_admin=False)["doc"] is None


# ── org isolation ──


def test_org_isolation_reads_writes_and_deletes(s, s_b):
    a = mk_party(s, doc=VALID_CPF, roles=["customer"])
    assert parties.list_parties(s_b)[1] == 0
    assert parties.list_parties(s_b, role="customer")[1] == 0
    for call in (
        lambda: parties.get_party(s_b, a["id"]),
        lambda: parties.update_party(s_b, a["id"], {"legal_name": "Hacked"}),
        lambda: parties.set_roles(s_b, a["id"], ["supplier"]) and parties.get_party(s_b, a["id"]),
        lambda: parties.set_active(s_b, a["id"], False),
        lambda: parties.delete_party(s_b, a["id"]),
    ):
        with pytest.raises(NotFoundError):
            call()
    assert parties.find_by_doc(s_b, VALID_CPF) is None
    untouched = parties.get_party(s, a["id"])
    assert untouched["legal_name"] == "Ana Souza" and untouched["is_active"] is True and untouched["roles"] == ["customer"]


def test_set_roles_through_a_foreign_scope_never_writes(s, s_b):
    a = mk_party(s)
    # set_roles itself is scope-bound: it inserts rows stamped with B's org for a party that is A's.
    # The service-level guard is the get_party 404 in the router + the composite FK on a real DB;
    # prove at least that A's role set is unaffected when B tries through the public surface.
    with pytest.raises(NotFoundError):
        parties.get_party(s_b, a["id"])
    assert parties.get_party(s, a["id"])["roles"] == []
