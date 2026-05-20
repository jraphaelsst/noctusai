"""Tests for `noctusai_lib.domain.real_estate`.

Covers `PropertyData` shape, `validate_product_code`, and
`build_youtube_metadata` — the cross-CRM domain primitives lifted from
``products/social-wiring/backend/app/services/crm_service.py`` 2026-05-20
via ``social-wiring-vista-seed-lift``.
"""

from __future__ import annotations

from noctusai_lib.domain.real_estate import (
    PropertyData,
    build_youtube_metadata,
    validate_product_code,
)


# ─── validate_product_code ───────────────────────────────────────────────


def test_validate_product_code_accepts_canonical():
    assert validate_product_code("ONE10010") is True


def test_validate_product_code_accepts_short_and_long_within_bounds():
    # Pattern is ONE + 3–6 digits.
    assert validate_product_code("ONE100") is True       # 3 digits
    assert validate_product_code("ONE100000") is True    # 6 digits


def test_validate_product_code_rejects_too_short():
    assert validate_product_code("ONE10") is False       # 2 digits


def test_validate_product_code_rejects_too_long():
    assert validate_product_code("ONE1000000") is False  # 7 digits


def test_validate_product_code_rejects_wrong_prefix():
    assert validate_product_code("TWO10010") is False
    assert validate_product_code("one10010") is False    # case-sensitive


def test_validate_product_code_rejects_empty_and_garbage():
    assert validate_product_code("") is False
    assert validate_product_code("not_a_code") is False
    assert validate_product_code("ONE10010 ") is False   # trailing space


# ─── build_youtube_metadata ──────────────────────────────────────────────


def _prop_full() -> PropertyData:
    """Fully-populated property — exercises every metadata branch."""
    return PropertyData(
        product_code="ONE10010",
        title="Apartamento 3 quartos — Moema, São Paulo",
        description="Apartamento reformado em rua tranquila.",
        address="Rua das Flores, 123, Moema, São Paulo",
        price="R$ 1.200.000",
        bedrooms=3,
        area_sqm=120.0,
    )


def test_build_youtube_metadata_returns_required_keys():
    meta = build_youtube_metadata(_prop_full(), "ONE10010")
    assert set(meta.keys()) == {"title", "description", "tags"}


def test_build_youtube_metadata_title_shape():
    """Title is `f"{code} — {prop.title}"` truncated to 100 chars."""
    prop = _prop_full()
    meta = build_youtube_metadata(prop, "ONE10010")
    assert meta["title"] == f"ONE10010 — {prop.title}"
    assert len(meta["title"]) <= 100


def test_build_youtube_metadata_title_truncates_at_100():
    long = PropertyData(
        product_code="ONE10010",
        title="X" * 200,
        description="",
    )
    meta = build_youtube_metadata(long, "ONE10010")
    assert len(meta["title"]) == 100


def test_build_youtube_metadata_description_embeds_emoji_block():
    """Description embeds the 📍/💰/🛏️/📐 emoji lines when fields present."""
    meta = build_youtube_metadata(_prop_full(), "ONE10010")
    desc = meta["description"]
    assert isinstance(desc, str)
    assert "📍 Rua das Flores, 123, Moema, São Paulo" in desc
    assert "💰 R$ 1.200.000" in desc
    assert "🛏️ 3 quartos" in desc
    assert "📐 120m²" in desc
    # Embedded body + footer.
    assert "Apartamento reformado em rua tranquila." in desc
    assert "Enviado pelo Social Wiring." in desc


def test_build_youtube_metadata_description_skips_missing_fields():
    """Optional fields → corresponding emoji line is omitted."""
    bare = PropertyData(
        product_code="ONE10010",
        title="Apto",
        description="",
    )
    desc = build_youtube_metadata(bare, "ONE10010")["description"]
    assert "📍" not in desc
    assert "💰" not in desc
    assert "🛏️" not in desc
    assert "📐" not in desc
    # Footer still present.
    assert "Enviado pelo Social Wiring." in desc


def test_build_youtube_metadata_tags_include_code_and_canonical_tags():
    """Tags include product_code + "imóvel" + "real estate" + "imobiliária"."""
    meta = build_youtube_metadata(_prop_full(), "ONE10010")
    tags = meta["tags"]
    assert isinstance(tags, list)
    assert "ONE10010" in tags
    assert "imóvel" in tags
    assert "real estate" in tags
    assert "imobiliária" in tags


def test_build_youtube_metadata_tags_include_address_when_present():
    meta = build_youtube_metadata(_prop_full(), "ONE10010")
    assert "Rua das Flores, 123, Moema, São Paulo" in meta["tags"]


def test_build_youtube_metadata_tags_skip_address_when_absent():
    bare = PropertyData(
        product_code="ONE10010",
        title="Apto",
        description="",
    )
    tags = build_youtube_metadata(bare, "ONE10010")["tags"]
    # Address shouldn't appear; canonical tags still do.
    assert all("Rua" not in tag for tag in tags if isinstance(tag, str))
    assert "ONE10010" in tags
