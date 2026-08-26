"""The roteiro cronograma PDF — one imóvel per page, in visiting order.

HOW A PDF IS ASSERTED WITHOUT A PDF PARSER
------------------------------------------
`reportlab` writes, it does not read, and this product has no PDF reader
dependency. So the page count is asserted off the document's own catalogue —
every PDF carries `/Type /Pages ... /Count N` — and the content off the raw
byte stream, which is uncompressed for these documents. That is a real
assertion, not a smoke test: a layout change that dropped a page or a field
fails it.

The one thing it cannot see is where on the page something landed. That is the
honest limit of testing a PDF this way, and it is stated rather than implied.
"""
from __future__ import annotations

import re

import pytest

from app.modules.card_hub import roteiro_pdf_service as svc

pytest.importorskip(
    "reportlab",
    reason="reportlab>=4.0.0 is declared in requirements.txt — install it to run "
    "the PDF tests; skipping here would hide a broken generator.",
)


@pytest.fixture(autouse=True)
def _texto_legivel():
    """reportlab zlib-compresses page content streams by default, which hides
    every drawn string from a byte assertion. Turning compression off is a
    TEST-TIME global on `rl_config` — production output is untouched, and the
    alternative (adding a PDF parser dependency just to read our own writes)
    is a heavier price for the same assertion.
    """
    from reportlab import rl_config

    anterior = rl_config.pageCompression
    rl_config.pageCompression = 0
    yield
    rl_config.pageCompression = anterior


def _visita(codigo: str, ordem: int, **imovel) -> dict:
    base = {
        "codigo": codigo,
        "titulo": f"Apartamento {codigo}",
        "empreendimento": "Edifício Aurora",
        "logradouro": "Rua das Palmeiras",
        "numero": "320",
        "complemento": "apto 91",
        "bairro": "Centro",
        "cidade": "Florianópolis",
        "uf": "SC",
        "cep": "88010-000",
        "foto_destaque": None,
        "corretores": [{"nome": "Ana Prado", "email": "ana@example.com"}],
        "captacao": None,
        "ativo_no_vista": True,
        "fonte": "imoveis",
    }
    base.update(imovel)
    return {
        "id": f"v-{ordem}",
        "roteiro_id": "r-1",
        "codigo": codigo,
        "ordem": ordem,
        "status": "pendente",
        "observacao": None,
        "feedback_em": None,
        "created_at": "2026-08-25T12:00:00+00:00",
        "imovel": base,
    }


def _roteiro(*visitas, titulo=None) -> dict:
    return {
        "id": "3f5c2d69-0000-0000-0000-000000000001",
        "atendimento_id": "a-1",
        "titulo": titulo,
        "created_at": "2026-08-25T12:00:00+00:00",
        "visitas": list(visitas),
        "contagem": {
            "total": len(visitas), "realizadas": 0, "nao_realizadas": 0,
            "pendentes": len(visitas),
        },
    }


def _page_count(pdf: bytes) -> int:
    """The page tree's own `/Count`.

    Matched on `/Count` alone rather than anchored after `/Type /Pages`:
    reportlab writes dictionary keys in ALPHABETICAL order, so the real output
    is `/Count 3 /Kids [...] /Type /Pages` — an anchored regex silently matches
    nothing and the assertion below is what caught that.
    """
    assert re.search(rb"/Type\s*/Pages", pdf), "no page tree in the output"
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", pdf)]
    assert counts, "page tree carries no /Count"
    return max(counts)


class TestEstrutura:
    def test_is_a_pdf(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0)))
        assert pdf.startswith(b"%PDF-")

    def test_one_page_per_imovel(self):
        """🔴 The user's words: One property per page."""
        pdf = svc.gerar(
            _roteiro(_visita("ONE9001", 0), _visita("ONE9002", 1), _visita("ONE9003", 2))
        )
        assert _page_count(pdf) == 3

    def test_an_empty_roteiro_is_refused_not_a_blank_file(self):
        """A zero-page PDF is a corrupt file, not an empty state."""
        with pytest.raises(Exception) as exc:
            svc.gerar(_roteiro())
        assert getattr(exc.value, "status_code", None) == 400

    def test_filename_is_stable_and_scoped_to_the_roteiro(self):
        assert svc.nome_arquivo(_roteiro(_visita("ONE9001", 0))) == "roteiro-3f5c2d69.pdf"


