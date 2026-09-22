"""`PUT /api/matriculas/extracoes/{extracao_id}/imovel` — link an EXISTING
transcription to a property (migration 150).

WHAT THESE PIN
--------------
- an extraction with no código yet (`codigo IS NULL`) links successfully,
  and the response is the SAME summary shape `GET /extracoes` returns;
- an unregistered código is a 422, before anything is written;
- linking is idempotent — the same código twice is a no-op 200, not a
  refusal;
- an extraction already linked to a DIFFERENT código is a 409 UNLESS
  `substituir=true` — and even then it is STILL a 409, because the
  database's write-once trigger on `matricula_extracoes.codigo`
  (migrations 111/135/136) has no escape hatch for `substituir` to open;
  this only changes which of the two messages comes back;
- `GET /extracoes?sem_imovel=true` narrows to the unlinked pool the picker
  offers.

Auth is not re-tested here — `test_matriculas_auth_boundary.py` enumerates
every mounted route and asserts a strict 401 on each.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.matriculas.conftest import CODIGO, extracao_row, registry_row, seed


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


OUTRO_CODIGO = "AP9999"


class TestVincularImovel:
    def test_linking_an_unlinked_extraction_succeeds(self, client, scoped):
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row(CODIGO)],
            extracoes=[extracao_row(eid, codigo=None)],
        )
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": CODIGO}
        )
        body = _data(resp)
        assert body["codigo"] == CODIGO
        assert body["id"] == eid
        # The summary shape, not the full row — no `texto_extraido` key at all.
        assert "texto_extraido" not in body

        atualizado = [
            r for r in scoped.table("matricula_extracoes").select("*").execute().data
            if r["id"] == eid
        ][0]
        assert atualizado["codigo"] == CODIGO

    def test_the_link_is_logged(self, client, scoped):
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row(CODIGO)],
            extracoes=[extracao_row(eid, codigo=None)],
        )
        client.put(f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": CODIGO})

        acessos = scoped.table("imovel_documento_acessos").select("*").execute().data
        assert any(
            a["extracao_id"] == eid and a["acao"] == "imovel_vinculado"
            for a in acessos
        )

    def test_the_codigo_is_normalized_to_upper(self, client, scoped):
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row(CODIGO)],
            extracoes=[extracao_row(eid, codigo=None)],
        )
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": CODIGO.lower()}
        )
        assert _data(resp)["codigo"] == CODIGO

    def test_an_unregistered_codigo_is_refused_with_422(self, client, scoped):
        eid = str(uuid4())
        seed(scoped, registry=[], extracoes=[extracao_row(eid, codigo=None)])
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": "NUNCA-VISTO"}
        )
        assert resp.status_code == 422, resp.text

        atualizado = [
            r for r in scoped.table("matricula_extracoes").select("*").execute().data
            if r["id"] == eid
        ][0]
        assert atualizado["codigo"] is None, "nothing must be written on a 422"

    def test_linking_to_the_same_codigo_twice_is_idempotent(self, client, scoped):
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row(CODIGO)],
            extracoes=[extracao_row(eid, codigo=CODIGO)],
        )
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": CODIGO}
        )
        assert resp.status_code == 200, resp.text
        assert _data(resp)["codigo"] == CODIGO

    def test_relinking_to_a_different_codigo_without_substituir_is_409(
        self, client, scoped
    ):
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row(CODIGO), registry_row(OUTRO_CODIGO)],
            extracoes=[extracao_row(eid, codigo=CODIGO)],
        )
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": OUTRO_CODIGO}
        )
        assert resp.status_code == 409, resp.text

        atualizado = [
            r for r in scoped.table("matricula_extracoes").select("*").execute().data
            if r["id"] == eid
        ][0]
        assert atualizado["codigo"] == CODIGO, "the original link must survive a refusal"

    def test_relinking_with_substituir_is_still_409(self, client, scoped):
        """🔴 The DB's write-once guard (migrations 111/135/136) has NO
        escape hatch — `substituir=true` cannot make the database accept a
        change to an already-set `codigo`. This endpoint refuses BEFORE
        ever attempting the write, so the caller gets a named 409 instead
        of a raw driver exception."""
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row(CODIGO), registry_row(OUTRO_CODIGO)],
            extracoes=[extracao_row(eid, codigo=CODIGO)],
        )
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel",
            json={"codigo": OUTRO_CODIGO, "substituir": True},
        )
        assert resp.status_code == 409, resp.text

        atualizado = [
            r for r in scoped.table("matricula_extracoes").select("*").execute().data
            if r["id"] == eid
        ][0]
        assert atualizado["codigo"] == CODIGO

    def test_a_missing_extracao_is_404(self, client, scoped):
        seed(scoped, registry=[registry_row(CODIGO)], extracoes=[])
        resp = client.put(
            f"/api/matriculas/extracoes/{uuid4()}/imovel", json={"codigo": CODIGO}
        )
        assert resp.status_code == 404, resp.text

    def test_org_scoped_an_extracao_from_another_org_is_404(self, client, scoped):
        eid = str(uuid4())
        row = extracao_row(eid, codigo=None)
        row["org_id"] = "00000000-0000-4000-8000-000000000099"
        seed(scoped, registry=[registry_row(CODIGO)], extracoes=[row])
        resp = client.put(
            f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": CODIGO}
        )
        assert resp.status_code == 404, resp.text


class TestListarSemImovel:
    """`GET /extracoes` reads through the CALLER's own token (`get_user_
    client`), unlike the structured/PUT routes above (`get_matriculas_
    client`) — see this router's module docstring, point 3. So these seed
    `matricula_extracoes` on `client.mock_supabase` directly, the same
    convention `tests/modules/test_matriculas_router.py::TestListarExtracoes`
    already uses for this exact route — not `seed(scoped, ...)`, which
    writes through a DIFFERENT scoped mock instance this route never reads."""

    def test_sem_imovel_narrows_to_unlinked_extractions(self, client, scoped):
        linked = extracao_row(str(uuid4()), codigo=CODIGO)
        unlinked = extracao_row(str(uuid4()), codigo=None)
        client.mock_supabase.set_table_data("matricula_extracoes", [linked, unlinked])

        resp = client.get("/api/matriculas/extracoes", params={"sem_imovel": "true"})
        assert resp.status_code == 200, resp.text
        ids = {r["id"] for r in resp.json()["data"]}
        assert ids == {unlinked["id"]}

    def test_without_the_flag_every_extraction_is_listed(self, client, scoped):
        linked = extracao_row(str(uuid4()), codigo=CODIGO)
        unlinked = extracao_row(str(uuid4()), codigo=None)
        client.mock_supabase.set_table_data("matricula_extracoes", [linked, unlinked])

        resp = client.get("/api/matriculas/extracoes")
        ids = {r["id"] for r in resp.json()["data"]}
        assert ids == {linked["id"], unlinked["id"]}
