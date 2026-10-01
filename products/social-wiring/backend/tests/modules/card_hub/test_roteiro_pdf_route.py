"""`GET .../roteiros/{id}/pdf` end to end through the real app (CONTRACT §10 item 3).

The route is the one place the PDF service's three inputs meet: the roteiro,
the proprietários of each imóvel (`proprietarios_service.por_codigos`) and the
photos (`carregar_fotos`, blocking I/O pushed off the event loop). Pinned here:
the response carries the server-built filename, and a proprietário registered
for an imóvel reaches the document.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_roteiros import (
    _auth,
    _criar,
    _seed,
    imovel_row,
)


def _seed_sem_foto(scoped):
    cid, aid = _seed(scoped, codigos=("ONE9001", "ONE9002"))
    # No photo ⇒ `carregar_fotos` has nothing to download (no network in tests).
    scoped.set_table_data(
        "imoveis",
        [imovel_row(c, foto_destaque=None) for c in ("ONE9001", "ONE9002")],
    )
    return cid, aid


def _proprietario(codigo: str, cliente_id: str) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo": codigo,
        "cliente_id": cliente_id,
        "empresa_id": None,
        "origem": "manual",
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


class TestRoteiroPdfRoute:
    def test_serves_a_pdf_named_by_the_service(self, client, scoped):
        cid, _ = _seed_sem_foto(scoped)
        roteiro = _criar(client, cid, ["ONE9002", "ONE9001"], data_visita="2026-10-10")

        resp = client.get(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/pdf", headers=_auth()
        )

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b"%PDF-"
        assert (
            f'filename="roteiro-{roteiro["id"][:8]}-2026-10-10.pdf"'
            in resp.headers["content-disposition"]
        )

    def test_the_imoveis_proprietarios_reach_the_document(self, client, scoped):
        fitz = pytest.importorskip("fitz", reason="PyMuPDF is a declared requirement")
        cid, _ = _seed_sem_foto(scoped)
        dono = str(uuid4())
        scoped.set_table_data(
            "clientes", [cliente_row(cid), cliente_row(dono, nome="Dona Rita", cpf="52998224725")]
        )
        scoped.set_table_data("imovel_proprietarios", [_proprietario("ONE9001", dono)])
        roteiro = _criar(client, cid, ["ONE9001", "ONE9002"], data_visita="2026-10-10")

        resp = client.get(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/pdf", headers=_auth()
        )

        assert resp.status_code == 200, resp.text
        paginas = [p.get_text() for p in fitz.open(stream=resp.content, filetype="pdf")]
        assert len(paginas) == 2
        assert "Dona Rita" in paginas[0]
        assert "Dona Rita" not in paginas[1]
