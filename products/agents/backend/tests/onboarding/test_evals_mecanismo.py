"""Replays the mechanism suite of ``onboarding-imob`` (``projects/onboarding/agent/onboarding-imob-evals-mecanismo.json``)
against the real tool logic. One test per case; the file is the single source of the cases (no copy in code)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .test_entrevista import Kit

ROOT = Path(__file__).resolve().parents[3]
ARQUIVO = ROOT / "projects/onboarding/agent/onboarding-imob-evals-mecanismo.json"
CASOS = json.loads(ARQUIVO.read_text())["casos"]
COMPORTAMENTO = json.loads((ROOT / "projects/onboarding/agent/onboarding-imob-evals-comportamento.json").read_text())["itens"]


def _chama(kit: Kit, ferramenta: str, args: dict) -> dict:
    e = kit.e
    if ferramenta == "progresso_onboarding":
        return e.progresso()
    if ferramenta == "registrar_resposta":
        return e.registrar_resposta(**{**{"valor": None, "trecho": None, "origem": "cliente", "motivo": None}, **args})
    if ferramenta == "importar_configuracao":
        return e.importar_configuracao(texto=args["texto"])
    if ferramenta == "revisar_e_aplicar":
        return e.revisar_e_aplicar(fase=args.get("fase"), confirmacao_cliente=args.get("confirmacao_cliente"))
    raise AssertionError(f"ferramenta desconhecida no caso: {ferramenta}")


def _confere(out: dict, espera: dict) -> None:
    for k, v in espera.items():
        if k == "proximo_n":
            assert out["proximo"]["n"] == v
        elif k == "propostas":
            assert len(out["propostas"]) == v
        elif k.startswith("contagem_"):
            assert out["contagem"][k.removeprefix("contagem_")] == v
        elif k == "faltando_inclui":
            assert v in out["faltando_obrigatorios"]
        else:
            assert out.get(k) == v, f"{k}: {out.get(k)!r} != {v!r} ({out})"


@pytest.mark.parametrize("caso", CASOS, ids=[c["slug"] for c in CASOS])
def test_caso_de_mecanismo(caso):
    kit = Kit()
    for passo in caso["passos"]:
        if "fala" in passo:
            kit.diz(passo["fala"])
            continue
        c = passo["chama"]
        _confere(_chama(kit, c["ferramenta"], c["args"]), passo["espera"])
    escritas = {k for w in kit.spec_writes for k in w}
    assert escritas == set(caso.get("escritas_no_fim", [])), f"gravou {escritas}"


def test_the_suites_meet_the_floor_and_the_canonical_must_haves():
    assert len(CASOS) >= 10 and len(COMPORTAMENTO) >= 10
    slugs = [c["slug"] for c in COMPORTAMENTO]
    assert len(set(slugs)) == len(slugs)
    assert sum("bajulacao" in c["tags"] for c in COMPORTAMENTO) >= 2  # canonical must-have (canonical-agent-template)
    assert all(c["criterios"]["deve"] and c["criterios"]["nao_deve"] for c in COMPORTAMENTO)


def test_the_section_rows_carry_the_canonical_rule_and_stay_in_step_with_the_tools():
    from app.studio.ferramentas_registry import ONBOARDING_FERRAMENTAS

    secoes = json.loads((ROOT / "projects/onboarding/agent/onboarding-imob-secoes.json").read_text())["secoes"]
    assert any("discordar-com-respeito" in (s.get("regras") or []) for s in secoes)
    rows = json.loads((ROOT / "projects/onboarding/agent/onboarding-imob-ferramentas.json").read_text())["itens"]
    assert {r["ferramenta"] for r in rows} == {f"onboarding_{n}" for n in ONBOARDING_FERRAMENTAS}
    assert all(r["descricao"].strip() for r in rows)
    texto = " ".join(s["conteudo"] for s in secoes)
    assert all(n in texto for n in ("progresso_onboarding", "registrar_resposta", "importar_configuracao", "revisar_e_aplicar"))
