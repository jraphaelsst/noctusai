"""Act-pointer rebinding noise (divergence-email study, 2026-10-05): a new
matrícula extraction mints new act UUIDs for the SAME acts. `titulo_aquisitivo`
/ `onus_fonte` compare by the stable act key (kind, numero) — or char-range
overlap when unnumbered — so a rebind never opens a conflict, never emails."""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, dados_row, seed

ORG = UUID(ORG_ID)


def _atos(scoped, eid, specs):
    """specs: [(kind, numero, ini, fim)] -> ids; ADDs to matricula_atos."""
    existentes = scoped.table("matricula_atos").select("*").execute().data or []
    novos, ids = [], []
    for ordem, (kind, numero, ini, fim) in enumerate(specs):
        i = str(uuid4())
        ids.append(i)
        novos.append({"id": i, "org_id": ORG_ID, "extracao_id": eid, "ordem": ordem,
                      "kind": kind, "numero": numero, "char_inicio": ini, "char_fim": fim})
    scoped.set_table_data("matricula_atos", existentes + novos)
    return ids


def _dados(scoped):
    return [r for r in scoped.table("imovel_dados").select("*").execute().data
            if r["codigo"] == CODIGO][0]


def _conflitos(scoped):
    return scoped.table("imovel_campo_conflitos").select("*").execute().data


def _titulo(eid, ato, ini, fim):
    return {"titulo_aquisitivo_extracao_id": eid, "titulo_aquisitivo_ato_id": ato,
            "titulo_aquisitivo_char_inicio": ini, "titulo_aquisitivo_char_fim": fim}


def _onus(eid, atos):
    return {"onus_fonte_extracao_id": eid,
            "onus_fonte_atos": [{"ato_id": a, "char_inicio": i, "char_fim": f} for a, i, f in atos]}


def test_titulo_rebind_to_same_act_moves_pointer_keeps_confirmation(scoped):
    e1, e2 = str(uuid4()), str(uuid4())
    [a1] = _atos(scoped, e1, [("R", 4, 3353, 4350)])
    [a2] = _atos(scoped, e2, [("R", 4, 3299, 4294)])
    humano = str(uuid4())
    seed(scoped, dados=[dados_row(
        **_titulo(e1, a1, 3353, 4350),
        titulo_aquisitivo_origem="sugerido",
        titulo_aquisitivo_confirmado_por=humano,
        titulo_aquisitivo_confirmado_em="2026-09-20T00:00:00+00:00",
    )])
    scoped.set_table_data("matricula_atos", scoped.table("matricula_atos").select("*").execute().data)
    r = campos_svc.aplicar(scoped, ORG, CODIGO, "titulo_aquisitivo",
                           _titulo(e2, a2, 3299, 4294), origem="sugerido")
    assert r.status == campos_svc.REAPONTADO and r.conflito is None
    row = _dados(scoped)
    assert row["titulo_aquisitivo_extracao_id"] == e2
    assert row["titulo_aquisitivo_ato_id"] == a2
    assert row["titulo_aquisitivo_confirmado_por"] == humano
    assert row["titulo_aquisitivo_confirmado_em"]
    assert _conflitos(scoped) == []


def test_chained_rebinds_never_conflict(scoped):
    e = [str(uuid4()) for _ in range(3)]
    ids = [_atos(scoped, x, [("AV", 3, 100 + i, 200 + i)])[0] for i, x in enumerate(e)]
    seed(scoped, dados=[dados_row(
        **_titulo(e[0], ids[0], 100, 200), titulo_aquisitivo_origem="manual")])
    for i in (1, 2):
        r = campos_svc.aplicar(scoped, ORG, CODIGO, "titulo_aquisitivo",
                               _titulo(e[i], ids[i], 100 + i, 200 + i), origem="sugerido")
        assert r.status == campos_svc.REAPONTADO
    assert _dados(scoped)["titulo_aquisitivo_ato_id"] == ids[2]
    assert _dados(scoped)["titulo_aquisitivo_origem"] == "manual"
    assert _conflitos(scoped) == []


