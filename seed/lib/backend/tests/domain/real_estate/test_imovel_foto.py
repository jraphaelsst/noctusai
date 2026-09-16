"""`ImovelFoto` / `parse_imovel_fotos` — the S7 read-only photo gallery.

Contract proven live 2026-09-16 against tenant `CA2830` (200, 28 photos)
via `GET /imoveis/detalhes?imovel=<codigo>&pesquisa={"fields":["Codigo",
{"Foto":["Codigo","Foto","FotoPequena","Destaque","Tipo","Descricao"]}]}`.

`Foto` is dict-keyed by photo code on the wire — same shape trap as
`Corretor`. These tests exercise the normalizer directly (a fixture shaped
exactly like the real payload) rather than the Vista transport, per
`KB § PATTERNS/backend/seed-fake-real-adapter.md`.
"""

from __future__ import annotations

from noctusai_lib.domain.real_estate.imovel import ImovelFoto, parse_imovel_fotos


def test_dict_keyed_payload_normalizes_to_a_list():
    """`Foto` arrives keyed by photo code, not as a list — indexing it
    directly (`payload["Foto"][0]`) would silently yield a dict KEY (a
    string), not a photo. `parse_imovel_fotos` must never do that."""
    raw = {
        "10": {
            "Codigo": "10",
            "Foto": "https://cdn.example/10.jpg",
            "FotoPequena": "https://cdn.example/10_thumb.jpg",
            "Destaque": "Nao",
            "Tipo": "Fachada",
            "Descricao": "Fachada principal",
        },
        "11": {
            "Codigo": "11",
            "Foto": "https://cdn.example/11.jpg",
            "FotoPequena": "https://cdn.example/11_thumb.jpg",
            "Destaque": "Sim",
            "Tipo": "Sala",
            "Descricao": "Sala de estar",
        },
    }
    fotos = parse_imovel_fotos(raw)
    assert isinstance(fotos, list)
    assert all(isinstance(f, ImovelFoto) for f in fotos)
    assert {f.codigo for f in fotos} == {"10", "11"}


def test_destaque_string_sim_coerces_to_bool_true():
    """`Destaque` arrives as the STRING "Sim" on exactly one photo — must
    be coerced to an explicit bool, never left as the raw string."""
    raw = {"1": {"Codigo": "1", "Foto": "u1", "Destaque": "Sim"}}
    fotos = parse_imovel_fotos(raw)
    assert fotos[0].destaque is True
    assert isinstance(fotos[0].destaque, bool)


def test_destaque_string_nao_coerces_to_bool_false():
    raw = {"1": {"Codigo": "1", "Foto": "u1", "Destaque": "Nao"}}
    fotos = parse_imovel_fotos(raw)
    assert fotos[0].destaque is False


def test_missing_destaque_defaults_to_false_not_none():
    raw = {"1": {"Codigo": "1", "Foto": "u1"}}
    fotos = parse_imovel_fotos(raw)
    assert fotos[0].destaque is False


def test_ordering_is_destaque_first_then_codigo():
    """`codigo` sorts as a STRING (Vista sends it as one) — "30" < "5"
    lexicographically, which is the actual, intended tie-break."""
    raw = {
        "30": {"Codigo": "30", "Foto": "u30", "Destaque": "Nao"},
        "5": {"Codigo": "5", "Foto": "u5", "Destaque": "Nao"},
        "20": {"Codigo": "20", "Foto": "u20", "Destaque": "Sim"},
    }
    fotos = parse_imovel_fotos(raw)
    assert [f.codigo for f in fotos] == ["20", "30", "5"]
    assert fotos[0].destaque is True


def test_field_mapping_matches_the_proven_wire_shape():
    raw = {
        "1": {
            "Codigo": "1",
            "Foto": "https://cdn.example/full.jpg",
            "FotoPequena": "https://cdn.example/thumb.jpg",
            "Destaque": "Sim",
            "Tipo": "Cozinha",
            "Descricao": "Cozinha planejada",
        }
    }
    foto = parse_imovel_fotos(raw)[0]
    assert foto.codigo == "1"
    assert foto.url == "https://cdn.example/full.jpg"
    assert foto.url_thumb == "https://cdn.example/thumb.jpg"
    assert foto.tipo == "Cozinha"
    assert foto.descricao == "Cozinha planejada"


def test_list_shape_is_accepted_too():
    """`Corretor`'s sibling helper accepts both dict AND list shapes —
    `parse_imovel_fotos` mirrors that leniency."""
    raw = [{"Codigo": "1", "Foto": "u1", "Destaque": "Nao"}]
    fotos = parse_imovel_fotos(raw)
    assert len(fotos) == 1
    assert fotos[0].codigo == "1"


def test_non_dict_entries_are_skipped_not_raised():
    raw = {"1": {"Codigo": "1", "Foto": "u1"}, "2": "not-a-photo-dict"}
    fotos = parse_imovel_fotos(raw)
    assert len(fotos) == 1


def test_empty_none_and_wrong_type_all_return_empty_list():
    assert parse_imovel_fotos({}) == []
    assert parse_imovel_fotos(None) == []
    assert parse_imovel_fotos("not-a-payload") == []
    assert parse_imovel_fotos(42) == []
