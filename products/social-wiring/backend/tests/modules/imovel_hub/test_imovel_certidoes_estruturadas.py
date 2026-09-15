"""Imóvel CND group — cnd_iptu / cnd_condominio / guia_iptu / matrícula
structured extraction, confirmation, and the `GET .../certidoes` rollup
(migration 118).

WHAT THESE PIN BEYOND THE HAPPY PATH
------------------------------------
- the AI seam is a DI seam (`extract_text` / `analyze_estrutura`), never a
  monkeypatch of `chat_completion` or this module's own functions;
- a human's confirmation (`origem="manual"` or a non-null `confirmado_por`)
  is NEVER overwritten by a later automated read;
- a guia de IPTU's inscrição SUGGESTS into `imovel_dados.prefeitura_
  cadastro_imobiliario` only when that column is empty — first writer wins,
  same posture `numero_matricula` already has;
- a matrícula's own emissão date SUGGESTS into `imovel_dados.
  onus_certidao_em`, same rule;
- `PATCH .../extracao` refuses a field this document's tipo does not carry;
- `GET .../certidoes` returns the LATEST document per tipo, `guia_iptu`
  excluded (it carries no resultado/emissão of its own);
- every failure path is recorded/logged, never raised — this job runs
  detached from the upload request.

Auth is not re-tested here — `test_imovel_auth_boundary.py` enumerates every
mounted route (including the two new ones) and asserts a strict 401.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.imovel_hub import documentos_service
from tests.modules.imovel_hub.conftest import (
    CODIGO,
    ORG_ID,
    auth,
    dados_row,
    documento_row,
    seed,
)


def _texto_fixo(texto):
    async def _fn(conteudo, mimetype, org_id):
        return texto
    return _fn


def _analise_fixa(resultado):
    async def _fn(texto, tipo_documento, org_id):
        return resultado
    return _fn


async def _seed_storage(fake_storage, path: str) -> None:
    await fake_storage.put(
        bucket="social-wiring-documentos",
        key=path,
        data=b"%PDF",
        content_type="application/pdf",
    )


class TestUploadAcceptsTheNewTipos:
    def test_a_cnd_iptu_uploads(self, client, scoped, fake_storage, fake_extractor):
        seed(scoped)
        r = client.post(
            f"/api/imoveis/{CODIGO}/documentos",
            files={"file": ("cnd.pdf", b"%PDF-1.7 fake", "application/pdf")},
            data={"tipo_documento": "cnd_iptu"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["tipo_documento"] == "cnd_iptu"

    def test_a_cnd_condominio_uploads(self, client, scoped, fake_storage, fake_extractor):
        seed(scoped)
        r = client.post(
            f"/api/imoveis/{CODIGO}/documentos",
            files={"file": ("cnd.pdf", b"%PDF-1.7 fake", "application/pdf")},
            data={"tipo_documento": "cnd_condominio"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["tipo_documento"] == "cnd_condominio"


class TestTheStructuredExtraction:
    @pytest.mark.asyncio
    async def test_a_cnd_iptu_read_lands_on_the_document(self, client, scoped, fake_storage):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", storage_path=path)])
        await _seed_storage(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("CND IPTU ..."),
            analyze_estrutura=_analise_fixa({
                "numero": "PROT-1",
                "emitida_em": "2026-09-01",
                "validade_ate": "2026-10-01",
                "resultado": "negativa",
                "inscricao_imobiliaria": "12.345.678-9",
            }),
        )
        assert out["status"] == "ok"

        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        row = docs["items"][0]
        assert row["numero"] == "PROT-1"
        assert row["emitida_em"] == "2026-09-01"
        assert row["validade_ate"] == "2026-10-01"
        assert row["resultado"] == "negativa"
        assert row["inscricao_imobiliaria"] == "12.345.678-9"
        assert row["origem"] == "ia"
        assert row["confirmado_por"] is None

    @pytest.mark.asyncio
    async def test_a_cnd_condominio_read_only_carries_its_two_fields(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_condominio", storage_path=path)])
        await _seed_storage(fake_storage, path)

        # A COMPLIANT analyze_estrutura only ever answers with the fields it
        # was asked for — the extra-keys-are-dropped guarantee itself is
        # `_parse_json_estrutura`'s job and is pinned directly below
        # (`TestParseJsonEstrutura`), not re-asserted through this DI seam.
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("declaracao de quitacao ..."),
            analyze_estrutura=_analise_fixa({
                "emitida_em": "2026-09-05",
                "resultado": "positiva",
            }),
        )
        assert out["status"] == "ok"
        assert out["campos"] == ["emitida_em", "resultado"]

        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        row = docs["items"][0]
        assert row["emitida_em"] == "2026-09-05"
        assert row["resultado"] == "positiva"
        assert row["numero"] is None
        assert row["inscricao_imobiliaria"] is None


class TestParseJsonEstrutura:
    """The AI answer's defensive parse — pure, no DI seam needed."""

    def test_extra_keys_outside_the_tipos_campos_are_dropped(self):
        campos = documentos_service.CAMPOS_ESTRUTURA_POR_TIPO["cnd_condominio"]
        raw = (
            '{"numero": "SHOULD-BE-DROPPED", "emitida_em": "2026-09-05", '
            '"resultado": "positiva", '
            '"inscricao_imobiliaria": "SHOULD-BE-DROPPED"}'
        )
        out = documentos_service._parse_json_estrutura(raw, campos)
        assert out == {"emitida_em": "2026-09-05", "resultado": "positiva"}

    def test_an_out_of_vocabulary_resultado_is_dropped(self):
        campos = documentos_service.CAMPOS_ESTRUTURA_POR_TIPO["cnd_iptu"]
        raw = '{"resultado": "nao_emitida", "numero": "X"}'
        out = documentos_service._parse_json_estrutura(raw, campos)
        assert out == {"numero": "X"}

    def test_a_malformed_date_is_dropped(self):
        campos = documentos_service.CAMPOS_ESTRUTURA_POR_TIPO["cnd_iptu"]
        raw = '{"emitida_em": "15 de marco de 2026"}'
        assert documentos_service._parse_json_estrutura(raw, campos) is None

    def test_unparseable_json_returns_none(self):
        campos = documentos_service.CAMPOS_ESTRUTURA_POR_TIPO["cnd_iptu"]
        assert documentos_service._parse_json_estrutura("not json", campos) is None

    def test_a_markdown_fenced_answer_is_stripped_first(self):
        campos = documentos_service.CAMPOS_ESTRUTURA_POR_TIPO["cnd_condominio"]
        raw = '```json\n{"resultado": "negativa"}\n```'
        out = documentos_service._parse_json_estrutura(raw, campos)
        assert out == {"resultado": "negativa"}

    @pytest.mark.asyncio
    async def test_a_guia_iptu_read_suggests_into_prefeitura_cadastro_when_empty(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(scoped, documentos=[documento_row(did, tipo_documento="guia_iptu", storage_path=path)])
        await _seed_storage(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("guia de iptu ..."),
            analyze_estrutura=_analise_fixa({"inscricao_imobiliaria": "99.888.777-6"}),
        )
        assert out["status"] == "ok"
        assert out["sugerido_em_dados"] is True

        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["prefeitura_cadastro_imobiliario"] == "99.888.777-6"

    @pytest.mark.asyncio
    async def test_the_suggestion_never_overwrites_an_existing_value(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(
            scoped,
            documentos=[documento_row(did, tipo_documento="guia_iptu", storage_path=path)],
            dados=[dados_row(prefeitura_cadastro_imobiliario="ALREADY-SET")],
        )
        await _seed_storage(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("guia de iptu ..."),
            analyze_estrutura=_analise_fixa({"inscricao_imobiliaria": "99.888.777-6"}),
        )
        assert out["sugerido_em_dados"] is False

        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["prefeitura_cadastro_imobiliario"] == "ALREADY-SET"

    @pytest.mark.asyncio
    async def test_a_matricula_read_suggests_its_emission_date_into_onus_certidao_em(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(scoped, documentos=[documento_row(did, tipo_documento="matricula", storage_path=path)])
        await _seed_storage(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("certidao de matricula expedida em ..."),
            analyze_estrutura=_analise_fixa({"emitida_em": "2026-08-20"}),
        )
        assert out["sugerido_em_dados"] is True

        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["onus_certidao_em"] == "2026-08-20"

    @pytest.mark.asyncio
    async def test_a_confirmed_document_is_never_overwritten(self, client, scoped, fake_storage):
        """🔴 The lock `PATCH .../extracao` sets must survive a retry."""
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(
            scoped,
            documentos=[
                documento_row(
                    did,
                    tipo_documento="cnd_iptu",
                    storage_path=path,
                    resultado="negativa",
                    origem="manual",
                    confirmado_por=str(uuid4()),
                )
            ],
        )
        analyzer = _analise_fixa({"resultado": "positiva"})
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("..."),
            analyze_estrutura=analyzer,
        )
        assert out["status"] == "ignorado"

        docs = client.get(f"/api/imoveis/{CODIGO}/documentos", headers=auth()).json()
        assert docs["items"][0]["resultado"] == "negativa"


class TestEveryFailureIsRecordedNeverRaised:
    @pytest.mark.asyncio
    async def test_a_missing_document_is_recorded_not_raised(self, scoped, fake_storage):
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(str(uuid4())),
        )
        assert out["status"] == "erro"
        assert out["erro"] == "documento_nao_encontrado"

    @pytest.mark.asyncio
    async def test_a_deleted_document_is_not_read(self, scoped, fake_storage):
        did = str(uuid4())
        seed(
            scoped,
            documentos=[
                documento_row(
                    did, tipo_documento="cnd_iptu",
                    deleted_at="2026-02-01T00:00:00+00:00",
                )
            ],
        )
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
        )
        assert out["erro"] == "documento_removido"

    @pytest.mark.asyncio
    async def test_a_tipo_with_no_structured_extraction_is_refused(self, scoped, fake_storage):
        """Every UPLOADABLE tipo happens to be extraction-eligible today, so
        this exercises the guard directly against a row whose tipo predates
        (or bypasses) the allow-list — the same defensive posture
        `matricula_extracao_service`'s own `tipo_nao_extraivel` test takes.
        """
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, tipo_documento="escritura")])
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
        )
        assert out["erro"] == "tipo_nao_extraivel"

    @pytest.mark.asyncio
    async def test_a_missing_storage_object_is_recorded_not_raised(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", storage_path="nope")])
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
        )
        assert out["status"] == "erro"
        assert out["erro"] == "objeto_ausente"

    @pytest.mark.asyncio
    async def test_no_readable_text_is_sem_dados_not_erro(self, client, scoped, fake_storage):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", storage_path=path)])
        await _seed_storage(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo(None),
        )
        assert out["status"] == "sem_dados"

    @pytest.mark.asyncio
    async def test_the_ai_leg_returning_nothing_is_sem_dados_not_erro(
        self, client, scoped, fake_storage
    ):
        did = str(uuid4())
        path = f"{ORG_ID}/imoveis/{CODIGO}/x"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", storage_path=path)])
        await _seed_storage(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, UUID(ORG_ID), CODIGO, UUID(did),
            extract_text=_texto_fixo("texto ilegivel"),
            analyze_estrutura=_analise_fixa(None),
        )
        assert out["status"] == "sem_dados"


