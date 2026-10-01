"""The roteiro cronograma PDF (xhtml2pdf via `render_html_pdf`) — one imóvel per page.

Asserted by PARSING the produced PDF with PyMuPDF (`fitz`, already a declared
dependency): real page count and real extracted text, not byte greps.
"""
from __future__ import annotations

import httpx
import pytest

from app.modules.card_hub import roteiro_pdf_service as svc

fitz = pytest.importorskip("fitz", reason="PyMuPDF is a declared requirement")
pytest.importorskip("xhtml2pdf", reason="xhtml2pdf is a declared requirement")

def _png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


def _texto(pdf: bytes) -> list[str]:
    doc = fitz.open(stream=pdf, filetype="pdf")
    return [p.get_text() for p in doc]


def _visita(codigo: str, ordem: int, **imovel) -> dict:
    base = {
        "codigo": codigo, "titulo": f"Apartamento {codigo}",
        "empreendimento": "Edifício Aurora", "logradouro": "Rua das Palmeiras",
        "numero": "320", "complemento": "apto 91", "bairro": "Centro",
        "cidade": "Florianópolis", "uf": "SC", "cep": "88010-000",
        "foto_destaque": None,
        "corretores": [{"nome": "Ana Prado"}], "captacao": None,
        "ativo_no_vista": True, "fonte": "imoveis",
        "categoria": "Apartamento", "valor": 1234567.5, "valor_tipo": "venda",
        "dormitorios": 3, "suites": 1, "vagas": 2,
        "area_privativa": 85, "area_total": 120.5,
    }
    base.update(imovel)
    return {"id": f"v-{ordem}", "roteiro_id": "r-1", "codigo": codigo, "ordem": ordem,
            "status": "pendente", "observacao": None, "feedback_em": None,
            "created_at": "2026-08-25T12:00:00+00:00", "imovel": base}


def _roteiro(*visitas, titulo=None, data_visita="2026-10-15") -> dict:
    return {"id": "3f5c2d69-0000-0000-0000-000000000001", "atendimento_id": "a-1",
            "titulo": titulo, "data_visita": data_visita,
            "created_at": "2026-08-25T12:00:00+00:00", "visitas": list(visitas)}


class TestEstrutura:
    def test_one_page_per_imovel(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0), _visita("ONE9002", 1), _visita("ONE9003", 2)))
        assert pdf.startswith(b"%PDF-")
        assert len(_texto(pdf)) == 3

    def test_single_imovel_is_one_page(self):
        assert len(_texto(svc.gerar(_roteiro(_visita("ONE9001", 0))))) == 1

    def test_pages_follow_visitas_ordem_not_list_order(self):
        paginas = _texto(svc.gerar(_roteiro(_visita("ONE9002", 1), _visita("ONE9001", 0))))
        assert "ONE9001" in paginas[0] and "ONE9002" in paginas[1]

    def test_empty_roteiro_is_refused(self):
        with pytest.raises(Exception) as exc:
            svc.gerar(_roteiro())
        assert getattr(exc.value, "status_code", None) == 400


class TestNomeArquivo:
    def test_includes_data_visita(self):
        assert svc.nome_arquivo(_roteiro(data_visita="2026-10-15")) == "roteiro-3f5c2d69-2026-10-15.pdf"

    def test_without_date_has_no_date_part(self):
        assert svc.nome_arquivo(_roteiro(data_visita=None)) == "roteiro-3f5c2d69.pdf"


