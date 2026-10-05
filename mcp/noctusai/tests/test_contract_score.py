"""Tests for `noctus.dev.contract_score` — reference resolution, the private
request/scorecard handling, and the verdict-only return contract. The live
render (`harness.py --lote`) is the subprocess behind the `runner` DI seam;
here it is a fake runner (no database). Every value is invented.

WHAT THESE PIN
--------------
- a deal with no answer key / non-ok key / missing mirror / missing text is
  SKIPPED with a named reason — never guessed at;
- the reference paragraphs come from the answer key's own `fonte.arquivo`
  via the mirror manifest + the extract-once cache;
- the request file (it carries reference text) is 0600 while the harness
  runs and deleted afterwards — even when the harness fails;
- the return payload is re-filtered: a value the harness might leak (a name,
  a CPF, free text in a code field) never reaches the caller;
- a harness failure returns only the exception CLASS, never its message.
"""
from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import contract_score as cs  # noqa: E402

WORKTREE = str(Path(__file__).resolve().parents[3])
CPF_FAKE = "111.444.777-35"


@pytest.fixture()
def private(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setenv("NOCTUS_PRIVATE_DIR", str(root))
    return root


def _plantar_deal(private: Path, numero: str, *, status: str = "ok", texto: str | None = None) -> None:
    pasta = f"pasta{numero}"
    sha = f"sha{numero}"
    (private / "answer-keys").mkdir(parents=True, exist_ok=True)
    (private / "answer-keys" / f"{numero}.json").write_text(
        json.dumps({"status": status, "folder": {"drive_folder_id": pasta}, "fonte": {"arquivo": "CONTRATO.docx"}}),
        encoding="utf-8",
    )
    (private / "drive-mirror" / pasta).mkdir(parents=True, exist_ok=True)
    (private / "drive-mirror" / pasta / "manifest.json").write_text(
        json.dumps({"entries": [{"rel_path": "CONTRATO.docx", "sha256": sha}]}), encoding="utf-8"
    )
    if texto is not None:
        (private / "extractions").mkdir(parents=True, exist_ok=True)
        (private / "extractions" / f"{sha}.json").write_text(
            json.dumps({"text_source": "docx", "text": texto, "error": None}), encoding="utf-8"
        )


def _cards(private: Path, numeros: list[str]) -> str:
    caminho = private / "cards.json"
    caminho.write_text(json.dumps({n: {"cliente_id": f"00000000-0000-0000-0000-00000000000{i}", "atendimento_id": "x"} for i, n in enumerate(numeros)}), encoding="utf-8")
    return str(caminho)


class _Runner:
    def __init__(self, deals_out: dict, returncode: int = 0, stderr: str = ""):
        self.deals_out = deals_out
        self.returncode = returncode
        self.stderr = stderr
        self.chamadas: list[dict] = []

    def __call__(self, cmd, **kw):
        pedido_path = Path(cmd[cmd.index("--lote") + 1])
        modo = stat.S_IMODE(pedido_path.stat().st_mode)
        pedido = json.loads(pedido_path.read_text(encoding="utf-8"))
        self.chamadas.append({"cmd": cmd, "kw": kw, "modo": modo, "pedido": pedido})
        saida = {"total": {"limiares": {"redacao_min": 0.9}, "allowlist_entradas": 0, "allowlist_aprovadas": 0},
                 "deals": self.deals_out}
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=json.dumps(saida) + "\n", stderr=self.stderr)


def test_resolve_referencia_e_pula_sem_fonte(private):
    _plantar_deal(private, "101", texto="CLÁUSULA PRIMEIRA – DO OBJETO\nTexto do objeto.")
    _plantar_deal(private, "102", status="sem_contrato")
    _plantar_deal(private, "103", texto=None)  # mirrored, never extracted
    runner = _Runner({"101": {"veredito": "aprovado", "motivos": [], "numeros_divergentes": 0}})
    out = cs.contract_score(cards_path=_cards(private, ["101", "102", "103", "104"]), worktree_path=WORKTREE, runner=runner)
    assert out["status"] == "ok"
    assert {p["numero"]: p["motivo"] for p in out["deals_skipped"]} == {
        "102": "answer_key_status_sem_contrato",
        "103": "sem_texto_extraido",
        "104": "sem_answer_key",
    }
    (chamada,) = runner.chamadas
    assert [d["numero"] for d in chamada["pedido"]["deals"]] == ["101"]
    assert chamada["pedido"]["deals"][0]["ref_paragrafos"] == ["CLÁUSULA PRIMEIRA – DO OBJETO", "Texto do objeto."]
    assert chamada["modo"] == 0o600
    assert chamada["kw"]["cwd"].endswith("products/social-wiring/backend")
    assert out["verdict"] == "pass" and out["aprovados"] == 1 and out["taxa_aprovacao"] == 1.0


