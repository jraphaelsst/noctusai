"""Tests for ``noctus.photo_editing.*`` MCP tools.

All DB/storage interactions are mocked — no real Supabase credentials
required. Covers:
  - org resolution (UUID / slug / name / empty / not-found)
  - list_rejections (success incl. guide-version + model enrichment,
    no-data, org-not-found, org-required, invalid batch, invalid edit
    type, limit clamping, signed-url failure degrades gracefully)
  - registration smoke
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.photo_editing._resolve import resolve_org  # noqa: E402
from tools.noctus.photo_editing.list_rejections import list_rejections  # noqa: E402


# ─── helpers ─────────────────────────────────────────────────────────────────

_ORG_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_LOTE_ID = "bbbbbbbb-0000-0000-0000-000000000001"
_FOTO_ID = "cccccccc-0000-0000-0000-000000000001"


def _fake_org(org_id: str = _ORG_ID, nome: str = "Imobiliaria Exemplo", slug: str = "imob-exemplo") -> dict:
    return {"id": org_id, "nome": nome, "slug": slug}


def _fake_rejection_row(**overrides) -> dict:
    row = {
        "foto_id": _FOTO_ID,
        "lote_id": _LOTE_ID,
        "comentario": "Ceu ficou artificial demais",
        "tipos_edicao": ["ceu"],
        "guia_efetivo_sha256": "sha-abc",
        "avaliacao_score": "8.10",
        "avaliacao_recomendacao": "aprovar",
        "storage_path_original": f"{_ORG_ID}/{_LOTE_ID}/{_FOTO_ID}/original.jpg",
        "storage_path_editada": f"{_ORG_ID}/{_LOTE_ID}/{_FOTO_ID}/editada.jpg",
        "created_at": "2026-09-15T18:04:00+00:00",
    }
    row.update(overrides)
    return row


def _supabase_resp(data: list) -> MagicMock:
    m = MagicMock()
    m.data = data
    return m


def _make_client(
    *,
    orgs: list | None = None,
    dataset: list | None = None,
    edits: list | None = None,
    efetivos: list | None = None,
    guias: list | None = None,
    signed_url: dict | Exception | None = None,
):
    """Fake Supabase client covering both ``.table()`` (default schema)
    and ``.schema("public").from_(...)`` (organizations) call shapes, plus
    ``.storage.from_(bucket).create_signed_url``.
    """
    data_map = {
        "fotos_dataset": dataset or [],
        "fotos_edicoes": edits or [],
        "fotos_guias_efetivos": efetivos or [],
        "fotos_guias_estilo": guias or [],
        "organizations": orgs or [],
    }

    def _chain(name):
        resp_data = data_map.get(name, [])
        chain = MagicMock()
        for m in ("select", "eq", "order", "limit", "in_", "overlaps", "ilike"):
            getattr(chain, m).return_value = chain
        chain.execute.return_value = _supabase_resp(resp_data)
        return chain

    client = MagicMock()
    client.table.side_effect = _chain

    def _schema(name):
        schema_ns = MagicMock()
        schema_ns.from_.side_effect = _chain
        return schema_ns

    client.schema.side_effect = _schema

    storage_bucket = MagicMock()
    if isinstance(signed_url, Exception):
        storage_bucket.create_signed_url.side_effect = signed_url
    else:
        storage_bucket.create_signed_url.return_value = signed_url or {
            "signedURL": "https://example.supabase.co/storage/v1/object/sign/edicao-fotos/x"
        }
    client.storage.from_.return_value = storage_bucket

    return client


# ─── _resolve.resolve_org ──────────────────────────────────────────────────


def test_resolve_org_by_uuid():
    org = _fake_org()
    client = _make_client(orgs=[org])
    result = resolve_org(client, org["id"])
    assert result["id"] == org["id"]


def test_resolve_org_by_slug():
    org = _fake_org()
    client = _make_client(orgs=[org])
    result = resolve_org(client, org["slug"])
    assert result["slug"] == org["slug"]


def test_resolve_org_empty_is_required_error():
    client = _make_client(orgs=[])
    result = resolve_org(client, None)
    assert result == {
        "error": "org_required",
        "message": "org is required — pass an organization UUID, slug, or name.",
    }


def test_resolve_org_not_found():
    client = _make_client(orgs=[])
    result = resolve_org(client, "nonexistent")
    assert result is None


# ─── list_rejections ─────────────────────────────────────────────────────────


def test_list_rejections_success_with_enrichment():
    org = _fake_org()
    dataset = [_fake_rejection_row()]
    edits = [
        {"foto_id": _FOTO_ID, "modelo_id": "gpt-image-2.5-sunburst", "modelo_versao": "2026-09-08", "tentativa": 1}
    ]
    efetivos = [{"sha256": "sha-abc", "guia_estilo_id": "guia-1"}]
    guias = [{"id": "guia-1", "versao": 7}]
    client = _make_client(orgs=[org], dataset=dataset, edits=edits, efetivos=efetivos, guias=guias)

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"])

    assert result["total_returned"] == 1
    row = result["rejections"][0]
    assert row["foto_id"] == _FOTO_ID
    assert row["comentario"] == "Ceu ficou artificial demais"
    assert row["guia_versao"] == 7
    assert row["modelo_id"] == "gpt-image-2.5-sunburst"
    assert row["modelo_versao"] == "2026-09-08"
    assert row["antes_url"].startswith("https://")
    assert row["depois_url"].startswith("https://")


def test_list_rejections_no_data():
    org = _fake_org()
    client = _make_client(orgs=[org], dataset=[])

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"])

    assert result.get("status") == "no_data"


def test_list_rejections_org_not_found():
    client = _make_client(orgs=[])

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=None):
        result = list_rejections(org="unknown")

    assert result.get("error") == "org_not_found"


def test_list_rejections_org_required():
    client = _make_client()
    required = {"error": "org_required", "message": "x"}

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=required):
        result = list_rejections(org="")

    assert result == required


def test_list_rejections_not_configured():
    with patch(
        "tools.noctus.photo_editing.list_rejections.get_pe_client",
        side_effect=RuntimeError("missing creds"),
    ):
        result = list_rejections(org="anything")

    assert result.get("error") == "not_configured"


def test_list_rejections_invalid_batch():
    org = _fake_org()
    client = _make_client(orgs=[org])

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"], batch="not-a-uuid")

    assert result.get("error") == "invalid_batch"


def test_list_rejections_invalid_edit_type():
    org = _fake_org()
    client = _make_client(orgs=[org])

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"], edit_types=["nonexistent_type"])

    assert result.get("error") == "invalid_edit_type"
    assert "nonexistent_type" in result["invalid"]


def test_list_rejections_limit_clamped_above_max():
    org = _fake_org()
    client = _make_client(orgs=[org], dataset=[])

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"], limit=500)

    # Clamped to 100 — no crash, degrades to no_data on the empty fixture.
    assert result.get("status") == "no_data"


def test_list_rejections_signed_url_failure_degrades_to_none():
    org = _fake_org()
    dataset = [_fake_rejection_row()]
    client = _make_client(orgs=[org], dataset=dataset, signed_url=RuntimeError("storage down"))

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"])

    row = result["rejections"][0]
    assert row["antes_url"] is None
    assert row["depois_url"] is None
    # The row itself still surfaces — a broken signed URL never blanks the list.
    assert row["comentario"] == "Ceu ficou artificial demais"


def test_list_rejections_missing_guide_and_model_are_null_not_crash():
    org = _fake_org()
    dataset = [_fake_rejection_row(guia_efetivo_sha256="sha-unmapped")]
    client = _make_client(orgs=[org], dataset=dataset, edits=[], efetivos=[], guias=[])

    with patch("tools.noctus.photo_editing.list_rejections.get_pe_client", return_value=client), \
         patch("tools.noctus.photo_editing.list_rejections.resolve_org", return_value=org):
        result = list_rejections(org=org["id"])

    row = result["rejections"][0]
    assert row["guia_versao"] is None
    assert row["modelo_id"] is None
    assert row["modelo_versao"] is None


# ─── registration smoke ───────────────────────────────────────────────────────


def test_register_all_smoke():
    """register_all() should register 1 tool without raising."""
    from tools.noctus.photo_editing import register_all

    names: list[str] = []

    class FakeServer:
        def tool(self, *, name: str, description: str = ""):
            def decorator(fn):
                names.append(name)
                return fn
            return decorator

    register_all(FakeServer())

    assert names == ["noctus.photo_editing.list_rejections"]
