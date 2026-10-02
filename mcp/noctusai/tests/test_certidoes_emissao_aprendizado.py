"""Tests for ``noctus.dev.certidoes_emissao_aprendizado``.

Hermetic: ``FakeSqlExecutor`` stands in for the Management API and a tmp repo
root holds the sidecar + KB doc the sync mode regenerates. The classification is
the product's own ``aprendizado.py`` (loaded by path from THIS repo), so these
tests also pin that the tool and the product share one implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]

from tools.noctus.dev.certidoes_emissao_aprendizado import (  # noqa: E402
    BEGIN,
    END,
    KB_REL,
    SIDECAR_REL,
    certidoes_emissao_aprendizado,
)
from tools.noctus.dev.migrate_product import FakeSqlExecutor  # noqa: E402

PCEN = "Positiva com efeitos de negativa"


def _obs(id_, *, pref="nova", ok=False, ass="605|x|", fb=None, data_tipo=None, t="2026-09-01T10:00:00", price="0.24"):
    return {
        "id": id_, "org_id": "o", "tipo": "cnd_federal", "sucesso": ok, "assinatura": None if ok else ass,
        "preferencia_emissao": pref, "fallback_de": fb, "data_tipo": data_tipo, "documento_hash": "h",
        "created_at": t, "tentativa": 1, "code": 200 if ok else 605, "code_message": None,
        "errors": [], "price_brl": price, "billable": True, "validade": None,
    }


def _pcen_cases(n):
    out = []
    for i in range(n):
        out += [_obs(f"n{i}", t=f"2026-09-0{i + 1}T10:00:00"),
                _obs(f"v{i}", pref="2via", ok=True, fb=f"n{i}", data_tipo=PCEN, t=f"2026-09-0{i + 1}T10:00:01")]
    return out


def _executor(obs, eventos=()):
    return FakeSqlExecutor(preset_rows={
        "FROM social_wiring.certidao_emissao_observacoes": list(obs),
        "FROM social_wiring.certidao_emissao_aprendizados": list(eventos),
    })


def _evento(t="2026-09-05T12:00:00+00:00"):
    return {"org_id": "o", "tipo": "cnd_federal", "assinatura": "605|x|", "classe": "pcen",
            "classe_anterior": "desconhecida", "evidencia": {"pcen": 3, "transitoria": 0, "total": 3},
            "primeira_obs_em": "2026-09-01", "ultima_obs_em": "2026-09-03", "decidido_em": t}


def _tmp_root(tmp_path: Path) -> Path:
    """A repo root carrying the REAL aprendizado.py + a KB doc with the markers."""
    src = REPO_ROOT / "products/social-wiring/backend/app/modules/certidoes/aprendizado.py"
    dst = tmp_path / "products/social-wiring/backend/app/modules/certidoes/aprendizado.py"
    dst.parent.mkdir(parents=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    kb = tmp_path / KB_REL
    kb.parent.mkdir(parents=True)
    kb.write_text(f"# doc\n\n{BEGIN}\n_vazio_\n{END}\n\ntail\n", encoding="utf-8")
    return tmp_path


class TestReport:
    def test_report_e_somente_leitura_e_traz_o_relatorio(self, tmp_path):
        root = _tmp_root(tmp_path)
        ex = _executor(_pcen_cases(3), [_evento()])
        r = certidoes_emissao_aprendizado("report", executor=ex, repo_root=root)
        assert r["status"] == "ok" and r["observacoes"] == 6
        fed = r["relatorio"]["tipos"]["cnd_federal"]
        assert fed["chamadas"] == 6 and fed["assinaturas_de_falha"][0]["classe"] == "pcen"
        assert [n["classe"] for n in r["novos_aprendizados"]] == ["pcen"]
        assert r["wrote"] == [] and not (root / SIDECAR_REL).exists()
        assert all(s.lstrip().upper().startswith("SELECT") for s in ex.executed)

    def test_sem_credencial_e_not_configured_nunca_um_relatorio_vazio_falso(self, tmp_path, monkeypatch):
        from tools.noctus.dev import migrate_product
        monkeypatch.setattr(migrate_product, "make_sql_executor", lambda **_k: None)
        r = certidoes_emissao_aprendizado("report", repo_root=_tmp_root(tmp_path))
        assert r["status"] == "not_configured" and r["relatorio"] is None

    def test_falha_de_leitura_e_erro_tipado(self, tmp_path):
        ex = FakeSqlExecutor(fail_on={"certidao_emissao_observacoes"})
        r = certidoes_emissao_aprendizado("report", executor=ex, repo_root=_tmp_root(tmp_path))
        assert r["status"] == "error" and "observacoes" in r["error"]

    def test_modo_desconhecido_e_erro(self, tmp_path):
        assert certidoes_emissao_aprendizado("x", executor=_executor([]), repo_root=_tmp_root(tmp_path))["status"] == "error"

    def test_sem_dados_nao_quebra(self, tmp_path):
        r = certidoes_emissao_aprendizado("report", executor=_executor([]), repo_root=_tmp_root(tmp_path))
        assert r["status"] == "ok" and r["relatorio"]["tipos"] == {} and r["aprendizados_ate"] is None


class TestSync:
    def test_escreve_sidecar_e_secao_da_kb(self, tmp_path):
        root = _tmp_root(tmp_path)
        r = certidoes_emissao_aprendizado("sync", executor=_executor(_pcen_cases(3), [_evento()]), repo_root=root)
        assert r["status"] == "synced" and set(r["wrote"]) == {SIDECAR_REL, KB_REL}
        side = yaml.safe_load((root / SIDECAR_REL).read_text(encoding="utf-8"))
        assert side["aprendizados_ate"] == "2026-09-05T12:00:00+00:00"
        assert any(f.startswith("[observado] cnd_federal") for f in side["known_facts"])
        assert any("605|x|" in d["drift"] for d in side["drifts_surfaced"])
        kb = (root / KB_REL).read_text(encoding="utf-8")
        assert "`605|x|`" in kb and "pcen" in kb and kb.startswith("# doc") and kb.rstrip().endswith("tail")
        assert kb.count(BEGIN) == 1 and kb.count(END) == 1

    def test_e_idempotente_e_novos_aprendizados_zeram_depois(self, tmp_path):
        root = _tmp_root(tmp_path)
        ex = _executor(_pcen_cases(3), [_evento()])
        primeira = certidoes_emissao_aprendizado("sync", executor=ex, repo_root=root)
        assert primeira["changed"] is True and len(primeira["novos_aprendizados"]) == 1
        antes = {p: (root / p).read_text(encoding="utf-8") for p in (SIDECAR_REL, KB_REL)}
        segunda = certidoes_emissao_aprendizado("sync", executor=ex, repo_root=root)
        assert segunda["status"] == "unchanged" and segunda["changed"] is False and segunda["wrote"] == []
        assert segunda["novos_aprendizados"] == []
        assert {p: (root / p).read_text(encoding="utf-8") for p in antes} == antes

    def test_preserva_o_que_foi_escrito_a_mao_e_troca_so_o_observado(self, tmp_path):
        root = _tmp_root(tmp_path)
        side = root / SIDECAR_REL
        side.write_text(yaml.safe_dump({
            "artifact": "x", "known_facts": ["fato manual", "[observado] velho"],
            "alternatives_considered": [{"alt": "a", "rejected_because": "b"}],
        }), encoding="utf-8")
        certidoes_emissao_aprendizado("sync", executor=_executor(_pcen_cases(3), [_evento()]), repo_root=root)
        novo = yaml.safe_load(side.read_text(encoding="utf-8"))
        assert "fato manual" in novo["known_facts"] and "[observado] velho" not in novo["known_facts"]
        assert novo["alternatives_considered"] == [{"alt": "a", "rejected_because": "b"}]

    def test_um_aprendizado_novo_aparece_uma_vez(self, tmp_path):
        root = _tmp_root(tmp_path)
        certidoes_emissao_aprendizado("sync", executor=_executor(_pcen_cases(3), [_evento()]), repo_root=root)
        depois = certidoes_emissao_aprendizado(
            "report", executor=_executor(_pcen_cases(3), [_evento(), _evento("2026-09-20T00:00:00+00:00")]),
            repo_root=root)
        assert [n["decidido_em"] for n in depois["novos_aprendizados"]] == ["2026-09-20T00:00:00+00:00"]

    def test_kb_sem_marcadores_e_erro_nao_escrita_silenciosa(self, tmp_path):
        root = _tmp_root(tmp_path)
        (root / KB_REL).unlink()
        r = certidoes_emissao_aprendizado("sync", executor=_executor(_pcen_cases(3)), repo_root=root)
        assert r["status"] == "error" and not (root / SIDECAR_REL).exists()

    def test_kb_sem_marcador_ganha_a_secao_no_fim(self, tmp_path):
        root = _tmp_root(tmp_path)
        (root / KB_REL).write_text("# doc sem marcador\n", encoding="utf-8")
        certidoes_emissao_aprendizado("sync", executor=_executor(_pcen_cases(3)), repo_root=root)
        assert BEGIN in (root / KB_REL).read_text(encoding="utf-8")


class TestArtefatosReais:
    def test_a_doc_da_kb_carrega_os_marcadores_que_o_sync_precisa(self):
        kb = (REPO_ROOT / KB_REL).read_text(encoding="utf-8")
        assert kb.count(BEGIN) == 1 and kb.count(END) == 1 and kb.index(BEGIN) < kb.index(END)

    def test_o_sidecar_semente_e_yaml_valido_com_as_categorias(self):
        side = yaml.safe_load((REPO_ROOT / SIDECAR_REL).read_text(encoding="utf-8"))
        for campo in ("known_facts", "errors_encountered", "drifts_surfaced", "alternatives_considered",
                      "manual_validation_log", "bugs_fixed_during_dev"):
            assert campo in side