def test_pedido_privado_apagado_mesmo_em_falha(private):
    _plantar_deal(private, "101", texto="Texto.")
    runner = _Runner({}, returncode=1, stderr=f"Traceback ...\nValueError: CPF {CPF_FAKE} inválido para FULANO")
    out = cs.contract_score(cards_path=_cards(private, ["101"]), worktree_path=WORKTREE, runner=runner)
    assert out["status"] == "error"
    assert out["error"] == "harness exit 1 (ValueError)"
    assert CPF_FAKE not in json.dumps(out) and "FULANO" not in json.dumps(out)
    assert not list((private / "scores").glob(".pedido-*"))


def test_retorno_filtra_qualquer_valor_vazado(private):
    _plantar_deal(private, "101", texto="Texto.")
    vazado = {
        "veredito": "reprovado",
        "motivos": ["numeros_divergentes:2", f"cpf {CPF_FAKE}"],
        "numeros_divergentes": 2,
        "categorias": {"redacao": 0.91234, "FULANO DE TAL": 1.0},
        "render_erro": f"KeyError: '{CPF_FAKE}'",
        "nome": "FULANO DE TAL",
        "gaps": {"faltando": 3, "pronto": False, "cpf": CPF_FAKE},
        "detalhe_texto": "o valor é R$ 500.000,00",
    }
    out = cs.contract_score(cards_path=_cards(private, ["101"]), worktree_path=WORKTREE, runner=_Runner({"101": vazado}))
    texto = json.dumps(out, ensure_ascii=False)
    for valor in (CPF_FAKE, "FULANO", "500.000"):
        assert valor not in texto
    deal = out["deals"]["101"]
    assert deal["motivos"] == ["numeros_divergentes:2"]
    assert deal["categorias"] == {"redacao": 0.9123}
    assert deal["gaps"] == {"faltando": 3, "pronto": False}
    assert "render_erro" not in deal
    assert out["verdict"] == "fail"


def test_contadores_de_lacuna_e_nao_fato_passam_o_filtro(private):
    """The honest-comparison counters (gaps / aligned / unavailable / re-issued)
    are numbers — they ride the whitelist so the owner sees them next to the
    divergence count; a value-shaped extra next to them still does not."""
    _plantar_deal(private, "101", texto="Texto.")
    resumo = {
        "veredito": "incompleto", "numeros_divergentes": 3, "datas_divergentes": 1,
        "numeros_alinhados": 4, "datas_alinhadas": 1, "dados_indisponiveis": 5, "assinatura_excluidos": 6,
        "certidoes_lacuna": 7, "certidoes_extras": 2, "certidoes_reemitidas": 8, "valor_vazado": CPF_FAKE,
    }
    out = cs.contract_score(cards_path=_cards(private, ["101"]), worktree_path=WORKTREE, runner=_Runner({"101": resumo}))
    deal = out["deals"]["101"]
    for chave in ("numeros_alinhados", "datas_alinhadas", "dados_indisponiveis", "assinatura_excluidos",
                  "certidoes_lacuna", "certidoes_extras", "certidoes_reemitidas"):
        assert deal[chave] == resumo[chave]
    assert CPF_FAKE not in json.dumps(out)


def test_numeros_filtra_e_sem_deals(private):
    out = cs.contract_score(cards=[{"numero": "9", "cliente_id": "x"}], numeros=["8"], worktree_path=WORKTREE, runner=_Runner({}))
    assert out == {"status": "no_deals", "deals": {}, "deals_skipped": []}


def test_cards_ausente_e_erro_nomeado(private):
    out = cs.contract_score(cards_path=str(private / "nada.json"), worktree_path=WORKTREE, runner=_Runner({}))
    assert out["status"] == "error" and "cards file not found" in out["error"]


def test_limiares_e_allowlist_repassados(private):
    _plantar_deal(private, "101", texto="Texto.")
    runner = _Runner({"101": {"veredito": "aprovado"}})
    cs.contract_score(
        cards_path=_cards(private, ["101"]), worktree_path=WORKTREE, runner=runner,
        limiares={"redacao_min": 0.8}, allowlist_path="/tmp/allow.json",
    )
    pedido = runner.chamadas[0]["pedido"]
    assert pedido["limiares"] == {"redacao_min": 0.8}
    assert pedido["allowlist"] == "/tmp/allow.json"
    assert pedido["org_id"] == cs.SW_ORG_ID
