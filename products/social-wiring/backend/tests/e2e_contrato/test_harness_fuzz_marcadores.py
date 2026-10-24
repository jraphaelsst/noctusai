"""Property/fuzz proof for the gap-marker render (`harness.dados_com_marcadores`
+ `renderizar_em_memoria(com_marcadores=True)`), the path `noctus.dev.
contract_score` takes for a NOT-`pronto` card.

Why a fuzz instead of a fix per incident: the generator `assert … # gated`s
inputs the readiness gate (`derivacao`) guarantees in PRODUCTION; a card that
is not `pronto` violates them by definition, so the marker render must supply
a stand-in for every one of them. For each `contrato_gerador` fixture variant
this blanks, ONE AT A TIME, every field of every dataclass in the card (and
drops every list element), then asserts:

1. the marker render never raises;
2. the harness changes ONLY fields it is declared to mark — a production-
   optional field (address complemento, intermediário representante, the
   registry-address override, the pendências prazo …) is never turned into a
   marker (it would invent a gap the real contract never has).

The inventory of `# gated` assertions (and the readiness rule behind each) is
in `KB § CONTEXT/PRODUCTS/social-wiring/CONTRACT-E2E-RUNBOOK.md` § 4.1.
"""
from __future__ import annotations

import dataclasses
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import harness  # noqa: E402

from tests.modules.card_hub import contrato_gerador_fixtures as fx  # noqa: E402

VARIANTES = range(1, 7)


def _cenarios() -> dict[str, Any]:
    """Every variant + the scenario builders that reach the gated branches the
    plain variants do not (PJ seller + representante, already-paid ônus, the
    split sinal, divisão, multi-imóvel permuta)."""
    from tests.modules.card_hub import contrato_gerador_fixtures_pagamentos as pag
    from tests.modules.card_hub import test_contrato_gerador_partes_clausulas as pc

    cenarios: dict[str, Any] = {f"v{n}": fx.variante(n) for n in VARIANTES}
    cenarios.update(
        pj_vendedora=pc._pj_vendedora(),
        onus_ja_quitado=pc._ja_quitado(),
        sinal_em_partes=pag.sinal_em_partes(),
        divisao_valor=pag.divisao_por_valor(),
        divisao_percentual=pag.divisao_por_percentual(),
        permuta_dois_imoveis=pag.permuta_dois_imoveis(),
        permuta_duas_parcelas=pag.permuta_duas_parcelas(),
        onus_boleto=pag.onus_por_boleto(),
    )
    return cenarios

#: Fields production prints conditionally / resolves from a fallback: blanking
#: one must NEVER make the harness mark it.
OPCIONAIS_PRODUCAO = frozenset(
    {
        "Endereco.complemento",
        "Imovel.endereco_registro_texto",
        "Intermediario.representante_nome",
        "Intermediario.representante_cpf",
        "Intermediario.representante_creci",
        "DadosContrato.prazo_pendencias_dias",
    }
)

#: What the harness may legitimately rewrite besides the per-type text map:
#: code/structural stand-ins (see `dados_com_marcadores`).
ESTRUTURAIS = frozenset(
    {
        "Pessoa.genero",
        "Parcela.valor",
        "DadosContrato.valor_negociado",
        "DadosContrato.parcelas",
        "DadosContrato.favorecidos",
        "DadosContrato.intermediarios",
        "Intermediario.favorecido_id",
        "Parcela.favorecido_id",
        "Parcela.divisao",
        "DivisaoFavorecido.favorecido_id",
        "DadosContrato.termos",
        "Termos.posse_data",
        "Termos.onus_baixa_protocolo_em",
        "DadosContrato.pessoas_juridicas",
        "DadosContrato.vendedores",
        "DadosContrato.compradores",
        "Matricula.atos",
        "Matricula.texto",
        "Imovel.onus_fonte_atos",
        "Imovel.numero_registro_imoveis",
    }
)


#: Cards with NO stand-in by design (nothing to render around): the render
#: raises and `pontuar_deal` reports `incompleto_sem_render`. Each is a
#: structural absence gated by a readiness `falta`/`bloqueio`
#: (`partes.*`, `negociacao.imovel`) or a dangling cross-reference
#: (`PERMUTA_IMOVEL_NAO_CARREGADO`) — never a missing VALUE. Anything else
#: raising is a missing stand-in and fails the fuzz.
SEM_RENDER = frozenset(
    {
        "DadosContrato.vendedores",  # no seller: no parte to qualify
        "DadosContrato.compradores",
        "-Pessoa[]",  # drops the only seller (first element)
        "Pessoa.papel",  # the seller stops being a proprietário/anuente
        "DadosContrato.imovel",  # negociacao.imovel
        "DadosContrato.permuta_imoveis",  # PERMUTA_IMOVEL_NAO_CARREGADO
        "-PermutaImovel[]",
        "PermutaImovel.permuta_ativo_id",
        "DadosContrato.partes_pj",  # the PJ was the only party of its side
        "-ParteJuridica[]",
        "ParteJuridica.lado",
    }
)


