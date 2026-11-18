"""The onboarding channel provisions and rotates its own social-wiring token: idempotent, rotated on expiry, fail-closed
with a named code, and the secret never leaves the store (status, events, errors, logs)."""
from __future__ import annotations

import dataclasses
import json
import logging
from datetime import timedelta

import pytest

from noctusai_lib.api.auth.session import hash_token

from app.onboarding.sw_canal import RENOVAR_ANTES, TTL, CanalErro, FakeSwCanal
from app.onboarding.sw_settings import SwSettingsStaffClient
from tests.onboarding.sw_canal_kit import NOW, ORG, SCOPE, STAFF, SW_URL, avancar, build_kit

import httpx


def _nenhum_segredo(texto: str, kit) -> None:
    for linha in kit.linhas():
        assert linha["token_hash"] not in texto  # a hash is not the secret, but must not travel either
    seg = kit.guardado()
    if seg:
        assert seg not in texto, "the token value leaked"


class TestProvisioning:
    def test_a_first_use_mints_probes_stores_and_records_without_any_human(self):
        kit = build_kit()
        segredo = kit.canal.garantir(ORG, STAFF)
        assert kit.guardado() == segredo and segredo.startswith("noc_")
        (linha,) = kit.linhas()
        assert linha["scopes"] == [SCOPE] and linha["issuer"] == "noctus-platform" and linha["org_id"] == str(ORG)
        assert linha["token_hash"] == hash_token(segredo)
        assert linha["expires_at"] == (NOW + TTL).isoformat()
        # probed BEFORE being stored, with the new token itself
        assert kit.seen == [("GET", "/api/julia/onboarding/whoami", segredo)]
        (ev,) = kit.eventos.itens
        assert (ev.evento, ev.ok, ev.ator, ev.expira_em) == ("sw_canal_provisionado", True, STAFF, NOW + TTL)

    def test_it_is_idempotent_a_valid_token_is_never_re_minted(self):
        kit = build_kit()
        a = kit.canal.garantir(ORG, STAFF)
        b = kit.canal.garantir(ORG, STAFF)
        assert a == b and len(kit.linhas()) == 1 and len(kit.eventos.itens) == 1

    def test_a_token_inside_the_renewal_window_is_rotated_and_the_old_one_revoked(self):
        kit = build_kit()
        velho = kit.canal.garantir(ORG, STAFF)
        avancar(kit, days=(TTL - RENOVAR_ANTES).days, hours=1)
        novo = kit.canal.garantir(ORG, STAFF)
        assert novo != velho and kit.guardado() == novo
        por_hash = {r["token_hash"]: r for r in kit.linhas()}
        assert por_hash[hash_token(velho)]["revoked_at"] and not por_hash[hash_token(novo)]["revoked_at"]
        assert [e.evento for e in kit.eventos.itens] == ["sw_canal_provisionado", "sw_canal_renovado"]

    def test_an_expired_token_is_replaced_on_its_next_use(self):
        kit = build_kit()
        velho = kit.canal.garantir(ORG, STAFF)
        avancar(kit, days=TTL.days + 1)
        assert kit.canal.status().estado == "expirado"
        novo = kit.canal.garantir(ORG, STAFF)
        assert novo != velho and kit.canal.status().estado == "provisionado"

    def test_a_token_revoked_or_deleted_at_social_wiring_is_replaced(self):
        kit = build_kit()
        velho = kit.canal.garantir(ORG, STAFF)
        kit.linhas().clear()  # deleted at the other end
        assert kit.canal.status().codigo == "token_nao_encontrado"
        novo = kit.canal.garantir(ORG, STAFF)
        assert novo != velho and kit.canal.status().estado == "provisionado"

    def test_an_unreadable_stored_value_is_replaced_not_served(self, monkeypatch):
        from noctusai_lib.security.app_config import AppConfigDecryptError

        kit = build_kit()
        kit.canal.garantir(ORG, STAFF)
        real_get = kit.store.get
        estado = {"quebrado": True}

        def get(key):
            if estado["quebrado"]:
                raise AppConfigDecryptError("x")
            return real_get(key)

        monkeypatch.setattr(kit.store, "get", get)
        assert kit.canal.status().codigo == "armazenamento_ilegivel"
        novo = kit.canal.garantir(ORG, STAFF)
        estado["quebrado"] = False
        assert kit.guardado() == novo


