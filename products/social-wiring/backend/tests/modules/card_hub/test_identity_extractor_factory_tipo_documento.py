"""Regression coverage for `NOC-REMEDIATE[identity-extractor-factory-ignores-tipo-documento]`.

`card_hub.deps.get_identity_extractor_factory()` used to build the identity
extractor keyed ONLY on `org_id`. Every REAL caller of
`identidade_extracao_service.extrair_identidade` — the upload route, the
`.../extrair` re-run route, and the recovery sweep — pre-builds the
extractor through that factory BEFORE `extrair_identidade` ever loads the
document row, so `extrair_identidade`'s own
`extractor or make_identity_extractor(..., max_pages=paginas_maximas(...))`
fallback always short-circuited in production and the type-driven page cap
(`TIPOS_LEITURA_INTEGRAL`) never ran. A `certidao_casamento` got the
adapter's 3-page default instead of a whole read — which does not degrade
the answer, it INVERTS it (the marriage is on page 1, the divórcio
averbação is further in).

These tests pin the fix at three levels:

1. The factory itself now resolves `max_pages` from `tipo_documento`
   (`TestDepsFactoryThreadsTipoDocumentoIntoMaxPages`).
2. ALL THREE real call sites now pass `tipo_documento` into the factory
   (`TestRealCallersThreadTipoDocumentoIntoTheFactory`) — the upload route,
   the re-run route, and the sweep. The whole bug was that the mapping was
   correct but unreachable; asserting only on `paginas_maximas` (already
   covered by `test_identidade_extracao.py`) would miss exactly the gap
   that shipped it.
3. Content that only exists on the LAST page of a multi-page certidão
   reaches the extracted fields when the fix is wired end-to-end, and does
   NOT for a type outside `TIPOS_LEITURA_INTEGRAL`
   (`TestContentOnTheLastPageReachesTheExtractedFields`).

Kept out of `test_identidade_extracao.py`: that file's own docstring notes
it already carries `unittest.mock.patch(...)` calls that trip
`test_seam_guard` on ANY edit, so new coverage for this module lands in a
sibling file rather than re-triggering that guard on unrelated lines.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import deps
from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import FakeIdentityExtractor
from tests.modules.card_hub.conftest import (
    ORG_ID,
    cliente_row,
    documento_row,
    documento_tipo_row,
)

ORG_UUID = UUID(ORG_ID)
BUCKET = "social-wiring-documentos"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestDepsFactoryThreadsTipoDocumentoIntoMaxPages:
    """The factory seam itself: `_build_identity_extractor` must resolve
    `max_pages` from `tipo_documento`, for BOTH sides of `TIPOS_LEITURA_INTEGRAL`."""

    @pytest.mark.parametrize(
        "tipo,esperado",
        [
            ("certidao_casamento", None),
            ("certidao_nascimento", None),
            ("rg", -1),
            ("cpf", -1),
            ("cnh", -1),
            (None, -1),
        ],
    )
    def test_max_pages_follows_paginas_maximas(self, monkeypatch, tipo, esperado):
        visto: dict = {}

        def _fabrica(**kw):
            visto.update(kw)
            return FakeIdentityExtractor()

        # Substitutes the SEED factory at this module's own import site (a
        # third-party-shaped boundary — the documented Fake/Real swap
        # point), not this module's own logic. Mirrors
        # `test_identidade_extracao.py::test_the_cap_reaches_the_extractor_factory`.
        monkeypatch.setattr(deps, "make_identity_extractor", _fabrica)  # self-patch-ok: seed Fake/Real factory swap point, not our own logic

        # `resolve_provider` is `_build_identity_extractor`'s own injected
        # collaborator (see that function's docstring) — NOT a patch of
        # `resolve_vision_provider`. Its default reaches a real Supabase
        # client via `resolve_api_key_detail`'s tier-1 lookup
        # (`build_api_key_store()` -> `get_admin_client()`), which raises
        # `SupabaseException: supabase_url is required` in any environment
        # with no Supabase config (CI has none). This test's whole subject
        # is the `tipo_documento` -> `max_pages` mapping, which has nothing
        # to do with provider resolution — a fake collaborator proves the
        # same thing without a live credential chain.
        deps._build_identity_extractor(
            ORG_ID, tipo, resolve_provider=lambda _org_id: "openai"
        )

        assert visto.get("max_pages") == esperado
        assert visto.get("org_id") == ORG_ID
        assert visto.get("real") is True
        assert visto.get("provider") == "openai"


class TestRealCallersThreadTipoDocumentoIntoTheFactory:
    """The gap the mapping test above cannot see on its own: did every REAL
    caller actually hand the factory a `tipo_documento` at all? Spies on
    `get_identity_extractor_factory`'s call args, one caller at a time."""

    def _spy_factory(self, app, calls: list[tuple[str, Optional[str]]]):
        from app.modules.card_hub.deps import get_identity_extractor_factory

        def _build(org_id, tipo_documento=None):
            calls.append((org_id, tipo_documento))
            return FakeIdentityExtractor()

        prev = app.dependency_overrides.get(get_identity_extractor_factory)
        app.dependency_overrides[get_identity_extractor_factory] = lambda: _build
        return prev, get_identity_extractor_factory

    def test_upload_route_passes_the_uploaded_tipo(self, client, scoped, fake_storage):
        from app.main import app

        calls: list[tuple[str, Optional[str]]] = []
        prev, key = self._spy_factory(app, calls)
        try:
            cid = str(uuid4())
            scoped.set_table_data("clientes", [cliente_row(cid)])
            scoped.set_table_data(
                "cliente_documento_tipos",
                [documento_tipo_row("certidao_casamento", categoria="identidade", identidade=True)],
            )
            resp = client.post(
                f"/api/clientes/{cid}/documentos",
                files={"file": ("certidao.pdf", b"%PDF-1.4 fake", "application/pdf")},
                data={"tipo_documento": "certidao_casamento"},
                headers=_auth(),
            )
            assert resp.status_code == 201, resp.text
        finally:
            if prev is None:
                app.dependency_overrides.pop(key, None)
            else:
                app.dependency_overrides[key] = prev

        assert calls, "the factory was never asked to build an extractor"
        [(seen_org, seen_tipo)] = calls
        assert seen_org == ORG_ID
        assert seen_tipo == "certidao_casamento"

    @pytest.mark.asyncio
    async def test_reextrair_route_passes_the_documents_own_tipo(
        self, client, scoped, fake_storage
    ):
        from app.main import app

        calls: list[tuple[str, Optional[str]]] = []
        prev, key = self._spy_factory(app, calls)
        try:
            cid = str(uuid4())
            did = str(uuid4())
            path = f"{ORG_ID}/clientes/{cid}/{did}"
            scoped.set_table_data("clientes", [cliente_row(cid)])
            scoped.set_table_data(
                "cliente_documentos",
                [
                    documento_row(
                        did, cid,
                        tipo_documento="certidao_casamento", categoria_lgpd="identidade",
                        storage_path=path, extracao_status="erro",
                        extracao_erro="openai: 429", extracao_tentativas=1,
                    )
                ],
            )
            await fake_storage.put(
                bucket=BUCKET, key=path, data=b"%PDF-1.4 fake", content_type="application/pdf"
            )
            resp = client.post(
                f"/api/clientes/{cid}/documentos/{did}/extrair", headers=_auth()
            )
            assert resp.status_code == 200, resp.text
        finally:
            if prev is None:
                app.dependency_overrides.pop(key, None)
            else:
                app.dependency_overrides[key] = prev

        assert calls, "the factory was never asked to build an extractor"
        [(seen_org, seen_tipo)] = calls
        assert seen_org == ORG_ID
        assert seen_tipo == "certidao_casamento"

    @pytest.mark.asyncio
    async def test_sweep_passes_the_stalled_rows_tipo(self, client, scoped, fake_storage):
        from datetime import datetime, timedelta, timezone

        cid = str(uuid4())
        did = str(uuid4())
        path = f"{ORG_ID}/clientes/{cid}/{did}"
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    did, cid,
                    tipo_documento="certidao_casamento", categoria_lgpd="identidade",
                    storage_path=path,
                    extracao_status="processando",
                    extracao_em=(
                        datetime.now(timezone.utc) - timedelta(minutes=60)
                    ).isoformat(),
                    extracao_tentativas=1,
                )
            ],
        )
        await fake_storage.put(
            bucket=BUCKET, key=path, data=b"%PDF-1.4 fake", content_type="application/pdf"
        )

        calls: list[tuple[str, Optional[str]]] = []

        def _factory(org_id, tipo_documento=None):
            calls.append((org_id, tipo_documento))
            return FakeIdentityExtractor()

        result = await svc.varrer_extracoes_pendentes(
            scoped, fake_storage, extractor_factory=_factory
        )
        assert result["retomados"] == 1

        assert calls, "the sweep never asked the factory to build an extractor"
        [(seen_org, seen_tipo)] = calls
        assert seen_org == ORG_ID
        assert seen_tipo == "certidao_casamento"