def _campos_permitidos() -> set[str]:
    permitido = set(ESTRUTURAIS)
    permitido |= {f"{c}.{f}" for c, f in harness.ENTRADAS_ESTRUTURAIS}
    permitido |= {"Imovel.endereco_registro_texto", "PermutaImovel.endereco_registro_texto"}
    for tipo, campos in harness.CAMPOS_MARCAVEIS_POR_TIPO.items():
        classe = tipo.split(".")[-1]
        permitido |= {f"{classe}.{c}" for c in campos}
    for c in harness.CAMPOS_DATA_MARCAVEIS:
        permitido |= {f"{cls}.{c}" for cls in ("Certidao", "CertidaoImovel", "PactoAntenupcial", "Pessoa")}
    return permitido


def _anulavel(valor: Any, anotacao: str) -> bool:
    """A scalar the loader can hand over as `None` only when declared Optional
    (a `None` where the type says `Decimal` is an invalid card, not a gap)."""
    if isinstance(valor, (str, bool, list, tuple)):
        return True
    return "Optional" in anotacao or "None" in anotacao


def _em_branco(valor: Any, anotacao: str) -> Any:
    if isinstance(valor, bool):
        return False
    if isinstance(valor, str):
        return None if "None" in anotacao or "Optional" in anotacao else ""
    if isinstance(valor, list):
        return []
    if isinstance(valor, tuple):
        return ()
    return None


def variacoes(obj: Any, vistos: set[str]) -> Iterator[tuple[str, Any]]:
    """Every single-field blanking / single-element drop inside `obj`, one
    `(label, mutated_obj)` per DISTINCT `Class.field` (first occurrence)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        classe = type(obj).__name__
        for f in dataclasses.fields(obj):
            valor = getattr(obj, f.name)
            rotulo = f"{classe}.{f.name}"
            if valor not in (None, "", [], ()) and rotulo not in vistos and _anulavel(valor, str(f.type)):
                vistos.add(rotulo)
                yield rotulo, dataclasses.replace(obj, **{f.name: _em_branco(valor, str(f.type))})
            for rot, novo in variacoes(valor, vistos):
                yield rot, dataclasses.replace(obj, **{f.name: novo})
    elif isinstance(obj, (list, tuple)):
        fabrica = type(obj) if type(obj) in (list, tuple) else None
        if fabrica is None:
            return
        for i, el in enumerate(obj):
            nome = type(el).__name__
            rotulo = f"-{nome}[]"
            if rotulo not in vistos and dataclasses.is_dataclass(el):
                vistos.add(rotulo)
                yield rotulo, fabrica(x for j, x in enumerate(obj) if j != i)
            for rot, novo in variacoes(el, vistos):
                yield rot, fabrica(novo if j == i else x for j, x in enumerate(obj))


def _alterados(antes: Any, depois: Any, saida: set[str]) -> None:
    if antes is depois:
        return
    if dataclasses.is_dataclass(antes) and not isinstance(antes, type):
        classe = type(antes).__name__
        for f in dataclasses.fields(antes):
            a, b = getattr(antes, f.name), getattr(depois, f.name)
            if a is b:
                continue
            if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
                for x, y in zip(a, b):
                    _alterados(x, y, saida)
            elif dataclasses.is_dataclass(a) and type(a) is type(b):
                _alterados(a, b, saida)
            elif a != b:
                saida.add(f"{classe}.{f.name}")


def _casos():
    for n, base in _cenarios().items():
        for rotulo, mutado in variacoes(base, set()):
            yield n, rotulo, mutado


def test_render_com_marcadores_nunca_levanta_nem_marca_opcional():
    permitido = _campos_permitidos()
    inicio = time.time()
    total = 0
    falhas: list[str] = []
    base_mudou: dict[str, set[str]] = {}
    for n, base in _cenarios().items():
        base_mudou[n] = set()
        _alterados(base, harness.dados_com_marcadores(base)[0], base_mudou[n])
    for n, rotulo, mutado in _casos():
        total += 1
        try:
            harness.contexto_em_memoria(mutado, com_marcadores=True)
            marcado, _ = harness.dados_com_marcadores(mutado)
        except Exception as exc:  # noqa: BLE001 — collected, reported below
            if rotulo in SEM_RENDER:
                continue
            falhas.append(f"{n} {rotulo}: {type(exc).__name__}: {exc}"[:200])
            continue
        mudou: set[str] = set()
        _alterados(mutado, marcado, mudou)
        mudou -= base_mudou[n] - {rotulo}
        if rotulo in OPCIONAIS_PRODUCAO and rotulo in mudou:
            falhas.append(f"{n} {rotulo}: production-optional field was turned into a marker")
        indevidos = {c for c in mudou - permitido if not c.endswith("_dias")}
        if indevidos:
            falhas.append(f"{n} {rotulo}: harness rewrote undeclared fields {sorted(indevidos)}")
    assert total > 100, f"fuzz generated only {total} cases — walker is broken"
    assert not falhas, "\n".join(falhas)
    assert time.time() - inicio < 60


@pytest.mark.parametrize("campo", sorted(OPCIONAIS_PRODUCAO))
def test_opcional_de_producao_declarado_existe(campo):
    """The optional list names real fields (a rename must not silently disarm the fuzz)."""
    classe, nome = campo.split(".")
    from app.modules.card_hub.contrato_gerador import dados as modulo

    assert nome in {f.name for f in dataclasses.fields(getattr(modulo, classe))}