class TestFailsClosedWithNamedErrors:
    def test_a_new_token_the_wire_refuses_is_revoked_and_never_replaces_a_working_one(self):
        kit = build_kit()
        bom = kit.canal.garantir(ORG, STAFF)
        avancar(kit, days=TTL.days - 1)  # due for rotation
        kit.forcar["/api/julia/onboarding/whoami"] = 403
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert exc.value.codigo == "sw_forbidden" and "403" in exc.value.mensagem
        assert kit.guardado() == bom
        assert sum(1 for r in kit.linhas() if not r["revoked_at"]) == 1  # the failed mint was revoked
        assert kit.eventos.itens[-1].evento == "sw_canal_provisionamento_falhou" and not kit.eventos.itens[-1].ok

    def test_a_mint_failure_is_emissao_falhou_and_stores_nothing(self):
        kit = build_kit()
        kit.admin.fail_mint = True
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert exc.value.codigo == "emissao_falhou" and kit.guardado() is None

    def test_social_wiring_down_at_probe_time_is_unreachable_and_nothing_is_stored(self):
        kit = build_kit()
        kit.forcar["/api/julia/onboarding/whoami"] = 503
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert exc.value.codigo == "sw_unreachable" and kit.guardado() is None
        assert all(r["revoked_at"] for r in kit.linhas())

    def test_a_lookup_failure_never_mints_next_to_a_possibly_live_token(self, monkeypatch):
        kit = build_kit()
        kit.canal.garantir(ORG, STAFF)

        def quebra(schema, secret):
            raise RuntimeError("db down")

        monkeypatch.setattr(kit.admin, "find_by_secret", quebra)
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert exc.value.codigo == "sw_indisponivel" and len(kit.linhas()) == 1

    def test_a_non_persistent_store_in_a_deploy_context_refuses_by_name(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        kit = build_kit(persistent=False)
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert exc.value.codigo == "armazenamento_indisponivel" and kit.linhas() == []
        assert kit.canal.status().estado == "erro"

    def test_a_missing_social_wiring_url_is_a_named_failure_not_a_silent_skip(self):
        kit = build_kit()
        kit.canal._base_url = lambda: None
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert exc.value.codigo == "sw_error" and kit.guardado() is None


class TestStatus:
    def test_nothing_provisioned_is_ausente_and_status_never_provisions(self):
        kit = build_kit()
        s = kit.canal.status()
        assert (s.estado, s.escopo, s.emissor) == ("ausente", SCOPE, "noctus-platform")
        assert kit.linhas() == [] and kit.guardado() is None

    def test_provisioned_carries_expiry_and_days(self):
        kit = build_kit()
        kit.canal.garantir(ORG, STAFF)
        s = kit.canal.status()
        assert s.estado == "provisionado" and s.expira_em == NOW + TTL and s.dias_restantes == TTL.days
        # the provisioning probe against social-wiring is itself a successful call
        assert s.ultima_chamada_ok.evento == "sw_canal_provisionado" and s.ultimo_erro is None

    def test_a_revoked_token_is_a_named_error(self):
        kit = build_kit()
        kit.canal.garantir(ORG, STAFF)
        kit.linhas()[0]["revoked_at"] = NOW.isoformat()
        s = kit.canal.status()
        assert (s.estado, s.codigo) == ("erro", "token_revogado")

    def test_status_and_events_never_contain_the_secret(self):
        kit = build_kit()
        kit.canal.testar(ORG, STAFF)
        kit.canal.registrar_chamada(ok=False, codigo="sw_http_422", mensagem="recusado", ator=STAFF)
        texto = json.dumps(dataclasses.asdict(kit.canal.status()), default=str) + repr(kit.eventos.itens)
        _nenhum_segredo(texto, kit)


class TestTestarConexao:
    def test_success_records_the_test_and_shows_it_as_the_last_ok_call(self):
        kit = build_kit()
        teste, status = kit.canal.testar(ORG, STAFF)
        assert teste.ok and teste.codigo is None
        assert status.estado == "provisionado" and status.ultima_chamada_ok.evento == "sw_canal_conexao_testada"
        assert len(kit.seen) == 2  # the provisioning probe + the test itself, both read-only GETs
        assert all(m == "GET" for m, _, _ in kit.seen)

    def test_failure_is_reported_with_a_ptbr_reason_and_recorded(self):
        kit = build_kit()
        kit.canal.garantir(ORG, STAFF)
        kit.forcar["/api/julia/onboarding/whoami"] = 403
        teste, status = kit.canal.testar(ORG, STAFF)
        assert not teste.ok and teste.codigo == "sw_forbidden" and "escopo ou emissor" in teste.mensagem
        assert status.ultimo_erro.evento == "sw_canal_conexao_testada" and status.ultimo_erro.codigo == "sw_forbidden"

    def test_when_provisioning_fails_the_test_reports_that_reason(self):
        kit = build_kit()
        kit.admin.fail_mint = True
        teste, status = kit.canal.testar(ORG, STAFF)
        assert (teste.ok, teste.codigo) == (False, "emissao_falhou") and status.estado == "ausente"
        assert status.ultimo_erro.codigo == "emissao_falhou"

    def test_a_token_with_the_wrong_scope_or_issuer_is_rejected_by_the_wire(self):
        kit = build_kit()
        kit.canal.garantir(ORG, STAFF)
        kit.linhas()[0]["issuer"] = "agents"  # an org-issued token
        teste, _ = kit.canal.testar(ORG, STAFF)
        assert not teste.ok and teste.codigo == "sw_forbidden"  # the stub answered 403 issuer_not_allowed


class TestTokenNeverLeaks:
    def test_the_secret_is_only_in_the_authorization_header_never_in_a_url_or_a_log(self, caplog):
        caplog.set_level(logging.DEBUG)
        kit = build_kit()
        seg = kit.canal.garantir(ORG, STAFF)
        kit.forcar["/api/julia/onboarding/whoami"] = 403
        avancar(kit, days=TTL.days)
        with pytest.raises(CanalErro) as exc:
            kit.canal.garantir(ORG, STAFF)
        assert seg not in caplog.text and seg not in str(exc.value)
        novo = [b for _, _, b in kit.seen][-1]
        assert novo not in caplog.text and novo not in str(exc.value)

    def test_the_settings_client_reports_each_call_to_the_channel_and_refuses_by_name_when_unprovisioned(self):
        canal = FakeSwCanal("noc_x")
        porta = SwSettingsStaffClient(
            SW_URL, canal, transport=httpx.MockTransport(lambda r: httpx.Response(422, json={"code": "setting_nao_permitida"})))
        r = porta.aplicar(ORG, "pesquisa", None, {"pesquisa": True}, ator=STAFF)
        assert (r.ok, r.codigo) == (False, "setting_nao_permitida") and canal.chamadas == [(False, "setting_nao_permitida")]
        sem = FakeSwCanal(None)
        r = SwSettingsStaffClient(SW_URL, sem).aplicar(ORG, "pesquisa", None, {}, ator=STAFF)
        assert r.codigo == "canal_sw_nao_provisionado" and sem.chamadas == [(False, "canal_sw_nao_provisionado")]

    def test_a_real_channel_serves_the_apply_call_and_records_it(self):
        kit = build_kit()
        visto: list[httpx.Request] = []

        def sw(req):
            visto.append(req)
            return httpx.Response(200, json={"data": {}})

        porta = SwSettingsStaffClient(SW_URL, kit.canal.como(ORG, STAFF), transport=httpx.MockTransport(sw))
        r = porta.aplicar(ORG, "pesquisa", None, {"pesquisa": True}, ator=STAFF)
        assert r.ok and visto[0].headers["authorization"] == f"Bearer {kit.guardado()}"
        assert kit.eventos.ultimo(ok=True).evento == "sw_canal_chamada_concluida"
        assert [e.evento for e in kit.eventos.itens] == ["sw_canal_provisionado", "sw_canal_chamada_concluida"]
