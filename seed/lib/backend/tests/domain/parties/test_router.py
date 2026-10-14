"""Router contract: paths, statuses, envelopes, pt-BR codes, authz (staff read / admin write), masking, isolation, CSV."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.parties import IMPORT_UPLOAD_MAX_BYTES, IMPORT_UPLOAD_PATH_PATTERN, csv_io
from noctusai_lib.domain.parties._common import Scope
from noctusai_lib.domain.parties.errors import PartiesError

from .conftest import CFG, ORG_A, VALID_CNPJ, VALID_CPF

U0 = "11111111-1111-1111-1111-111111111111"
P = "/api/parties"

#: (method, path, is_write) -- the whole surface.
ROUTES = [
    ("GET", P, False), ("POST", P, True), ("GET", f"{P}/export.csv", False), ("POST", f"{P}/import", True),
    ("GET", f"{P}/{U0}", False), ("PATCH", f"{P}/{U0}", True), ("PUT", f"{P}/{U0}/roles", True),
    ("POST", f"{P}/{U0}/archive", True), ("POST", f"{P}/{U0}/restore", True), ("DELETE", f"{P}/{U0}", True),
]


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


def mk(h, headers=None, **over):
    r = call(h, "POST", P, headers or h.admin, json={"kind": "PF", "legal_name": "Ana Souza", **over})
    assert r.status_code == 201, r.text
    return r.json()["data"]


@pytest.mark.parametrize("method, path, _write", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path, _write):
    assert call(h, method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if r[2]])
def test_staff_cannot_write(h, method, path, write):
    kw = {"files": {"file": ("a.csv", b"kind,legal_name\nPF,Ana\n", "text/csv")}} if path.endswith("/import") else {"json": {}}
    assert call(h, method, path, h.staff("user"), **kw).status_code == 403


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if not r[2]])
def test_staff_can_read(h, method, path, write):
    status = call(h, method, path, h.staff("user")).status_code
    assert status not in (401, 403)  # 200, or 404 for the placeholder id -- never an authz refusal


def test_extra_fields_are_rejected_not_silently_dropped(h):
    assert call(h, "POST", P, h.admin, json={"kind": "PF", "legal_name": "A", "typo_field": 1}).status_code == 422
    assert call(h, "POST", P, h.admin, json={"kind": "PF", "legal_name": "A", "address": {"cidade": "x"}}).status_code == 422
    assert call(h, "POST", P, h.admin, json={"kind": "XX", "legal_name": "A"}).status_code == 422
    assert call(h, "POST", P, h.admin, json={"kind": "PF", "legal_name": "A", "roles": ["ceo"]}).status_code == 422


def test_import_route_is_declared_for_the_body_cap():
    assert IMPORT_UPLOAD_PATH_PATTERN == "/api/parties/import"
    assert IMPORT_UPLOAD_MAX_BYTES > csv_io.MAX_IMPORT_BYTES  # multipart framing headroom


def test_lifecycle_through_http(h):
    p = mk(h, doc=VALID_CPF, roles=["customer"], phones=["11994573387"], email="Ana@X.com")
    assert p["roles"] == ["customer"] and p["doc"] == VALID_CPF and p["email"] == "ana@x.com"
    r = call(h, "PATCH", f"{P}/{p['id']}", h.admin, json={"trade_name": "Aninha", "roles": ["supplier"]})
    assert r.status_code == 200 and r.json()["data"]["roles"] == ["supplier"]
    r = call(h, "PUT", f"{P}/{p['id']}/roles", h.admin, json={"roles": ["carrier", "employee"]})
    assert r.json()["data"]["roles"] == ["carrier", "employee"]
    assert call(h, "POST", f"{P}/{p['id']}/archive", h.admin).json()["data"]["is_active"] is False
    assert call(h, "GET", f"{P}?active=true", h.staff()).json()["data"] == []
    assert call(h, "POST", f"{P}/{p['id']}/restore", h.admin).json()["data"]["is_active"] is True
    assert call(h, "DELETE", f"{P}/{p['id']}", h.admin).status_code == 204
    assert call(h, "GET", f"{P}/{p['id']}", h.staff()).status_code == 404


def test_pt_br_error_codes_and_statuses(h):
    mk(h, doc=VALID_CPF)
    r = call(h, "POST", P, h.admin, json={"kind": "PF", "legal_name": "Dup", "doc": VALID_CPF})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "documento_duplicado")
    r = call(h, "POST", P, h.admin, json={"kind": "PF", "legal_name": "Bad", "doc": "52998224726"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "documento_invalido")
    assert r.json()["error"]["details"]["field"] == "doc"
    r = call(h, "GET", f"{P}/{U0}", h.staff())
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = call(h, "PUT", f"{P}/{U0}/roles", h.admin, json={"roles": ["customer"]})
    assert r.status_code == 404  # no write before the 404
    assert call(h, "GET", f"{P}?role=ceo", h.staff()).status_code == 422


def test_delete_referenced_party_answers_409_with_archive_hint(h):
    p = mk(h)
    h.db.table("ref_things").insert({"id": U0, "org_id": ORG_A, "party_id": p["id"]}).execute()
    r = call(h, "DELETE", f"{P}/{p['id']}", h.admin)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "parceiro_em_uso")
    assert r.json()["error"]["details"]["hint"] == "archive"
    assert call(h, "GET", f"{P}/{p['id']}", h.staff()).status_code == 200


def test_lists_use_the_seed_envelopes(h):
    mk(h)
    r = call(h, "GET", f"{P}?page=1&page_size=10", h.staff()).json()
    assert set(r) == {"data", "pagination"} and r["pagination"]["total"] == 1
    assert call(h, "GET", f"{P}?page_size=101", h.staff()).status_code == 422
    assert set(call(h, "GET", f"{P}/{r['data'][0]['id']}", h.staff()).json()) == {"data"}


# ── LGPD masking ──


def test_doc_is_masked_for_staff_everywhere_and_whole_for_admin(h):
    p = mk(h, doc="529.982.247-25", roles=["customer"])
    assert p["doc"] == VALID_CPF  # the admin who wrote it sees it whole
    for path in (P, f"{P}/{p['id']}"):
        body = call(h, "GET", path, h.admin).json()["data"]
        assert (body[0] if isinstance(body, list) else body)["doc"] == VALID_CPF
        body = call(h, "GET", path, h.staff()).json()["data"]
        assert (body[0] if isinstance(body, list) else body)["doc"] == "***.982.247-**"
    csv_staff = call(h, "GET", f"{P}/export.csv", h.staff()).content.decode("utf-8-sig")
    assert VALID_CPF not in csv_staff and "***.982.247-**" in csv_staff
    assert VALID_CPF in call(h, "GET", f"{P}/export.csv", h.admin).content.decode("utf-8-sig")


# ── org isolation through HTTP ──


def test_org_b_sees_and_touches_nothing_of_org_a(h):
    a = mk(h, doc=VALID_CPF, roles=["customer"])
    b_staff, b_admin = h.staff("org-b"), h.staff("org-b-admin")
    assert call(h, "GET", P, b_staff).json()["pagination"]["total"] == 0
    assert call(h, "GET", f"{P}?role=customer", b_staff).json()["data"] == []
    for method, path, kw in (
        ("GET", f"{P}/{a['id']}", {}),
        ("PATCH", f"{P}/{a['id']}", {"json": {"legal_name": "Hacked"}}),
        ("PUT", f"{P}/{a['id']}/roles", {"json": {"roles": ["supplier"]}}),
        ("POST", f"{P}/{a['id']}/archive", {}),
        ("DELETE", f"{P}/{a['id']}", {}),
    ):
        assert call(h, method, path, b_admin, **kw).status_code == 404, (method, path)
    mine = call(h, "GET", f"{P}/{a['id']}", h.admin).json()["data"]
    assert mine["legal_name"] == "Ana Souza" and mine["is_active"] and mine["roles"] == ["customer"]
    # org B can register the same document: uniqueness is per tenant
    assert call(h, "POST", P, b_admin, json={"kind": "PF", "legal_name": "Ana B", "doc": VALID_CPF}).status_code == 201
    assert call(h, "GET", f"{P}/export.csv", b_staff).content.decode("utf-8-sig").strip().count("\n") == 1  # header + Ana B only


# ── CSV ──


def test_export_has_header_roles_and_neutralises_formulas(h):
    mk(h, legal_name='=HYPERLINK("http://x")', doc=VALID_CPF, roles=["customer", "supplier"],
       address={"city": "Santos", "state": "sp"}, phones=["11994573387", "1132165498"])
    r = call(h, "GET", f"{P}/export.csv", h.admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    text = r.content.decode("utf-8-sig")
    header, row = text.strip().split("\r\n")
    assert header.split(",")[:3] == ["kind", "doc", "legal_name"]
    assert "'=HYPERLINK" in row and "customer;supplier" in row and "+5511994573387;+551132165498" in row
    assert "Santos" in row and "SP" in row


def test_export_filters_apply(h):
    mk(h, legal_name="Cliente", roles=["customer"])
    mk(h, kind="PJ", legal_name="Fornecedor", doc=VALID_CNPJ, roles=["supplier"])
    text = call(h, "GET", f"{P}/export.csv?role=supplier", h.admin).content.decode("utf-8-sig")
    assert "Fornecedor" in text and "Cliente" not in text


def test_export_too_big_is_refused_not_truncated(h):
    mk(h)
    mk(h, legal_name="Bia")
    with pytest.raises(PartiesError) as e:
        csv_io.parties_csv(Scope(h.db, CFG, ORG_A), is_admin=True, max_rows=1)
    assert (e.value.code, e.value.status_code) == ("exportacao_grande_demais", 422)


CSV = (
    "tipo;documento;nome;email;telefones;papeis;ativo;address_city\n"
    "PF;529.982.247-25;Ana Souza;ana@x.com;11994573387;customer,supplier;sim;Santos\n"
    "PJ;11.222.333/0001-81;Beta Ltda;;1132165498;carrier;sim;\n"
    "PF;529.982.247-26;Doc Ruim;;;;;\n"          # bad check digit -> error
    f"PF;{VALID_CPF};Repetida;;;;;\n"             # duplicate inside the file -> skipped
    "PF;;Sem Documento;;;customer;;\n"
    ";;;;;;;\n"                                    # blank line is ignored
    "XX;;Tipo Ruim;;;;;\n"                         # bad kind -> error
)


def _upload(h, data: bytes, headers=None, **form):
    return call(h, "POST", f"{P}/import", headers or h.admin, files={"file": ("p.csv", data, "text/csv")}, data=form)


def test_import_creates_reports_and_skips(h):
    r = _upload(h, CSV.encode("utf-8"))
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["created"] == 3 and body["dry_run"] is False
    assert [s["line"] for s in body["skipped"]] == [5]
    assert [e["line"] for e in body["errors"]] == [4, 8]
    assert body["errors"][0]["code"] == "documento_invalido" and body["errors"][0]["field"] == "doc"
    listed = call(h, "GET", P, h.admin).json()["data"]
    assert sorted(p["legal_name"] for p in listed) == ["Ana Souza", "Beta Ltda", "Sem Documento"]
    ana = next(p for p in listed if p["legal_name"] == "Ana Souza")
    assert ana["roles"] == ["customer", "supplier"] and ana["address"] == {"city": "Santos"} and ana["phones"] == ["+5511994573387"]
    # re-importing is idempotent for documented parties: skipped, never duplicated
    again = _upload(h, CSV.encode("utf-8")).json()["data"]
    assert again["created"] == 1 and len(again["skipped"]) == 3  # only the document-less row is created again


def test_import_dry_run_writes_nothing(h):
    body = _upload(h, CSV.encode("utf-8"), dry_run="true").json()["data"]
    assert body["dry_run"] is True and body["created"] == 3 and len(body["errors"]) == 2
    assert call(h, "GET", P, h.admin).json()["pagination"]["total"] == 0


def test_import_accepts_comma_dialect_and_cp1252(h):
    body = _upload(h, "kind,legal_name,doc\nPF,José Antônio,\n".encode("cp1252")).json()["data"]
    assert body["created"] == 1
    assert call(h, "GET", P, h.admin).json()["data"][0]["legal_name"] == "José Antônio"


def test_import_rejects_bad_files(h):
    assert _upload(h, b"").status_code == 422
    r = _upload(h, b"foo,bar\n1,2\n")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "importacao_invalida")
    r = _upload(h, b"kind,legal_name\n" + b"PF,x\n" * (csv_io.MAX_IMPORT_ROWS + 1))
    assert (r.status_code, r.json()["error"]["code"]) == (422, "importacao_grande_demais")
    r = _upload(h, b"kind,legal_name\n" + b"x" * (csv_io.MAX_IMPORT_BYTES + 10))
    assert (r.status_code, r.json()["error"]["code"]) == (413, "importacao_grande_demais")


def test_import_keeps_formula_text_and_export_neutralises_it(h):
    _upload(h, b'kind,legal_name\nPF,"=1+1"\n')
    assert call(h, "GET", P, h.admin).json()["data"][0]["legal_name"] == "=1+1"
    assert "'=1+1" in call(h, "GET", f"{P}/export.csv", h.admin).content.decode("utf-8-sig")


def test_oversized_csv_field_is_a_422_not_a_500(h):
    big = b"kind,legal_name\nPF," + b"x" * 200_000 + b"\n"
    r = call(h, "POST", f"{P}/import", h.admin, files={"file": ("p.csv", big, "text/csv")})
    assert r.status_code == 422
    # and a malformed HEADER row (the first `next(reader)`) too
    r = call(h, "POST", f"{P}/import", h.admin, files={"file": ("p.csv", b"kind," + b"y" * 200_000 + b"\nPF,Ana\n", "text/csv")})
    assert r.status_code == 422