class TestConteudo:
    def test_header_fields(self):
        p = _texto(svc.gerar(_roteiro(_visita("ONE9001", 0), _visita("ONE9002", 1), titulo="Terça de manhã"),
                             cliente_nome="Marina Souza"))[1]
        for s in ("Terça de manhã", "Marina Souza", "15/10/2026", "Imóvel 2 de 2", "ONE9002"):
            assert s in p

    def test_technical_data(self):
        p = _texto(svc.gerar(_roteiro(_visita("ONE9001", 0))))[0]
        for s in ("Apartamento", "Rua das Palmeiras 320", "apto 91", "Centro", "Florianópolis/SC",
                  "R$ 1.234.567,50", "3 dorm.", "1 suítes", "2 vagas", "85 m²", "120,5 m²",
                  "Edifício Aurora", "Ana Prado"):
            assert s in p, s

    def test_missing_additive_keys_render_dash_not_crash(self):
        v = _visita("ONE9001", 0)
        for k in ("categoria", "valor", "valor_tipo", "dormitorios", "suites", "vagas",
                  "area_privativa", "area_total"):
            v["imovel"].pop(k)
        p = _texto(svc.gerar(_roteiro(v)))[0]
        assert "—" in p and "ONE9001" in p

    def test_valor_falls_back_to_valor_venda_then_locacao(self):
        v = _visita("ONE9001", 0, valor=None, valor_tipo=None, valor_venda=None, valor_locacao=2500)
        assert "R$ 2.500,00 /mês" in _texto(svc.gerar(_roteiro(v)))[0]

    def test_form_blocks_present(self):
        p = _texto(svc.gerar(_roteiro(_visita("ONE9001", 0))))[0]
        for s in ("Visita realizada", "Sim", "Não", "Assinatura", "Gerou proposta?", "Proposta:",
                  "Permuta", "Financiamento", "FGTS", "PROPRIETÁRIO"):
            assert s in p, s

    def test_proprietarios_listed_else_dash(self):
        pdf = svc.gerar(
            _roteiro(_visita("ONE9001", 0), _visita("ONE9002", 1)),
            proprietarios_por_codigo={"one9001": [{"nome": "Carlos Dono", "documento": "123.456.789-09",
                                                   "tipo_pessoa": "PF"}]},
        )
        p0, p1 = _texto(pdf)
        assert "Carlos Dono" in p0 and "123.456.789-09" in p0
        assert "Carlos Dono" not in p1

    def test_html_in_data_is_escaped(self):
        p = _texto(svc.gerar(_roteiro(_visita("ONE9001", 0, titulo="<b>X</b> & Y"))))[0]
        assert "<b>X</b> & Y" in p

    def test_emoji_in_text_does_not_break_rendering(self):
        assert len(_texto(svc.gerar(_roteiro(_visita("ONE9001", 0), titulo="Roteiro 🏠")))) == 1

    def test_delisted_imovel_renders_and_says_so(self):
        v = _visita("ONE4770", 0, empreendimento=None, logradouro=None, numero=None, complemento=None,
                    corretores=[], bairro="Trindade", ativo_no_vista=False, fonte="registry")
        p = _texto(svc.gerar(_roteiro(v)))[0]
        assert "Trindade" in p and "catálogo Vista" in p


class TestFotos:
    def test_embedded_photo_is_an_image_and_no_placeholder(self):
        uri = "data:image/png;base64," + __import__("base64").b64encode(PNG).decode()
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0)), fotos_por_codigo={"ONE9001": uri})
        doc = fitz.open(stream=pdf, filetype="pdf")
        assert doc[0].get_images()
        assert "foto indisponível" not in doc[0].get_text()

    def test_missing_photo_renders_visible_placeholder(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0)))
        doc = fitz.open(stream=pdf, filetype="pdf")
        assert not doc[0].get_images()
        assert "foto indisponível" in doc[0].get_text()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestCarregarFotos:
    IMOVEIS = [{"codigo": "one9001", "foto_destaque": "https://cdn.example/a.png"}]

    def test_success_builds_data_uri_keyed_by_canonical_codigo(self):
        c = _client(lambda r: httpx.Response(200, content=PNG, headers={"content-type": "image/png"}))
        out = svc.carregar_fotos(self.IMOVEIS, client=c)
        assert out["ONE9001"].startswith("data:image/png;base64,")

    def test_falls_back_to_first_of_fotos(self):
        c = _client(lambda r: httpx.Response(200, content=PNG, headers={"content-type": "image/png"}))
        out = svc.carregar_fotos([{"codigo": "A1", "fotos": [{"url": "https://x/y.png"}]}], client=c)
        assert "A1" in out

    @pytest.mark.parametrize("resp", [
        httpx.Response(404),
        httpx.Response(200, content=b"<html/>", headers={"content-type": "text/html"}),
        httpx.Response(200, content=b"x" * (svc.FOTO_MAX_BYTES + 1), headers={"content-type": "image/png"}),
        httpx.Response(200, content=b"", headers={"content-type": "image/png"}),
    ])
    def test_failures_are_missing_key_and_logged(self, resp, caplog):
        with caplog.at_level("WARNING"):
            out = svc.carregar_fotos(self.IMOVEIS, client=_client(lambda r: resp))
        assert out == {}
        assert "ONE9001" in caplog.text

    def test_network_error_is_missing_key_and_logged(self, caplog):
        def boom(request):
            raise httpx.ConnectTimeout("slow", request=request)
        with caplog.at_level("WARNING"):
            assert svc.carregar_fotos(self.IMOVEIS, client=_client(boom)) == {}
        assert "ONE9001" in caplog.text

    def test_non_http_scheme_is_never_fetched(self):
        calls = []
        c = _client(lambda r: calls.append(r) or httpx.Response(200))
        assert svc.carregar_fotos([{"codigo": "A1", "foto_destaque": "file:///etc/passwd"}], client=c) == {}
        assert calls == []
