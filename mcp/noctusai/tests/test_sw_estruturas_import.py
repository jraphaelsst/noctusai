"""``noctus.sw.estruturas_import`` — injected httpx.MockTransport, no network, SYNTHETIC files only (the real ones are vendor-derived)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.sw import estruturas_import as tool  # noqa: E402

TOKEN = "platform_admin_session_token_value"
SENTINELA = "ZZ-SENTINELA-TEXTO"
DOC = [{"corestudio_id": "1", "perfil": "criador", "formula_headline": f"{SENTINELA} fórmula", "formato": "reels", "objetivos": ["alcance"],
        "blocos": [{"ordem": 1, "nome_original": f"{SENTINELA} bloco", "nota": "", "repeticoes": 1, "tipo": "Headline", "tempo": "0–3s", "instrucao": f"{SENTINELA} i"}],
        "preenchido_por": "sintetico"}]
RELATORIO = {
    "id": "lote-1", "fonte": "referencia", "status": "simulada", "dry_run": True, "arquivo_sha256": tool.sha256_documento(DOC), "linhas_total": 1,
    "perfis_criados": 1, "perfis_mesclados": 0, "estruturas_criadas": 1, "estruturas_atualizadas": 0, "estruturas_inalteradas": 0,
    "estruturas_ignoradas": 0, "ignoradas_motivos": {}, "blocos_criados": 1, "campos_nao_importados": [], "erro": None,
    "created_at": "2026-11-15T00:00:00Z", "finished_at": "2026-11-15T00:00:01Z",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("NOCTUS_SW_TOKEN", TOKEN)
    monkeypatch.setenv("NOCTUS_SW_URL", "https://sw.test/")
    monkeypatch.setenv("NOCTUS_ESTRUTURAS_IMPORT_DIR", str(tmp_path))


@pytest.fixture
def arquivo(tmp_path):
    p = tmp_path / "estruturas-referencia.json"
    p.write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
    return p


def _t(handler):
    return httpx.MockTransport(handler)


def test_the_file_identity_matches_the_api_golden_vector():
    # the SAME literal pinned by test_estruturas_import_loader.py (backend): both sides hash the canonical JSON
    assert tool.sha256_documento({"é": [1, "x"]}) == "2a90a5462aab643e0a02f1e8d16cd4aa562a95741f31c6111be2f4bd591793dc"


def test_not_configured_and_bad_arguments_are_typed_errors(monkeypatch):
    assert tool.estruturas_import("status", fonte="x")["error"]["codigo"] == "fonte_invalida"
    assert tool.estruturas_import("nope")["error"]["codigo"] == "acao_invalida"
    monkeypatch.delenv("NOCTUS_SW_TOKEN")
    assert tool.estruturas_import("plan")["error"]["codigo"] == "nao_configurado"


def test_plan_posts_a_dry_run_with_the_parsed_document_and_returns_counts_only(arquivo):
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, json.loads(req.content), req.headers["authorization"]))
        return httpx.Response(200, json={"data": {**RELATORIO, "texto_do_vendor": SENTINELA}})

    out = tool.estruturas_import("plan", "referencia", _transport=_t(handler))
    method, path, corpo, auth = seen[0]
    assert (method, path) == ("POST", "/api/media-creation/estruturas/importacoes")
    assert corpo["dry_run"] is True and corpo["fonte"] == "referencia" and corpo["conteudo"] == DOC and corpo["arquivo_nome"] == "estruturas-referencia.json"
    assert auth == f"Bearer {TOKEN}"
    assert out["status"] == "planned" and out["sha256_confere"] is True and out["fechado"] is True
    assert out["relatorio"]["estruturas_criadas"] == 1 and "texto_do_vendor" not in out["relatorio"]
    assert SENTINELA not in json.dumps(out) and TOKEN not in json.dumps(out)


def test_plan_flags_a_server_sha_that_does_not_match_the_local_file(arquivo):
    out = tool.estruturas_import("plan", _transport=_t(lambda r: httpx.Response(200, json={"data": {**RELATORIO, "arquivo_sha256": "0" * 64}})))
    assert out["sha256_confere"] is False


def test_plan_flags_a_report_that_does_not_account_for_every_row(arquivo):
    out = tool.estruturas_import("plan", _transport=_t(lambda r: httpx.Response(200, json={"data": {**RELATORIO, "estruturas_criadas": 0}})))
    assert out["fechado"] is False


def test_apply_without_confirm_sends_nothing(arquivo):
    def handler(req):
        raise AssertionError("no request may be made")

    assert tool.estruturas_import("apply", _transport=_t(handler))["error"]["codigo"] == "confirmacao_obrigatoria"


def test_apply_with_confirm_posts_dry_run_false_and_returns_the_run_id(arquivo):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(202, json={"data": {"id": "lote-9", "status": "em_andamento"}})

    out = tool.estruturas_import("apply", confirm=True, _transport=_t(handler))
    assert seen[0]["dry_run"] is False and out == {"status": "em_andamento", "importacao_id": "lote-9", "proximo_passo": "action=status importacao_id=<id>"}


def test_the_server_refusal_without_a_simulation_is_passed_through_as_a_code(arquivo):
    out = tool.estruturas_import("apply", confirm=True, _transport=_t(lambda r: httpx.Response(
        409, json={"code": "simulacao_obrigatoria", "detail": "Rode a simulação deste arquivo antes de aplicar."})))
    assert out["error"]["codigo"] == "simulacao_obrigatoria" and out["error"]["http_status"] == 409


def test_a_nested_error_shape_and_a_403_are_typed_and_never_leak_the_token(arquivo):
    out = tool.estruturas_import("plan", _transport=_t(lambda r: httpx.Response(403, json={"error": {"code": "FORBIDDEN", "message": "restrito"}})))
    assert out["error"]["codigo"] == "FORBIDDEN" and out["error"]["http_status"] == 403 and TOKEN not in json.dumps(out)


def test_a_422_carries_the_motivo_code_and_no_server_text(arquivo):
    out = tool.estruturas_import("plan", _transport=_t(lambda r: httpx.Response(422, json={"code": "arquivo_invalido", "detail": f"{SENTINELA} eco", "motivo": "esperado_array"})))
    assert out["error"]["codigo"] == "arquivo_invalido" and out["error"]["motivo"] == "esperado_array" and SENTINELA not in json.dumps(out)


def test_status_polls_one_run_or_lists_the_latest(arquivo):
    paths = []

    def handler(req):
        paths.append(req.url.path)
        if req.url.path.endswith("lote-1"):
            return httpx.Response(200, json={"data": {**RELATORIO, "status": "concluida", "dry_run": False}})
        return httpx.Response(200, json={"data": {"items": [RELATORIO, RELATORIO], "total": 2}})

    um = tool.estruturas_import("status", importacao_id="lote-1", _transport=_t(handler))
    assert um["relatorio"]["status"] == "concluida"
    lista = tool.estruturas_import("status", _transport=_t(handler))
    assert len(lista["importacoes"]) == 2 and paths == ["/api/media-creation/estruturas/importacoes/lote-1", "/api/media-creation/estruturas/importacoes"]


def test_an_unreadable_file_reports_only_the_error_class(tmp_path):
    (tmp_path / "estruturas-referencia.json").write_text(f'{{"a": "{SENTINELA}" ', encoding="utf-8")
    out = tool.estruturas_import("plan")
    assert out["error"]["codigo"] == "arquivo_ilegivel" and SENTINELA not in json.dumps(out)


def test_a_missing_file_and_a_maquina_default_are_resolved(tmp_path, arquivo):
    assert tool.estruturas_import("plan", arquivo=str(tmp_path / "nao-existe.json"))["error"]["codigo"] == "arquivo_nao_encontrado"
    assert tool.estruturas_import("plan", "maquina_de_roteiros")["error"]["codigo"] == "arquivo_nao_encontrado"  # none in the dir
    (tmp_path / "maquina-de-roteiros-2026-11-15.json").write_text(json.dumps({"colecoes": {"perfis": [], "moldes": []}}), encoding="utf-8")
    seen = []
    tool.estruturas_import("plan", "maquina_de_roteiros", _transport=_t(lambda r: (seen.append(json.loads(r.content)), httpx.Response(200, json={"data": RELATORIO}))[1]))
    assert seen[0]["fonte"] == "maquina_de_roteiros" and seen[0]["arquivo_nome"] == "maquina-de-roteiros-2026-11-15.json"


def test_it_is_registered_in_the_sw_package():
    from tools.noctus import sw

    names = []

    class Srv:
        def tool(self, **kw):
            names.append(kw["name"])
            return lambda fn: fn

    sw.register_all(Srv())
    assert "noctus.sw.estruturas_import" in names


def test_the_tool_logs_no_row_text_and_no_token(arquivo, caplog):
    with caplog.at_level("DEBUG"):
        tool.estruturas_import("plan", _transport=_t(lambda r: httpx.Response(200, json={"data": RELATORIO})))
    # the tool has no logger of its own; the HTTP library's request line is method + URL + status (no body, no headers)
    assert all(r.name == "httpx" for r in caplog.records)
    assert SENTINELA not in caplog.text and TOKEN not in caplog.text
