"""Julia v2 A-RT2 small fixes: the 422 never echoes input; the standard router answers fixed texts; the leak
detector's shingle length is per-rule data."""
from __future__ import annotations

from uuid import uuid4

from app.channels import conformidade as conf
from app.stores.conformidade import FakeConformidadeStore, RegraConfig


class TestValidationNeverEchoesInput:
    SEGREDO = "SEGREDO-NAO-ECOAR-123"

    def test_the_handler_builds_messages_from_the_error_type_only(self):
        import asyncio

        from fastapi.exceptions import RequestValidationError

        from app.validation import request_validation_handler

        exc = RequestValidationError([{
            "type": "value_error", "loc": ("body", "campo"), "msg": f"Value error, {self.SEGREDO}",
            "input": self.SEGREDO, "ctx": {"error": ValueError(self.SEGREDO)},
        }, {
            "type": "string_too_short", "loc": ("body", "nome"), "msg": "String should have at least 3 characters",
            "input": self.SEGREDO, "ctx": {"min_length": 3},
        }])
        resp = asyncio.run(request_validation_handler(None, exc))
        body = resp.body.decode()
        assert resp.status_code == 422 and self.SEGREDO not in body
        assert '"field":"campo"' in body.replace(" ", "") and '"type":"string_too_short"' in body.replace(" ", "")

    def test_the_app_registers_it(self):
        from fastapi.exceptions import RequestValidationError

        from app.main import app
        from app.validation import request_validation_handler

        assert app.exception_handlers[RequestValidationError] is request_validation_handler


class TestQualificacaoRouterFixedTexts:
    def test_a_value_error_from_the_store_is_a_fixed_text(self):
        from fastapi import HTTPException

        from app.routers.qualificacao_router import _Mapped

        import pytest

        for exc, status in ((ValueError("critério 'segredo_x' peso 99 inválido"), 422),):
            with pytest.raises(HTTPException) as info:
                with _Mapped():
                    raise exc
            assert info.value.status_code == status
            assert "segredo_x" not in str(info.value.detail) and info.value.detail["code"] == "invalid_field"

    def test_not_found_and_conflict_do_not_echo_the_exception_text(self):
        import pytest
        from fastapi import HTTPException

        from app.routers.qualificacao_router import _Mapped
        from app.stores._db_errors import StudioConflict
        from app.stores.errors import NotFound

        for exc in (NotFound("padrao 'imob-lead' criterio 'preco'"), StudioConflict("key_taken", "chave 'segredo'")):
            with pytest.raises(HTTPException) as info:
                with _Mapped():
                    raise exc
            assert "imob-lead" not in str(info.value.detail) and "segredo" not in str(info.value.detail)


class TestShingleLengthPerRule:
    def test_default_when_unset_or_invalid(self):
        assert conf.shingle_tokens_da_regra(None) == conf.SHINGLE_TOKENS
        assert conf.shingle_tokens_da_regra(RegraConfig("vazamento_prompt")) == conf.SHINGLE_TOKENS
        for ruim in (3, 65, "20", True, 12.5):
            assert conf.shingle_tokens_da_regra(
                RegraConfig("vazamento_prompt", parametros={"shingle_tokens": ruim})) == conf.SHINGLE_TOKENS
        assert conf.shingle_tokens_da_regra(
            RegraConfig("vazamento_prompt", parametros={"shingle_tokens": 24})) == 24

    # a 15-token mandatory disclosure that the prompt contains and every reply must repeat
    DIVULGACAO = "sou uma assistente virtual de inteligencia artificial e posso encaminhar voce para um corretor"

    class _Compiled:
        def __init__(self, texto: str) -> None:
            self.texto = texto
            self.conteudo = None

    def _imp(self, store, org, version, k):
        prompt = self._Compiled(f"Regra um. {self.DIVULGACAO}. Fim das regras internas do atendimento privado que ninguem alem da equipe da plataforma deve ler jamais.")
        return conf.garantir_impressao(store, org, version, prompt, k)

    def test_a_longer_window_stops_the_disclosure_from_self_triggering(self):
        store, org, ver = FakeConformidadeStore(), uuid4(), uuid4()
        resposta = f"Oi! {self.DIVULGACAO}. Voce quer comprar ou alugar?"
        curto = self._imp(store, org, ver, 12)
        assert conf.detectar_vazamento(resposta, canario_do_prompt=None, impressao=curto) is not None
        # the disclosure is 15 tokens; a 24-token window cannot be matched by repeating it alone
        longo = self._imp(store, org, ver, 24)
        assert longo.shingle_tokens == 24 and store.obter_impressao(org, ver).shingle_tokens == 24
        assert conf.detectar_vazamento(resposta, canario_do_prompt=None, impressao=longo) is None

    def test_a_real_reproduction_is_still_caught_with_the_longer_window(self):
        store, org, ver = FakeConformidadeStore(), uuid4(), uuid4()
        longo = self._imp(store, org, ver, 24)
        copia = (f"Regra um. {self.DIVULGACAO}. Fim das regras internas do atendimento privado que ninguem alem da "
                 "equipe da plataforma deve ler jamais.")
        assert conf.detectar_vazamento(copia, canario_do_prompt=None, impressao=longo) is not None

    def test_the_stored_fingerprint_is_reused_when_the_length_matches(self):
        store, org, ver = FakeConformidadeStore(), uuid4(), uuid4()
        a = self._imp(store, org, ver, 12)
        assert self._imp(store, org, ver, 12) is a