class _ResolvedText:
    def __init__(self, text: str) -> None:
        self.text, self.error, self.error_message = text, None, None


class _PageCappedResolver:
    """Stands in for `RealMediaResolver` — the ONE place `max_pages`
    genuinely gates what reaches the model. `PAGINAS` mimics a certidão
    whose page 1 states the marriage and whose divórcio averbação sits on
    the LAST page; a resolver built with a positive cap never sees it,
    exactly like the production adapter this stubs (`-1` — "not specified"
    — mirrors the adapter's own literal 3-page default, per
    `documents.factory.make_identity_extractor`'s own docstring)."""

    PAGINAS = (
        "CERTIDAO DE CASAMENTO\n"
        "OS CONTRAENTES CASARAM-SE SOB O REGIME DA COMUNHAO PARCIAL DE BENS\n",
        "FILHOS DO CASAL: (nenhum)\n",
        "OBSERVACOES: nenhuma\n",
        "AVERBACAO: DIVORCIO AVERBADO EM 10/03/2020, CONFORME SENTENCA\n",
    )
    _ADAPTER_DEFAULT_CAP = 3

    def __init__(self, max_pages: Optional[int]) -> None:
        self._max_pages = max_pages

    async def resolve(self, media):
        if self._max_pages is None:
            paginas = self.PAGINAS
        else:
            cap = (
                self._ADAPTER_DEFAULT_CAP
                if self._max_pages == -1
                else self._max_pages
            )
            paginas = self.PAGINAS[:cap]
        return _ResolvedText("".join(paginas))


