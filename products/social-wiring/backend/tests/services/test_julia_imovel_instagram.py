"""Julia S6: Instagram post/reel link -> mapped listing (`julia_imovel_instagram` + `julia_ferramentas_service._resolver_instagram`)."""
from uuid import uuid4

import pytest

from app.services import julia_ferramentas_service as ferr, julia_imovel_instagram as ig


@pytest.mark.parametrize("texto,esperado", [
    ("https://www.instagram.com/p/C8abcDEF123/", ["C8abcDEF123"]),
    ("https://instagram.com/reel/Cx-_9zYQW12/?igsh=abc&utm_source=qr", ["Cx-_9zYQW12"]),
    ("olha esse https://www.instagram.com/imobiliaria/reel/DAbc12345/ aqui", ["DAbc12345"]),
    ("https://www.instagram.com/reels/DAbc12345", ["DAbc12345"]),
    ("https://m.instagram.com/p/AAAAA11111/?hl=pt", ["AAAAA11111"]),
    ("https://www.instagram.com/p/AAAAA11111/ e https://www.instagram.com/p/AAAAA11111/", ["AAAAA11111"]),
    ("https://www.instagram.com/imobiliaria/", []),
    ("https://example.com/p/AAAAA11111/", []),
    ("sem link nenhum", []),
])
def test_analisar_shortcodes(texto, esperado):
    assert ig.analisar(texto)[0] == esperado


def test_share_link_is_flagged_not_mapped():
    assert ig.analisar("https://www.instagram.com/share/p/BAbCdEfGh/") == ([], True)
    assert ig.analisar("https://www.instagram.com/share/reel/BAbCdEfGh") == ([], True)


class _Q:
    def __init__(self, rows):
        self.rows = rows
        self.f = {}

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.f[k] = v
        return self

    def in_(self, k, vs):
        self.f[k] = list(vs)
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = [x for x in self.rows if x["org_id"] == self.f["org_id"] and x["shortcode"] in self.f["shortcode"]]
        return r


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def table(self, nome):
        assert nome == ig.T
        return _Q(self.rows)


class _Catalogo:
    def __init__(self, linhas):
        self.linhas = linhas

    def um(self, codigo):
        return self.linhas.get(codigo)


def test_codigos_is_org_scoped():
    org, outra = uuid4(), uuid4()
    c = _Client([{"org_id": str(org), "shortcode": "AAAAA11111", "codigo_imovel": "AP1"},
                 {"org_id": str(outra), "shortcode": "BBBBB22222", "codigo_imovel": "AP2"}])
    assert ig.codigos(c, org, ["AAAAA11111", "BBBBB22222"]) == ["AP1"]
    assert ig.codigos(c, org, []) == []


def test_resolver_instagram_mapped_and_unmapped():
    org = uuid4()
    c = _Client([{"org_id": str(org), "shortcode": "AAAAA11111", "codigo_imovel": "AP1"}])
    cat = _Catalogo({"AP1": {"codigo": "AP1"}})
    ok = ferr._resolver_instagram(c, org, cat, "https://www.instagram.com/reel/AAAAA11111/?igsh=x")
    assert ok["encontrado"] and ok["via"] == "instagram" and ok["codigo"] == "AP1"
    nada = ferr._resolver_instagram(c, org, cat, "https://www.instagram.com/p/ZZZZZ99999/")
    assert nada == {"encontrado": False, "candidatos": [], "motivo": ig.SEM_MAPEAMENTO}
    comp = ferr._resolver_instagram(c, org, cat, "https://www.instagram.com/share/p/BAbCdEfGh/")
    assert comp["motivo"] == ig.LINK_COMPARTILHADO
    assert ferr._resolver_instagram(c, org, cat, "AP0042") is None


def test_mapped_to_unpublished_listing_is_not_found():
    org = uuid4()
    c = _Client([{"org_id": str(org), "shortcode": "AAAAA11111", "codigo_imovel": "GONE"}])
    r = ferr._resolver_instagram(c, org, _Catalogo({}), "https://www.instagram.com/p/AAAAA11111/")
    assert r["encontrado"] is False and r["motivo"] == ig.SEM_MAPEAMENTO
