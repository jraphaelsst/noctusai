"""A profissão the operator TYPED is printed as typed (live deal 857, 2026-10-21:
"jogador de futebol", "autônoma" were blocked, both exactly what the signed
contract printed); a MACHINE-read one outside the vocabulary still blocks
("aposentanda"). All data is synthetic."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.card_hub.contrato_gerador import carregador, derivacao, profissoes
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(profissao, origem):
    d = fx.variante(1)
    v = replace(d.vendedores[0], profissao=profissao, profissao_origem=origem)
    d = replace(d, vendedores=[v] + list(d.vendedores[1:]))
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _campos(av):
    return [f["campo"] for f in av.faltando]


def test_manual_profession_outside_vocabulary_warns_never_blocks():
    av = _avaliar("cantor de ópera lírico", "manual")
    assert "qualificacao.profissao" not in _campos(av)
    assert "PROFISSAO_DIGITADA_FORA_DO_VOCABULARIO" in [a["codigo"] for a in av.avisos]


def test_machine_profession_outside_vocabulary_still_blocks():
    for origem in (None, "matricula", "documento"):
        av = _avaliar("aposentanda", origem)
        assert "qualificacao.profissao" in _campos(av)


def test_vocabulary_knows_the_deal_857_professions():
    for valor in ("jogador de futebol", "atleta profissional", "autônoma", "Autônomo"):
        assert profissoes.reconhecida(valor)


def test_loader_carries_profissao_origem():
    assert "profissao_origem" in carregador.Pessoa.__dataclass_fields__