def _patch_media_resolver(monkeypatch):
    """Swaps the seed's OWN Real/Fake extension point
    (`noctusai_lib.integrations.media.get_media_resolver`, the function
    `DocumentTextLadder._get_resolver` calls when no resolver was injected)
    for one whose output genuinely depends on `max_pages` — so an assertion
    on the FINAL `IdentityFields` proves the cap reached the vision rung,
    not merely that `paginas_maximas` computed the right number. Same
    category of patch `test_extractor.py`/`test_civil_status.py` already
    make on `classify_pdf_text_layer` — the seed's documented swap point,
    never our own logic or a compliance guard.
    """
    import noctusai_lib.integrations.media as media_mod

    def _fake_get_media_resolver(*, max_pages=-1, **_kw):
        return _PageCappedResolver(max_pages=max_pages)

    monkeypatch.setattr(media_mod, "get_media_resolver", _fake_get_media_resolver)  # self-patch-ok: seed Real/Fake resolver factory swap point, not our own logic


class TestContentOnTheLastPageReachesTheExtractedFields:
    """🔴 The whole point of the fix, proven end-to-end through the deps
    factory: a certidão de casamento's divórcio averbação — the LAST
    "page" — must reach `IdentityFields.estado_civil`. A document type
    outside `TIPOS_LEITURA_INTEGRAL` must NOT: it keeps the adapter's own
    3-page default and never sees it, which is the behaviour-preserving
    half of this fix."""

    @pytest.mark.asyncio
    async def test_certidao_casamento_reads_the_averbacao_on_the_last_page(
        self, monkeypatch
    ):
        _patch_media_resolver(monkeypatch)
        # `resolve_provider` is the injected collaborator, not a real
        # credential lookup — see `_build_identity_extractor`'s docstring.
        # This test's subject is `max_pages`, not the provider.
        extractor = deps._build_identity_extractor(
            ORG_ID, "certidao_casamento", resolve_provider=lambda _org_id: "openai"
        )

        out = await extractor.extract(
            b"\x89PNG", mimetype="image/png", filename="certidao.png"
        )

        assert out.estado_civil == "divorciado"
        assert out.estado_civil_rotulo is not None
        assert "AVERBACAO" in out.estado_civil_rotulo
        # …and the registro's own page-1 fact is still there for regime_bens,
        # which the divórcio averbação does not touch.
        assert out.regime_bens == "comunhao_parcial"

    @pytest.mark.asyncio
    async def test_an_rg_keeps_the_adapters_default_and_never_reaches_it(
        self, monkeypatch
    ):
        """The same 4-'page' document, read through a type NOT in
        `TIPOS_LEITURA_INTEGRAL` — the truncated read this fix must NOT
        change for a type that never needed a whole one."""
        _patch_media_resolver(monkeypatch)
        extractor = deps._build_identity_extractor(
            ORG_ID, "rg", resolve_provider=lambda _org_id: "openai"
        )

        out = await extractor.extract(
            b"\x89PNG", mimetype="image/png", filename="rg.png"
        )

        # The registro still reads "casado" — the averbação past page 3
        # never arrived.
        assert out.estado_civil == "casado"
        assert out.estado_civil_rotulo is not None
        assert "AVERBACAO" not in out.estado_civil_rotulo
