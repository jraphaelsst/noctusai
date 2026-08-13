"""`Imovel` round-trip tests against REAL captured Vista payloads.

Every fixture row is a verbatim response from tenant ``oneconsu-rest``,
captured 2026-08-03 during the full-catalog census, and each was selected
because it exercises one documented wire quirk. Synthetic payloads were
deliberately not used: the whole reason this model exists is that the wire
does things nobody would invent (``"0"`` meaning two different things,
``Corretor`` switching between dict and list, ``null`` appearing in exactly
one field), and a hand-written fixture encodes the author's belief about
the wire rather than the wire.

Census population for the percentages cited below: 1919 listar rows, 75
stratified detalhes payloads covering all 20 categorias and all 3 statuses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from noctusai_lib.domain.real_estate.imovel import (
    Imovel,
    caracteristica_slug,
    derive_finalidades,
    normalize_place_name,
    parse_caracteristicas,
    parse_corretores,
    parse_area,
    parse_count,
    parse_money,
    parse_sim_nao,
)
from noctusai_lib.integrations.vista.imovel_normalizer import (
    merge_vista_payloads,
    vista_to_imovel,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "vista" / "imovel_payloads.json"


@pytest.fixture(scope="module")
def payloads() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def by_quirk(payloads) -> dict:
    return {row["_quirk"]: row for row in payloads["listar"]}


# ─── W3 — the "0" overload, the rule most likely to be re-broken ──────────


def test_valor_locacao_zero_means_not_for_rent_not_free(by_quirk):
    """`ValorLocacao: "0"` on a Venda listing → None, never 0.0.

    1488/1919 rows carry this. Returning 0.0 renders "R$ 0" across 78% of
    the catalog.
    """
    imovel = vista_to_imovel(listing=by_quirk["venda_locacao_zero"])
    assert by_quirk["venda_locacao_zero"]["ValorLocacao"] == "0"
    assert imovel.valor_locacao is None
    assert imovel.valor_venda is not None


def test_valor_venda_zero_on_aluguel_is_the_same_fact_inverted(by_quirk):
    """63 of the 66 Aluguel rows carry `ValorVenda: "0"`."""
    imovel = vista_to_imovel(listing=by_quirk["aluguel_venda_zero"])
    assert imovel.valor_venda is None
    assert imovel.valor_locacao is not None
    assert imovel.para_aluguel is True


def test_room_counts_keep_a_real_zero(by_quirk):
    """A Terreno genuinely has 0 dormitórios — this must NOT become None.

    The `"0" → None` rule is correct for money and area and WRONG here.
    Collapsing it would make "terrenos" indistinguishable from "unknown".
    """
    row = by_quirk["terreno_zero_quartos"]
    assert row["Dormitorios"] == "0"
    imovel = vista_to_imovel(listing=row)
    assert imovel.dormitorios == 0
    assert imovel.dormitorios is not None


def test_area_construida_zero_is_unknown_not_zero(by_quirk):
    """`"0"` on 1918/1919 rows — a building with no area does not exist."""
    imovel = vista_to_imovel(listing=by_quirk["venda_locacao_zero"])
    assert imovel.area_construida is None


# ─── W2 — null exists, contra the single-sample reading ───────────────────


def test_codigo_imobiliaria_json_null_is_handled(by_quirk):
    """38/1919 rows carry JSON `null` here, not `""`.

    Phase 1 concluded from one imóvel that Vista "uses '' never null". A
    coercion that only strips `""` raises AttributeError on these rows.
    """
    row = by_quirk["codigo_imobiliaria_null"]
    assert row["CodigoImobiliaria"] is None
    imovel = vista_to_imovel(listing=row)
    assert imovel.codigo_imobiliaria is None


# ─── W7 — Corretor is polymorphic AND multi ───────────────────────────────


def test_multi_corretor_keeps_every_broker(by_quirk):
    """252/1919 imóveis (13.1%) have 2–3 corretores.

    The previous helper returned only the first name, silently dropping a
    co-broker on one imóvel in eight.
    """
    row = by_quirk["multi_corretor"]
    assert len(row["Corretor"]) >= 2
    imovel = vista_to_imovel(listing=row)
    assert len(imovel.corretores) == len(row["Corretor"])
    assert all(c.nome for c in imovel.corretores)


def test_corretor_empty_list_shape_does_not_explode(by_quirk):
    """16/1919 rows send `Corretor: []` instead of a dict."""
    row = by_quirk["corretor_lista_vazia"]
    assert row["Corretor"] == []
    assert vista_to_imovel(listing=row).corretores == []


# ─── The banheiros bug — a flag was being read as a count ─────────────────


def test_banheiro_social_is_a_bool_both_ways(by_quirk):
    """`BanheiroSocial` is "Sim"/"Nao", and was fed to an int coercion.

    That threw internally and returned None, so `banheiros` was None on
    1919/1919 rows — the entire catalog — silently.
    """
    assert vista_to_imovel(listing=by_quirk["banheiro_social_sim"]).banheiro_social is True
    assert vista_to_imovel(listing=by_quirk["banheiro_social_nao"]).banheiro_social is False


# ─── W11 — codes are not ONE-prefixed ─────────────────────────────────────


def test_non_one_prefixed_code_is_modelled(by_quirk):
    row = by_quirk["codigo_nao_one"]
    assert not row["Codigo"].startswith("ONE")
    assert vista_to_imovel(listing=row).codigo == row["Codigo"]


# ─── Geo — absent on 36.8%, so the UI needs a branch ──────────────────────


def test_missing_geo_is_none_and_flagged(by_quirk):
    row = by_quirk["sem_geo"]
    assert row["Latitude"] == ""
    imovel = vista_to_imovel(listing=row)
    assert imovel.latitude is None and imovel.longitude is None
    assert imovel.tem_geo is False


# ─── W4 — finalidade, from the right source ───────────────────────────────


def test_finalidade_from_status_when_detalhes_absent(by_quirk):
    """A listar-only row has no `FinalidadeStatus`, so `Status` must answer."""
    imovel = vista_to_imovel(listing=by_quirk["venda_e_aluguel"])
    assert imovel.finalidades == frozenset({"venda", "aluguel"})
    assert imovel.para_venda and imovel.para_aluguel


def test_finalidade_status_wins_when_detalhes_present(payloads):
    codigo, detalhes = next(iter(payloads["detalhes"].items()))
    imovel = vista_to_imovel(listing=payloads["detalhes_listar_row"], detalhes=detalhes)
    assert imovel.finalidades, "FinalidadeStatus should have resolved a finalidade"
    assert imovel.finalidades <= {"venda", "aluguel"}


def test_derive_finalidades_prefers_status_over_the_finalidade_field():
    """`Finalidade` carries audience (Residencial), not transaction."""
    assert derive_finalidades(status="Venda", finalidade="Residencial") == frozenset({"venda"})


# ─── W12 / W5 / W6 — the amenity schema ───────────────────────────────────


def test_caracteristicas_is_a_fixed_76_key_schema(payloads):
    _, detalhes = next(iter(payloads["detalhes"].items()))
    assert len(detalhes["Caracteristicas"]) == 76
    assert set(detalhes["Caracteristicas"].values()) <= {"Sim", "Nao"}


def test_only_sim_amenities_land_in_the_slug_set(payloads):
    _, detalhes = next(iter(payloads["detalhes"].items()))
    raw = detalhes["Caracteristicas"]
    expected = sum(1 for v in raw.values() if v == "Sim")
    slugs = parse_caracteristicas(raw)
    # Slugs can be fewer than "Sim" count iff a collision pair is both-Sim.
    assert 0 < len(slugs) <= expected


def test_slug_collapses_vistas_inserted_acronym_spaces():
    """W5 — Vista de-camelizes its own keys mid-acronym."""
    assert caracteristica_slug("Sala T V") == "salatv"
    assert caracteristica_slug("T V Cabo") == "tvcabo"
    assert caracteristica_slug("W C Empregada") == "wcempregada"


def test_the_one_known_collision_pair_merges_rather_than_dropping():
    """W6 — both spellings are the same amenity with a tenant typo.

    Exactly one collision exists in the 76-key space. They must resolve to
    the same slug (merge with OR), which is what makes "has a maid's room"
    answerable without picking a winner.
    """
    a = caracteristica_slug("Dependenciade Empregada")
    b = caracteristica_slug("Dependencia De Empregada")
    assert a == b
    assert parse_caracteristicas({"Dependenciade Empregada": "Nao",
                                  "Dependencia De Empregada": "Sim"}) == frozenset({a})


def test_tem_caracteristica_accepts_raw_or_slugged_key(payloads):
    _, detalhes = next(iter(payloads["detalhes"].items()))
    imovel = vista_to_imovel(listing=payloads["detalhes_listar_row"], detalhes=detalhes)
    sim_key = next(k for k, v in detalhes["Caracteristicas"].items() if v == "Sim")
    assert imovel.tem_caracteristica(sim_key) is True
    assert imovel.tem_caracteristica(caracteristica_slug(sim_key)) is True


# ─── normalize_place_name — the cidade/empreendimento casing collision ────
#
# Every case below is a real live value (roadmap
# `social-wiring-imoveis-vista-2026-08`, Q4-extended 2026-08-13), not a
# synthetic one — same discipline as the fixture-driven tests above: the
# wire does things nobody would invent (here: two OPPOSITE casing defects
# in the same 18-value city set).


def test_the_two_live_cidade_collision_pairs_merge_to_one_spelling():
    """The measured collision: 76 imóveis split 57/19 across two spellings
    of the same city. Both sides must resolve to the connective-lowered
    form — dropping either would hide a quarter of that city's inventory
    from a filter keyed on the other spelling."""
    assert normalize_place_name("Embu das Artes") == "Embu das Artes"
    assert normalize_place_name("Embu Das Artes") == "Embu das Artes"


def test_the_two_live_empreendimento_collision_pairs_merge_to_one_spelling():
    """26 imóveis across two empreendimentos, each split between a Roman
    numeral (II/III) and the naive-title-case shape that produced it
    (Ii/Iii)."""
    assert (
        normalize_place_name("Granja Viana II - Gleba 1 e 2 - Km 26")
        == "Granja Viana II - Gleba 1 e 2 - Km 26"
    )
    assert (
        normalize_place_name("Granja Viana Ii - Gleba 1 e 2 - Km 26")
        == "Granja Viana II - Gleba 1 e 2 - Km 26"
    )
    assert (
        normalize_place_name("Paisagem Renoir II e III - Km 26")
        == "Paisagem Renoir II e III - Km 26"
    )
    assert (
        normalize_place_name("Paisagem Renoir Ii e Iii - Km 26")
        == "Paisagem Renoir II e III - Km 26"
    )


# The other 16 live `Cidade` values (roadmap: 18 distinct total, 1
# collision pair = 17 real cities; this is the un-collided 16). Every one
# must be a no-op — this is the "fixes 3 rows, doesn't break 30" proof.
LIVE_CIDADE_VALUES = [
    "Cotia",
    "Carapicuíba",
    "Vargem Grande Paulista",
    "Barueri",
    "Guarujá",
    "Osasco",
    "Santana de Parnaíba",
    "São Paulo",
    "Itapecerica da Serra",
    "Itapevi",
    "Jandira",
    "Ilhabela",
    "São Roque",
    "Ibiúna",
    "Vinhedo",
]


@pytest.mark.parametrize("cidade", LIVE_CIDADE_VALUES)
def test_every_other_live_cidade_value_is_a_no_op(cidade):
    """Accented and connective-bearing city names alike must round-trip
    unchanged — `Carapicuíba`/`Guarujá`/`Ibiúna` (accents), `Santana de
    Parnaíba`/`Itapecerica da Serra` (mid-name connectives), `Vargem Grande
    Paulista` (plain multi-word)."""
    assert normalize_place_name(cidade) == cidade


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("I", "I"), ("ii", "II"), ("III", "III"), ("iv", "IV"), ("V", "V"),
        ("vi", "VI"), ("vii", "VII"), ("VIII", "VIII"), ("ix", "IX"), ("x", "X"),
    ],
)
def test_roman_numerals_i_to_x_always_uppercase(raw, expected):
    assert normalize_place_name(f"Bloco {raw}") == f"Bloco {expected}"


def test_connective_in_first_position_is_not_lowered():
    """`"Do Carmo"` must not become `"do Carmo"` — a leading connective is
    still the start of how the place is written."""
    assert normalize_place_name("Do Carmo") == "Do Carmo"
    assert normalize_place_name("do Carmo") == "Do Carmo"


def test_connective_mid_name_is_lowered_regardless_of_input_casing():
    assert normalize_place_name("Chácara Da Barra") == "Chácara da Barra"
    assert normalize_place_name("Chácara da Barra") == "Chácara da Barra"


@pytest.mark.parametrize(
    "value",
    LIVE_CIDADE_VALUES
    + [
        "Embu das Artes",
        "Embu Das Artes",
        "Granja Viana II - Gleba 1 e 2 - Km 26",
        "Granja Viana Ii - Gleba 1 e 2 - Km 26",
        "Paisagem Renoir II e III - Km 26",
        "Paisagem Renoir Ii e Iii - Km 26",
        "Do Carmo",
    ],
)
def test_normalize_place_name_is_idempotent(value):
    once = normalize_place_name(value)
    assert normalize_place_name(once) == once


def test_normalize_place_name_handles_none_and_blank():
    assert normalize_place_name(None) is None
    assert normalize_place_name("") is None
    assert normalize_place_name("   ") is None


# ─── The listar/detalhes merge ────────────────────────────────────────────


def test_detalhes_never_erases_listar_only_fields(payloads):
    """`FotoDestaque` and `BanheiroSocial` exist ONLY on listar.

    A naive `{**listar, **detalhes}` merge drops them on every imóvel,
    because detalhes simply has no such key — and if detalhes ever sends
    them blank, an unguarded overlay would blank a populated value.
    """
    listing = payloads["detalhes_listar_row"]
    codigo, detalhes = next(iter(payloads["detalhes"].items()))
    merged = merge_vista_payloads(listing, detalhes)
    assert merged["FotoDestaque"] == listing["FotoDestaque"]
    assert merged["BanheiroSocial"] == listing["BanheiroSocial"]
    # and detalhes-only fields survive too
    assert "Caracteristicas" in merged and "Numero" in merged


def test_full_merge_produces_a_complete_imovel(payloads):
    listing = payloads["detalhes_listar_row"]
    codigo, detalhes = next(iter(payloads["detalhes"].items()))
    imovel = vista_to_imovel(listing=listing, detalhes=detalhes)
    assert imovel.codigo == codigo
    assert imovel.foto_destaque, "listar-only field lost"
    assert imovel.caracteristicas, "detalhes-only field lost"
    assert imovel.numero is not None, "detalhes-only field lost"


def test_every_fixture_row_round_trips(payloads):
    """No fixture row may raise — these are all real, live listings."""
    for row in payloads["listar"]:
        imovel = vista_to_imovel(listing=row)
        assert isinstance(imovel, Imovel)
        assert imovel.codigo == row["Codigo"]
        assert imovel.vista_raw, "raw payload must be preserved for audit"


def test_payload_without_codigo_raises_rather_than_returning_a_blank(by_quirk):
    """An imóvel with no identity is broken, not partial — fail loudly."""
    with pytest.raises(ValueError, match="no `Codigo`"):
        vista_to_imovel(listing={"Categoria": "Casa"})


# ─── Coercion helpers, directly ───────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [("0", None), ("", None), (None, None), ("4980000", 4980000.0), ("1.5", 1.5)],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw,expected", [("0", 0), ("", None), (None, None), ("4", 4)])
def test_parse_count_keeps_zero(raw, expected):
    assert parse_count(raw) == expected


@pytest.mark.parametrize("raw,expected", [("0", None), ("109.28", 109.28), ("", None)])
def test_parse_area_nulls_zero(raw, expected):
    assert parse_area(raw) == expected


@pytest.mark.parametrize(
    "raw,expected", [("Sim", True), ("Nao", False), ("Não", False), ("", None), (None, None)]
)
def test_parse_sim_nao(raw, expected):
    assert parse_sim_nao(raw) is expected


def test_endereco_completo_composes_the_split_parts():
    imovel = Imovel(codigo="ONE1", logradouro="Fernando Nobre", numero="4000", complemento="389")
    assert imovel.endereco_completo == "Fernando Nobre, 4000, 389"