class TestConteudo:
    """The four data points the user named, and nothing invented."""

    def test_carries_every_codigo_in_order(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0), _visita("ONE9002", 1)))
        assert pdf.index(b"ONE9001") < pdf.index(b"ONE9002")

    def test_carries_condominio_and_endereco(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0)))
        assert b"Aurora" in pdf
        assert b"Palmeiras" in pdf
        assert b"320" in pdf

    def test_owner_fields_render_as_blank_not_as_absent(self):
        """D1 — user-ratified 2026-08-25. Vista exposes no proprietário, so the
        LABEL still prints with an em-dash: a corretor must see that the field
        exists and is unknown, not wonder whether the report dropped it.
        Destination for the real data: `imovel_dados` (migration 075)."""
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0)))
        assert b"PROPRIET" in pdf.upper()
        assert b"CELULAR" in pdf.upper()

    def test_no_photo_is_embedded(self):
        """The user named four data points and a photo is not among them;
        fetching remote images server-side would add a failure mode this
        document does not need."""
        pdf = svc.gerar(
            _roteiro(_visita("ONE9001", 0, foto_destaque="https://cdn.example/x.jpg"))
        )
        # `/Subtype /Image`, NOT a bare `/Image`: every reportlab document
        # declares `/ProcSet [/PDF /Text /ImageB /ImageC /ImageI]` as
        # boilerplate, so the loose substring matches a document with no image
        # in it at all — a false failure that says nothing.
        assert b"/Subtype /Image" not in pdf
        assert b"cdn.example" not in pdf


class TestCaptacao:
    def test_prefers_the_imovel_dados_captador(self):
        """`captador_user_id` (075) is the canonical model and outranks the
        Vista corretor list."""
        pdf = svc.gerar(
            _roteiro(
                _visita("ONE9001", 0, captacao={"id": "u-1", "nome": "Bruno Sales"})
            )
        )
        assert b"Bruno Sales" in pdf
        assert b"Ana Prado" not in pdf

    def test_falls_back_to_every_vista_corretor_not_just_the_first(self):
        """13.1% of the catalog carries 2–3 corretores (040's census) and a
        first-only read discards the rest."""
        pdf = svc.gerar(
            _roteiro(
                _visita(
                    "ONE9001", 0,
                    corretores=[{"nome": "Ana Prado"}, {"nome": "Caio Lima"}],
                )
            )
        )
        assert b"Ana Prado" in pdf
        assert b"Caio Lima" in pdf

    def test_no_captador_anywhere_renders_blank(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0, corretores=[])))
        assert pdf.startswith(b"%PDF-")


class TestImovelDelistado:
    def test_renders_from_the_registry_snapshot_and_says_so(self):
        """A sold imóvel keeps its page. The registry snapshot has no street,
        so the endereço prints what it has without stray separators — and the
        page states the property has left the catalog, which a corretor needs
        before driving there."""
        pdf = svc.gerar(
            _roteiro(
                _visita(
                    "ONE4770", 0,
                    empreendimento=None, logradouro=None, numero=None,
                    complemento=None, cep=None, corretores=[],
                    bairro="Trindade", cidade="Florianópolis", uf="SC",
                    ativo_no_vista=False, fonte="registry",
                )
            )
        )
        assert _page_count(pdf) == 1
        assert b"ONE4770" in pdf
        assert b"Trindade" in pdf
        assert b"cat" in pdf  # "fora do catálogo Vista"


class TestCabecalho:
    def test_titulo_falls_back_to_the_creation_date(self):
        pdf = svc.gerar(_roteiro(_visita("ONE9001", 0)))
        assert b"25/08/2026" in pdf

    def test_cliente_name_rides_along_when_given(self):
        pdf = svc.gerar(
            _roteiro(_visita("ONE9001", 0), titulo="Terca de manha"),
            cliente_nome="Marina Souza",
        )
        assert b"Marina Souza" in pdf
        assert b"Terca de manha" in pdf
