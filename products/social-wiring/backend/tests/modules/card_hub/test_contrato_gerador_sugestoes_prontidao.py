"""`faltando[].sugestao` -- a pending document reading rides on its falta."""
from types import SimpleNamespace

from app.modules.card_hub.contrato_gerador.sugestoes_prontidao import anexar_sugestoes

TITULAR = "11111111-1111-1111-1111-111111111111"
PARTE_CID = "22222222-2222-2222-2222-222222222222"


def _dados():
    return SimpleNamespace(
        vendedores=[SimpleNamespace(parte_id=None, cliente_id=TITULAR)],
        compradores=[SimpleNamespace(parte_id="p1", cliente_id=PARTE_CID)],
    )


def _sug(**kw):
    base = {
        "valor": "Masculino", "documento_id": "d1", "documento_nome": "cert.pdf",
        "tipo_documento": "certidao_casamento", "confianca": "media",
        "leitura_comprometida": False,
    }
    return {**base, **kw}


def _falta(campo, parte_id=None, onde="partes"):
    return {"campo": campo, "rotulo": "x", "onde": onde, "parte_id": parte_id}


def test_titular_falta_carries_pending_suggestion():
    fs = [_falta("qualificacao.genero")]
    anexar_sugestoes(_dados(), fs, lambda cid: {"genero": _sug()} if cid == TITULAR else {})
    assert fs[0]["sugestao"] == {
        "cliente_id": TITULAR, "item_key": "genero", "documento_id": "d1",
        "documento_nome": "cert.pdf", "tipo_documento": "certidao_casamento",
        "valor": "Masculino", "confianca": "media",
    }


def test_any_identity_field_uses_same_mechanism_and_parte_maps_to_its_cliente():
    fs = [_falta("qualificacao.profissao", "p1")]
    anexar_sugestoes(_dados(), fs, lambda cid: {"profissao": _sug(valor="Engenheiro")} if cid == PARTE_CID else {})
    assert fs[0]["sugestao"]["cliente_id"] == PARTE_CID
    assert fs[0]["sugestao"]["valor"] == "Engenheiro"


def test_no_suggestion_when_absent_compromised_or_not_a_qualificacao_falta():
    fs = [
        _falta("qualificacao.genero"),
        _falta("qualificacao.nacionalidade"),
        _falta("negociacao.preco", onde="negociacao"),
    ]
    anexar_sugestoes(
        _dados(), fs,
        lambda cid: {"genero": _sug(leitura_comprometida=True)},
    )
    assert all("sugestao" not in f for f in fs)
