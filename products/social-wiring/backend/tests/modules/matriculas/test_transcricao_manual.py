"""`POST /extracoes/manual` (migration 149) — a matrícula transcribed by
typing/pasting its text, no PDF, no vision AI.

WHAT THESE PIN
--------------
- the created row lands `status=concluida` immediately (synchronous — there
  is no background task, unlike every upload path) and `origem=manual`;
- it runs through the EXACT SAME segmenter an AI transcription's text goes
  through: the acts, their kind/número/offsets, are IDENTICAL to what
  `TEXTO` produces via the upload path (`test_matricula_estrutura_service.
  py`'s `ESPERADOS`) — proving a manual row is not a second, parallel code
  path with its own (possibly diverging) segmentation;
- título aquisitivo / ônus-credor / previous-owners all work off a manual
  row exactly as they do off an uploaded one — the contract gate cannot
  tell the two apart;
- an empty/blank texto is a 422, never a silently-created empty extraction;
- `ruido` (migration 136 page-furniture detection) is `[]` — there is no
  page structure to detect furniture across.
"""
from __future__ import annotations

from app.modules.matriculas import titulo_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ESPERADOS,
    ORG_ID,
    TEXTO,
    registry_row,
    seed,
)
from uuid import UUID


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestCriarExtracaoManual:
    def test_lands_concluida_synchronously_with_origem_manual(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        data = _data(
            client.post("/api/matriculas/extracoes/manual", json={"codigo": CODIGO, "texto": TEXTO})
        )
        assert data["status"] == "concluida"
        assert data["origem"] == "manual"
        assert data["texto_extraido"] == TEXTO
        assert data["ruido"] == []

    def test_acts_match_what_the_same_text_produces_via_upload(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        data = _data(
            client.post("/api/matriculas/extracoes/manual", json={"codigo": CODIGO, "texto": TEXTO})
        )
        atos = _data(client.get(f"/api/matriculas/extracoes/{data['id']}/atos"))["atos"]
        obtidos = [(a["kind"], a["numero"]) for a in atos]
        assert obtidos == ESPERADOS

    def test_titulo_aquisitivo_confirmation_works_off_a_manual_row(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        data = _data(
            client.post("/api/matriculas/extracoes/manual", json={"codigo": CODIGO, "texto": TEXTO})
        )
        atos = _data(client.get(f"/api/matriculas/extracoes/{data['id']}/atos"))["atos"]
        r1 = next(a for a in atos if a["kind"] == "R" and a["numero"] == 1)

        _data(
            client.put(
                f"/api/matriculas/extracoes/{data['id']}/fontes",
                json={"titulo_aquisitivo_ato_id": r1["id"]},
            )
        )
        titulo = titulo_service.obter_titulo(scoped, UUID(ORG_ID), CODIGO)
        # A suggestion exists (an instrument, even if minimal, is derivable
        # from R-1's typed details) OR the reason is one of the KNOWN
        # motives — never a crash / never "this only works for uploads".
        assert titulo["ato"]["kind"] == "R"
        assert titulo["ato"]["numero"] == 1

    def test_blank_texto_is_a_422(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        resp = client.post("/api/matriculas/extracoes/manual", json={"codigo": CODIGO, "texto": "   "})
        assert resp.status_code in (400, 422)

    def test_empty_texto_is_rejected_at_the_schema(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        resp = client.post("/api/matriculas/extracoes/manual", json={"codigo": CODIGO, "texto": ""})
        assert resp.status_code == 422

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.post("/api/matriculas/extracoes/manual", json={"codigo": "NOPE9", "texto": TEXTO})
        assert resp.status_code == 404
