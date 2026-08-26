"""Roteiros + visitas — the qualificação → visita funnel (migration 082).

WHAT THIS SLICE EXISTS FOR
--------------------------
A visit used to be an agendamento with `tipo='visita'` — a calendar entry,
which cannot hold several properties, cannot be ordered, cannot be printed and,
above all, cannot be COUNTED. The user asked for the count explicitly: "This has
to be contabilized. Visitas that happened and the ones that didn't."

`TestContabilizacao` is that sentence as assertions.

🔴 THE LOAD-BEARING GROUP IS `TestRegistryNotMirror`. The user asked for FKs so
that per-imóvel statistics and a 2024→2028 cliente history stay readable. A FK
to `imoveis` would have DEFEATED that: the mirror only holds ACTIVE listings, an
imóvel leaves it when it is SOLD, and 35% of registered imóveis are already
gone from it (prod, 2026-08-25). Those tests hold the registry-not-mirror
decision shut on both legs — a delisted imóvel is still visitable, and it still
renders.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_agendamentos import atendimento_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def registry_row(codigo: str, *, ativo=True, **snap) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo_canonical": codigo,
        "codigo_display": codigo,
        "ativo_no_vista": ativo,
        "origem_descoberta": "vista_sync",
        "snap_titulo": snap.get("titulo"),
        "snap_bairro": snap.get("bairro"),
        "snap_cidade": snap.get("cidade"),
        "snap_uf": snap.get("uf"),
        "snap_foto_destaque": snap.get("foto"),
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def imovel_row(codigo: str, **over) -> dict:
    row = {
        "org_id": ORG_ID,
        "codigo": codigo,
        "codigo_norm": codigo,
        "titulo": f"Apartamento {codigo}",
        "empreendimento": "Edifício Aurora",
        "logradouro": "Rua das Palmeiras",
        "numero": "320",
        "complemento": "apto 91",
        "bairro": "Centro",
        "cidade": "Florianópolis",
        "uf": "SC",
        "cep": "88010-000",
        "foto_destaque": "https://cdn.example/one.jpg",
        "corretores": [{"nome": "Ana Prado", "email": "ana@example.com"}],
    }
    row.update(over)
    return row


def _seed(scoped, *, codigos=("ONE9001", "ONE9002"), atendimentos=None, mirror=True):
    cid = str(uuid4())
    aid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("atendimentos", atendimentos or [atendimento_row(aid, cid)])
    scoped.set_table_data("imovel_registry", [registry_row(c) for c in codigos])
    scoped.set_table_data("imoveis", [imovel_row(c) for c in codigos] if mirror else [])
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("roteiros", [])
    scoped.set_table_data("visitas", [])
    return cid, aid


def _criar(client, cid, codigos, **body) -> dict:
    resp = client.post(
        f"/api/clientes/{cid}/roteiros",
        json={"imoveis": list(codigos), **body},
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCriacao:
    def test_one_visita_per_property_in_the_order_given(self, client, scoped):
        """"First this property, then that one, and last this one" — the order
        the user drags IS the payload, and it comes back the same way."""
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002", "ONE9003"))
        roteiro = _criar(client, cid, ["ONE9003", "ONE9001", "ONE9002"])

        assert [v["codigo"] for v in roteiro["visitas"]] == [
            "ONE9003", "ONE9001", "ONE9002",
        ]
        assert [v["ordem"] for v in roteiro["visitas"]] == [0, 1, 2]
        assert {v["status"] for v in roteiro["visitas"]} == {"pendente"}

    def test_codigo_is_canonicalised(self, client, scoped):
        """Migration 062's one expression. A lowercase código typed anywhere
        must land on the same row as the uppercase one, or the FK misses and
        the imóvel silently has two histories."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["  one9001 "])
        assert roteiro["visitas"][0]["codigo"] == "ONE9001"

    def test_unknown_codigo_is_404_not_500(self, client, scoped):
        """`ensure_imovel` checks the registry EXPLICITLY. Left to the FK, an
        unknown código would surface as a driver 500 telling the caller
        nothing."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        resp = client.post(
            f"/api/clientes/{cid}/roteiros",
            json={"imoveis": ["ONE9001", "NOPE0001"]},
            headers=_auth(),
        )
        assert resp.status_code == 404, resp.text

    def test_duplicate_codigo_is_refused_not_deduped(self, client, scoped):
        """Silently collapsing a repeat would change the order the user dragged
        without telling them."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        resp = client.post(
            f"/api/clientes/{cid}/roteiros",
            json={"imoveis": ["ONE9001", "one9001"]},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert "ONE9001" in resp.text

    def test_empty_list_is_rejected_by_the_schema(self, client, scoped):
        cid, _ = _seed(scoped)
        resp = client.post(
            f"/api/clientes/{cid}/roteiros", json={"imoveis": []}, headers=_auth()
        )
        assert resp.status_code == 422, resp.text

    def test_refuses_to_guess_between_two_open_atendimentos(self, client, scoped):
        """409, never a guess — filing a route against the wrong deal is how
        2024's history ends up on a live negotiation."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "atendimentos",
            [atendimento_row(str(uuid4()), cid), atendimento_row(str(uuid4()), cid)],
        )
        scoped.set_table_data("imovel_registry", [registry_row("ONE9001")])
        scoped.set_table_data("imoveis", [imovel_row("ONE9001")])
        scoped.set_table_data("imovel_dados", [])
        scoped.set_table_data("roteiros", [])
        scoped.set_table_data("visitas", [])

        resp = client.post(
            f"/api/clientes/{cid}/roteiros",
            json={"imoveis": ["ONE9001"]},
            headers=_auth(),
        )
        assert resp.status_code == 409, resp.text


class TestContabilizacao:
    """🔴 "This has to be contabilized. Visitas that happened and the ones that
    didn't." — the user, verbatim."""

    def test_three_buckets_not_two(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002", "ONE9003"))
        roteiro = _criar(client, cid, ["ONE9001", "ONE9002", "ONE9003"])
        rid, visitas = roteiro["id"], roteiro["visitas"]

        for visita, status in zip(visitas, ("realizada", "nao_realizada", "pendente")):
            if status == "pendente":
                continue
            resp = client.patch(
                f"/api/clientes/{cid}/roteiros/{rid}/visitas/{visita['id']}",
                json={"status": status},
                headers=_auth(),
            )
            assert resp.status_code == 200, resp.text

        contagem = client.get(f"/api/clientes/{cid}/roteiros", headers=_auth()).json()[
            "items"
        ][0]["contagem"]
        assert contagem == {
            "total": 3,
            "realizadas": 1,
            "nao_realizadas": 1,
            "pendentes": 1,
        }

    def test_feedback_em_is_stamped_once_and_never_moves(self, client, scoped):
        """It is the timeline's `ocorrido_em`. Re-stamping would move a past
        event forward in the sort and lie about when it happened."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]
        url = f"/api/clientes/{cid}/roteiros/{rid}/visitas/{vid}"

        assert client.get(f"/api/clientes/{cid}/roteiros", headers=_auth()).json()[
            "items"
        ][0]["visitas"][0]["feedback_em"] is None

        primeiro = client.patch(url, json={"status": "realizada"}, headers=_auth()).json()
        assert primeiro["feedback_em"] is not None

        depois = client.patch(
            url, json={"status": "nao_realizada", "observacao": "não atendeu"},
            headers=_auth(),
        ).json()
        assert depois["feedback_em"] == primeiro["feedback_em"]
        assert depois["observacao"] == "não atendeu"

    def test_pendente_carries_no_feedback_timestamp(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]
        out = client.patch(
            f"/api/clientes/{cid}/roteiros/{rid}/visitas/{vid}",
            json={"status": "pendente"},
            headers=_auth(),
        ).json()
        assert out["feedback_em"] is None

    def test_unknown_status_is_422(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        resp = client.patch(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas/"
            f"{roteiro['visitas'][0]['id']}",
            json={"status": "talvez"},
            headers=_auth(),
        )
        assert resp.status_code == 422, resp.text


class TestOrdem:
    def test_reorder_rewrites_positions(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002", "ONE9003"))
        roteiro = _criar(client, cid, ["ONE9001", "ONE9002", "ONE9003"])
        rid = roteiro["id"]
        invertido = [v["id"] for v in reversed(roteiro["visitas"])]

        resp = client.put(
            f"/api/clientes/{cid}/roteiros/{rid}/ordem",
            json={"visita_ids": invertido},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert [v["codigo"] for v in resp.json()["visitas"]] == [
            "ONE9003", "ONE9002", "ONE9001",
        ]
        assert [v["ordem"] for v in resp.json()["visitas"]] == [0, 1, 2]

    def test_partial_set_is_refused(self, client, scoped):
        """A partial reorder that silently succeeded would leave two visitas
        sharing a position and the route in an order nobody chose."""
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002"))
        roteiro = _criar(client, cid, ["ONE9001", "ONE9002"])
        resp = client.put(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/ordem",
            json={"visita_ids": [roteiro["visitas"][0]["id"]]},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text

    def test_foreign_id_is_refused(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        resp = client.put(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/ordem",
            json={"visita_ids": [str(uuid4())]},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text


class TestRegistryNotMirror:
    """🔴 The FK target decision (migration 082 header · 076 before it).

    A FK to `imoveis` would reject a third of the catalog at INSERT and delete
    our history on delist. These two tests are what a future "let's just point
    it at the mirror, it's simpler" refactor has to get past.
    """

    def test_a_delisted_imovel_can_still_be_put_on_a_roteiro(self, client, scoped):
        """It has left the Vista mirror — because it SOLD, which is exactly
        when its visit history matters. The registry still knows it."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("atendimentos", [atendimento_row(str(uuid4()), cid)])
        scoped.set_table_data(
            "imovel_registry",
            [registry_row("ONE4770", ativo=False, titulo="Cobertura vendida", bairro="Trindade", cidade="Florianópolis", uf="SC")],
        )
        scoped.set_table_data("imoveis", [])  # gone from the catalog
        scoped.set_table_data("imovel_dados", [])
        scoped.set_table_data("roteiros", [])
        scoped.set_table_data("visitas", [])

        roteiro = _criar(client, cid, ["ONE4770"])
        imovel = roteiro["visitas"][0]["imovel"]
        assert imovel is not None, "a delisted imóvel must still render"
        assert imovel["fonte"] == "registry"
        assert imovel["ativo_no_vista"] is False
        assert imovel["titulo"] == "Cobertura vendida"
        assert imovel["bairro"] == "Trindade"
        # The registry snapshot is deliberately narrower than the mirror — no
        # street, no empreendimento. Null is the honest answer, not a gap.
        assert imovel["logradouro"] is None
        assert imovel["corretores"] == []

    def test_the_mirror_is_preferred_while_the_imovel_is_listed(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        imovel = roteiro["visitas"][0]["imovel"]
        assert imovel["fonte"] == "imoveis"
        assert imovel["ativo_no_vista"] is True
        assert imovel["empreendimento"] == "Edifício Aurora"
        assert imovel["logradouro"] == "Rua das Palmeiras"
        assert imovel["foto_destaque"] == "https://cdn.example/one.jpg"


class TestCaptacao:
    def test_prefers_imovel_dados_captador_over_the_vista_corretores(
        self, client, scoped
    ):
        """`captador_user_id` (migration 075) is the canonical model — a USER,
        because the commission slice is attributed to it and two spellings of a
        free-text name become two people."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        user_id = str(uuid4())
        scoped.set_table_data(
            "imovel_dados",
            [{"org_id": ORG_ID, "codigo": "ONE9001", "captador_user_id": user_id}],
        )
        roteiro = _criar(client, cid, ["ONE9001"])
        captacao = roteiro["visitas"][0]["imovel"]["captacao"]
        assert captacao is not None
        assert captacao["id"] == user_id

    def test_no_captador_is_null_never_reassigned(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        assert roteiro["visitas"][0]["imovel"]["captacao"] is None


class TestPropriedade:
    """The ownership check IS the authorisation — an id alone must never be
    enough to reach someone else's route."""

    def test_another_clientes_roteiro_is_404(self, client, scoped):
        cid_a = str(uuid4())
        cid_b = str(uuid4())
        aid_a = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid_a), cliente_row(cid_b)])
        scoped.set_table_data(
            "atendimentos",
            [atendimento_row(aid_a, cid_a), atendimento_row(str(uuid4()), cid_b)],
        )
        scoped.set_table_data("imovel_registry", [registry_row("ONE9001")])
        scoped.set_table_data("imoveis", [imovel_row("ONE9001")])
        scoped.set_table_data("imovel_dados", [])
        scoped.set_table_data("roteiros", [])
        scoped.set_table_data("visitas", [])

        roteiro = _criar(client, cid_a, ["ONE9001"])

        for method, url in (
            ("get", f"/api/clientes/{cid_b}/roteiros/{roteiro['id']}/pdf"),
            ("delete", f"/api/clientes/{cid_b}/roteiros/{roteiro['id']}"),
        ):
            resp = getattr(client, method)(url, headers=_auth())
            assert resp.status_code == 404, f"{method} {url} -> {resp.status_code}"

    def test_a_visita_reached_through_the_wrong_roteiro_is_404(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002"))
        um = _criar(client, cid, ["ONE9001"])
        outro = _criar(client, cid, ["ONE9002"])

        resp = client.patch(
            f"/api/clientes/{cid}/roteiros/{outro['id']}/visitas/"
            f"{um['visitas'][0]['id']}",
            json={"status": "realizada"},
            headers=_auth(),
        )
        assert resp.status_code == 404, resp.text


class TestVisitaAvulsa:
    def test_appended_at_the_end(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002"))
        roteiro = _criar(client, cid, ["ONE9001"])
        resp = client.post(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas",
            json={"codigo": "ONE9002"},
            headers=_auth(),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["ordem"] == 1

    def test_a_property_already_on_the_route_is_refused(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        resp = client.post(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas",
            json={"codigo": "one9001"},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text


class TestSoftDelete:
    def test_a_removed_roteiro_leaves_the_list(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        assert (
            client.delete(
                f"/api/clientes/{cid}/roteiros/{roteiro['id']}", headers=_auth()
            ).status_code
            == 204
        )
        assert client.get(f"/api/clientes/{cid}/roteiros", headers=_auth()).json() == {
            "items": [],
            "total": 0,
        }

    def test_a_removed_visita_leaves_the_count(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002"))
        roteiro = _criar(client, cid, ["ONE9001", "ONE9002"])
        client.delete(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas/"
            f"{roteiro['visitas'][0]['id']}",
            headers=_auth(),
        )
        contagem = client.get(f"/api/clientes/{cid}/roteiros", headers=_auth()).json()[
            "items"
        ][0]["contagem"]
        assert contagem["total"] == 1


class TestTimeline:
    """🔴 D3's memory leg — what an agent reads in 2028 to know what happened
    in 2024. Derived, never written: `timeline_service` has no insert path."""

    def _entries(self, client, cid) -> list[dict]:
        """NB the wire shape: `get_timeline` FLATTENS `payload` into the item
        (`**e["payload"]`), so the event fields are top-level here, not nested."""
        resp = client.get(
            f"/api/clientes/{cid}/timeline", params={"kinds": "visita"}, headers=_auth()
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["items"]

    def test_a_created_roteiro_appears_with_its_property_count(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001", "ONE9002"))
        _criar(client, cid, ["ONE9001", "ONE9002"], titulo="Terça de manhã")
        criado = [e for e in self._entries(client, cid) if e["evento"] == "roteiro_criado"]
        assert len(criado) == 1
        assert criado[0]["kind"] == "visita"
        assert criado[0]["imoveis"] == 2
        assert criado[0]["titulo"] == "Terça de manhã"

    def test_an_outcome_carries_the_codigo_and_the_observacao(self, client, scoped):
        """That sentence is the caution flag or the sales trigger someone reads
        back years later. It has to survive into the timeline."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        client.patch(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas/"
            f"{roteiro['visitas'][0]['id']}",
            json={"status": "nao_realizada", "observacao": "cliente desmarcou na porta"},
            headers=_auth(),
        )
        outcomes = [
            e for e in self._entries(client, cid) if e["evento"] == "visita_nao_realizada"
        ]
        assert len(outcomes) == 1
        assert outcomes[0]["codigo"] == "ONE9001"
        assert outcomes[0]["observacao"] == "cliente desmarcou na porta"

    def test_a_realizada_visita_is_a_distinct_event(self, client, scoped):
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        roteiro = _criar(client, cid, ["ONE9001"])
        client.patch(
            f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas/"
            f"{roteiro['visitas'][0]['id']}",
            json={"status": "realizada"},
            headers=_auth(),
        )
        assert {e["evento"] for e in self._entries(client, cid)} == {
            "roteiro_criado", "visita_realizada",
        }

    def test_a_pendente_visita_produces_no_entry(self, client, scoped):
        """`_gather_sistema`'s ruling on "restored", applied: an event with no
        honestly derivable timestamp is omitted, never stamped with now()."""
        cid, _ = _seed(scoped, codigos=("ONE9001",))
        _criar(client, cid, ["ONE9001"])
        assert {e["evento"] for e in self._entries(client, cid)} == {"roteiro_criado"}