class TestConfirmarExtracaoRoute:
    def test_the_operator_confirms_and_edits(self, client, scoped):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", resultado="negativa")])

        r = client.patch(
            f"/api/imoveis/{CODIGO}/documentos/{did}/extracao",
            json={"resultado": "positiva", "numero": "PROT-9"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["resultado"] == "positiva"
        assert body["numero"] == "PROT-9"
        assert body["origem"] == "manual"
        assert body["confirmado_por"] is not None
        assert body["confirmado_em"] is not None

    def test_an_empty_body_is_still_a_confirmation(self, client, scoped):
        """A pure "I reviewed this and it is correct" locks the row too."""
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", resultado="negativa")])

        r = client.patch(
            f"/api/imoveis/{CODIGO}/documentos/{did}/extracao",
            json={},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["resultado"] == "negativa"
        assert body["origem"] == "manual"
        assert body["confirmado_por"] is not None

    def test_a_field_the_tipo_does_not_carry_is_refused(self, client, scoped):
        """`guia_iptu` only has `inscricao_imobiliaria` — not `resultado`."""
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(did, tipo_documento="guia_iptu")])

        r = client.patch(
            f"/api/imoveis/{CODIGO}/documentos/{did}/extracao",
            json={"resultado": "negativa"},
            headers=auth(),
        )
        assert r.status_code == 400
        assert "resultado" in r.text

    def test_an_unknown_document_is_a_404(self, client, scoped):
        seed(scoped)
        r = client.patch(
            f"/api/imoveis/{CODIGO}/documentos/{uuid4()}/extracao",
            json={},
            headers=auth(),
        )
        assert r.status_code == 404


class TestCertidoesRoute:
    def test_returns_one_entry_per_tipo_latest_first_seen(self, client, scoped):
        seed(
            scoped,
            documentos=[
                documento_row(
                    str(uuid4()), tipo_documento="cnd_iptu",
                    resultado="negativa", emitida_em="2026-08-01",
                    created_at="2026-08-01T00:00:00+00:00",
                ),
                # A NEWER cnd_iptu — must win over the older one above.
                documento_row(
                    str(uuid4()), tipo_documento="cnd_iptu",
                    resultado="positiva", emitida_em="2026-09-01",
                    created_at="2026-09-01T00:00:00+00:00",
                ),
                documento_row(
                    str(uuid4()), tipo_documento="cnd_condominio",
                    resultado="negativa", emitida_em="2026-09-05",
                    created_at="2026-09-05T00:00:00+00:00",
                ),
                documento_row(
                    str(uuid4()), tipo_documento="matricula",
                    emitida_em="2026-07-01",
                    created_at="2026-07-01T00:00:00+00:00",
                ),
                # guia_iptu carries no resultado/emissão — must be excluded.
                documento_row(str(uuid4()), tipo_documento="guia_iptu"),
            ],
        )
        r = client.get(f"/api/imoveis/{CODIGO}/certidoes", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3
        por_tipo = {item["tipo"]: item for item in body["items"]}
        assert set(por_tipo) == {"cnd_iptu", "cnd_condominio", "matricula"}
        assert por_tipo["cnd_iptu"]["resultado"] == "positiva"
        assert por_tipo["cnd_iptu"]["emitida_em"] == "2026-09-01"
        assert por_tipo["matricula"]["emitida_em"] == "2026-07-01"

    def test_confirmado_reflects_a_manual_origem_or_a_confirmed_stamp(self, client, scoped):
        seed(
            scoped,
            documentos=[
                documento_row(
                    str(uuid4()), tipo_documento="cnd_iptu",
                    resultado="negativa", origem="ia",
                ),
            ],
        )
        body = client.get(f"/api/imoveis/{CODIGO}/certidoes", headers=auth()).json()
        assert body["items"][0]["confirmado"] is False

    def test_an_empty_imovel_returns_an_empty_envelope(self, client, scoped):
        seed(scoped)
        body = client.get(f"/api/imoveis/{CODIGO}/certidoes", headers=auth()).json()
        assert body == {"items": [], "total": 0}

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        r = client.get("/api/imoveis/NOPE9999/certidoes", headers=auth())
        assert r.status_code == 404