def test_unnumbered_acts_match_by_char_overlap(scoped):
    e1, e2 = str(uuid4()), str(uuid4())
    [a1] = _atos(scoped, e1, [("R", None, 3353, 4350)])
    [a2] = _atos(scoped, e2, [("R", None, 3299, 4294)])
    seed(scoped, dados=[dados_row(**_titulo(e1, a1, 3353, 4350), titulo_aquisitivo_origem="manual")])
    r = campos_svc.aplicar(scoped, ORG, CODIGO, "titulo_aquisitivo",
                           _titulo(e2, a2, 3299, 4294), origem="sugerido")
    assert r.status == campos_svc.REAPONTADO


def test_unconfirmed_sugerido_with_changed_acts_is_replaced_silently(scoped):
    e1, e2 = str(uuid4()), str(uuid4())
    [a1] = _atos(scoped, e1, [("R", 5, 10, 90)])
    [a2] = _atos(scoped, e2, [("R", 9, 10, 90)])
    seed(scoped, dados=[dados_row(**_titulo(e1, a1, 10, 90), titulo_aquisitivo_origem="sugerido")])
    r = campos_svc.aplicar(scoped, ORG, CODIGO, "titulo_aquisitivo",
                           _titulo(e2, a2, 10, 90), origem="sugerido")
    assert r.status == campos_svc.RELEITURA
    assert _dados(scoped)["titulo_aquisitivo_ato_id"] == a2
    assert _conflitos(scoped) == []


def test_confirmed_titulo_with_changed_act_conflicts_and_email_shows_labels(scoped):
    e1, e2 = str(uuid4()), str(uuid4())
    [a1] = _atos(scoped, e1, [("R", 5, 10, 90)])
    [a2] = _atos(scoped, e2, [("R", 9, 10, 90)])
    seed(scoped, dados=[dados_row(
        **_titulo(e1, a1, 10, 90), titulo_aquisitivo_origem="sugerido",
        titulo_aquisitivo_confirmado_em="2026-09-20T00:00:00+00:00",
        titulo_aquisitivo_confirmado_por=str(uuid4()))])
    r = campos_svc.aplicar(scoped, ORG, CODIGO, "titulo_aquisitivo",
                           _titulo(e2, a2, 10, 90), origem="sugerido")
    assert r.status == campos_svc.CONFLITO
    assert _dados(scoped)["titulo_aquisitivo_ato_id"] == a1

    visto = []

    class N:
        async def notify_imovel_field_conflict(self, *, org_id, conflito, codigo):
            visto.append(conflito)

    asyncio.run(campos_svc.notificar(scoped, ORG, CODIGO, [r.conflito], N()))
    assert visto[0]["valor_anterior"] == "atos: R-5"
    assert visto[0]["valor_proposto"] == "atos: R-9"
    assert a1 not in str(visto[0]["valor_anterior"])


def test_onus_same_set_rebinds_but_changed_set_conflicts_when_confirmed(scoped):
    e1, e2, e3 = str(uuid4()), str(uuid4()), str(uuid4())
    a1 = _atos(scoped, e1, [("R", 3, 10, 50), ("AV", 4, 60, 90)])
    a2 = _atos(scoped, e2, [("AV", 4, 61, 91), ("R", 3, 11, 51)])
    a3 = _atos(scoped, e3, [("R", 3, 11, 51)])
    seed(scoped, dados=[dados_row(
        **_onus(e1, [(a1[0], 10, 50), (a1[1], 60, 90)]), onus_fonte_origem="sugerido",
        onus_fonte_confirmado_em="2026-09-20T00:00:00+00:00",
        onus_fonte_confirmado_por=str(uuid4()))])
    r = campos_svc.aplicar(scoped, ORG, CODIGO, "onus_fonte",
                           _onus(e2, [(a2[0], 61, 91), (a2[1], 11, 51)]), origem="sugerido")
    assert r.status == campos_svc.REAPONTADO
    assert _dados(scoped)["onus_fonte_extracao_id"] == e2
    assert _dados(scoped)["onus_fonte_confirmado_em"]
    r2 = campos_svc.aplicar(scoped, ORG, CODIGO, "onus_fonte",
                            _onus(e3, [(a3[0], 11, 51)]), origem="sugerido")
    assert r2.status == campos_svc.CONFLITO
