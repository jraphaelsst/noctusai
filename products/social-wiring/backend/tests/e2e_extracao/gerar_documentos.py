#!/usr/bin/env python3
"""Deterministic generator for the sw-extraction-contract-gate-2026-09 E2E
fixture set: synthetic, fully-fictional PDFs (a text-layer version AND a
scan-like image-only version of each) plus ``esperado.json``, the answer key
``verificar.py`` scores a live database against.

WHY THIS EXISTS
---------------
The roadmap (``project-history/roadmaps/sw-extraction-contract-gate-2026-09.md``)
needs proof that file uploads land 100% of the contract's fields in the right
`clientes` / `imovel_dados` / `imovel_documentos` / `certidao_resultados` /
`matricula_ato_detalhes` columns — for BOTH a document with a real text layer
(the pdfminer.six leg of the extraction ladder) and a scanned, image-only one
(the PyMuPDF-rasterize -> vision leg). One generator producing both variants
from the SAME persona/imóvel facts (``dados.py``) is what keeps the answer
key from drifting away from the documents it describes.

DEPENDENCIES — none new
------------------------
``reportlab`` and ``PyMuPDF`` (``import fitz``) are ALREADY in
``products/social-wiring/backend/requirements.txt`` (the media_service /
certidões PDF pipeline). This script adds no new dependency; it just runs
those two libraries offline, at fixture-authoring time, from a virtualenv
that has them installed (the repo's shared venv does, per the backend's own
`requirements.txt` — a fresh checkout may need
``pip install -r products/social-wiring/backend/requirements.txt``, or just
the two packages, to RUN this generator; the checked-in output under
``fixtures/`` does not require it to be READ).

USAGE
-----
    python gerar_documentos.py [--out DIR]

Writes ``<out>/<id>_texto.pdf``, ``<out>/<id>_scan.pdf`` for every document in
``DOCUMENTOS``, plus ``<out>/esperado.json``. Re-running is idempotent byte-
for-byte (no wall-clock timestamps are embedded — see ``_PDF_DOC_DATE``).
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
import zlib
from pathlib import Path
from typing import Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

import dados as d

# ─── Deterministic seed — used only for the scan-variant's rotation/noise ──
SEED = 20260922

#: Fixed creation date baked into every rendered PDF so re-running this
#: generator produces byte-identical output (no wall-clock in the diff).
_PDF_DOC_DATE = "D:20260922000000Z"

_STYLE_LABEL = ParagraphStyle(
    "campo", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=2
)
_STYLE_HEADING = ParagraphStyle(
    "titulo", fontName="Helvetica-Bold", fontSize=11, leading=15, spaceAfter=6
)
_STYLE_BODY = ParagraphStyle(
    "corpo", fontName="Helvetica", fontSize=9.5, leading=14, spaceAfter=8,
    # LEFT, not justified (alignment=4): a dry-run against the real seed
    # parsers (`noctusai_lib.integrations.documents.*`) showed reportlab's
    # justification widens inter-word spacing on a wrapped line, and
    # pdfminer.six's extraction turns that widening into literal DOUBLE
    # spaces mid-value ("RICARDO  AUGUSTO  FERREIRA  LIMA") — an artifact of
    # THIS renderer, not of a real scanned document or a vision OCR pass.
    alignment=0,
)

_HEADING_MARKERS = (
    "REPÚBLICA FEDERATIVA", "CARTEIRA", "CERTIDÃO", "REGISTRO CIVIL",
    "SECRETARIA", "PREFEITURA", "MINISTÉRIO", "RECEITA FEDERAL",
    "OFÍCIO DE REGISTRO",
)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_heading(line: str) -> bool:
    return any(line.upper().startswith(m) for m in _HEADING_MARKERS)


def render_text_pdf(paragrafos: list[str], titulo_pdf: str) -> bytes:
    """One `Paragraph` per input line — label-anchored parsers read text
    sequentially, not by visual layout, so this is a faithful-enough text
    layer without hand-building a form template."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=titulo_pdf, author="sw-extracao-e2e (fixture — ficticio)",
        # Pins /CreationDate + /ModDate + internal object IDs so re-running
        # this generator on the same inputs produces a BYTE-IDENTICAL PDF —
        # no wall-clock timestamp in the diff.
        invariant=1,
    )
    flow: list[Any] = []
    for line in paragrafos:
        if line == "":
            flow.append(Spacer(1, 8))
            continue
        style = _STYLE_HEADING if _is_heading(line) else (
            _STYLE_BODY if len(line) > 110 else _STYLE_LABEL
        )
        flow.append(Paragraph(_esc(line), style))

    doc.build(flow)
    return buf.getvalue()


def rasterize_as_scan(pdf_bytes: bytes, *, seed: int) -> bytes:
    """Text-layer PDF -> image-only PDF: rasterize every page (PyMuPDF,
    ~144 DPI), apply a small deterministic rotation + sparse speckle noise,
    then rebuild a PDF from the bitmap alone. No text layer survives — this
    is the ladder's vision leg, not its pdfminer leg.
    """
    import fitz  # PyMuPDF — see module docstring; matches app/services/media_service.py's own `import fitz`.

    rng = random.Random(seed)
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    for page in src:
        angle = rng.uniform(-2.5, 2.5)
        mat = fitz.Matrix(2, 2).prerotate(angle)  # ~144 DPI, slight skew
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
        samples = bytearray(pix.samples)
        n_pixels = pix.width * pix.height
        n_noise = max(300, n_pixels // 350)
        for _ in range(n_noise):
            idx = rng.randrange(n_pixels) * pix.n
            shade = rng.randint(50, 160)
            samples[idx : idx + pix.n] = bytes([shade] * pix.n)
        noisy = fitz.Pixmap(pix.colorspace, pix.width, pix.height, bytes(samples), False)
        page_out = out.new_page(width=noisy.width, height=noisy.height)
        page_out.insert_image(page_out.rect, pixmap=noisy)
    out.set_metadata({"title": "", "author": "", "creationDate": _PDF_DOC_DATE})
    result = out.tobytes(deflate=True, garbage=4)
    out.close()
    src.close()
    return result


# ═════════════════════════════════════════════════════════════════════════
# The document catalogue
# ═════════════════════════════════════════════════════════════════════════
#
# Each entry: id / tipo_documento / paragrafos (rendered text) / uploads
# (one dict per upload target: `alvo`, `campos` — the DB column -> expected
# value every upload of THIS document must land) / optional `bonus_campos`
# (fields that land only after an additional human step — e.g. the
# Qualificações-queue "Confirmar" click documented in README.md — reported
# by verificar.py, never counted against the exit code) / optional
# `pending_spec` (fields whose exact target format some future slice has
# not shipped yet — reported as REVIEW, never scored as a miss; unused as
# of the 2026-09-23 reconciliation against the merged wave-1 slices, kept
# for the next genuinely-unresolved field rather than removed).

R, C, F = d.RICARDO, d.CAMILA, d.FERNANDO
IL, IH = d.IMOVEL_LIVRE, d.IMOVEL_HIPOTECA


def _doc_titular_rg() -> dict:
    p = R
    paragrafos = [
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "SECRETARIA DE SEGURANÇA PÚBLICA",
        "CARTEIRA DE IDENTIDADE",
        "",
        f"REGISTRO GERAL: {p.rg} {p.rg_orgao}",
        f"NOME: {p.nome}",
        "SEXO: M",
        "FILIAÇÃO",
        f"PAI: {p.pai}",
        f"MAE: {p.mae}",
        f"NATURALIDADE: {p.naturalidade}",
        f"DATA DE NASCIMENTO: {p.nascimento_extenso}",
        f"CPF: {p.cpf}",
        "DOC. ORIGEM: LIVRO 123 FOLHA 45 SÃO PAULO/SP",
    ]
    return {
        "id": "titular_rg",
        "descricao": "RG (modelo antigo) — Ricardo, titular",
        "tipo_documento": "rg",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": "cliente:titular",
            "campos": {
                "clientes.nome_oficial": p.nome,
                "clientes.data_nascimento": p.nascimento_iso,
                "clientes.genero": "Masculino",
                "clientes.cpf": p.cpf,
                "clientes.rg": p.rg,
                "clientes.rg_orgao_expedidor": p.rg_orgao,
            },
        }],
    }


def _doc_conjuge_cin() -> dict:
    p = C
    paragrafos = [
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "CARTEIRA DE IDENTIDADE NACIONAL",
        "",
        f"NOME: {p.nome}",
        "SEXO: F",
        f"DATA DE NASCIMENTO: {p.nascimento_extenso}",
        f"NATURALIDADE: {p.naturalidade}",
        f"CPF: {p.cpf}",
        f"REGISTRO GERAL: {p.rg} {p.rg_orgao}",
        # FILIAÇÃO comes AFTER cpf/rg — not immediately before it — so the
        # holder's own CPF is never within the label-lookback window of a
        # FILIAÇÃO/PAI/MAE block-opener decoy (see gerar_documentos.py's
        # dry-run note on `titular_rg`'s equivalent ordering; a CPF line
        # placed right after MAE gets DEMOTED to baixa confidence by
        # cpf.py's own block-opener guard — real behaviour, not a defect,
        # so the fixture avoids the layout that triggers it, same as most
        # real CIN/RG cards print CPF near the top anyway).
        "FILIAÇÃO",
        f"PAI: {p.pai}",
        f"MAE: {p.mae}",
        "DOC. ORIGEM: RG SSP/SP",
    ]
    return {
        "id": "conjuge_cin",
        "descricao": "CIN (Carteira de Identidade Nacional, modelo novo) — Camila, cônjuge",
        "tipo_documento": "rg",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": "cliente:conjuge",
            "campos": {
                "clientes.nome_oficial": p.nome,
                "clientes.data_nascimento": p.nascimento_iso,
                "clientes.genero": "Feminino",
                "clientes.cpf": p.cpf,
                "clientes.rg": p.rg,
                "clientes.rg_orgao_expedidor": p.rg_orgao,
            },
        }],
        "notas": (
            "Nacionalidade é deliberadamente OMITIDA deste documento: a "
            "certidão de casamento já cobre `clientes.nacionalidade` para "
            "Camila (via `nacionalidade.canonico()`, forma masculina "
            "canônica). Repeti-la aqui não adicionaria cobertura nova e só "
            "arriscaria uma segunda fonte para o mesmo campo."
        ),
    }


def _doc_vendedor_cnh() -> dict:
    p = F
    paragrafos = [
        "CARTEIRA NACIONAL DE HABILITAÇÃO",
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "",
        f"NOME: {p.nome}",
        f"DATA DE NASCIMENTO: {p.nascimento_extenso}",
        f"NATURALIDADE: {p.naturalidade}",
        f"CPF: {p.cpf}",
        f"DOC. IDENTIDADE: {p.rg} {p.rg_orgao}",
        "CATEGORIA: B",
        "1ª HABILITAÇÃO: 15/03/2005",
        "DATA DE EXPEDIÇÃO: 10/04/2023",
        "VALIDADE: 10/04/2033",
        # FILIAÇÃO LAST — a dry-run against the real `rg.find_rg` showed a
        # FILIAÇÃO/PAI/MAE block within ~48 chars BEFORE "DOC. IDENTIDADE"
        # demotes that reading to baixa with no matched_label (same
        # block-opener guard `cpf.py` applies — see `_doc_conjuge_cin`'s
        # note). Moving the decoy block to the end of the document, past
        # every field it could otherwise poison, is the realistic fix: most
        # CNH text layers print FILIAÇÃO in its own late section anyway.
        "FILIAÇÃO",
        f"PAI: {p.pai}",
        f"MAE: {p.mae}",
    ]
    return {
        "id": "vendedor_cnh",
        "descricao": "CNH — Fernando, vendedor",
        "tipo_documento": "cnh",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": "cliente:vendedor",
            "campos": {
                "clientes.nome_oficial": p.nome,
                "clientes.data_nascimento": p.nascimento_iso,
                "clientes.cpf": p.cpf,
                "clientes.rg": p.rg,
                "clientes.rg_orgao_expedidor": p.rg_orgao,
            },
        }],
    }


def _doc_certidao_casamento() -> dict:
    campos_comuns = {
        "clientes.estado_civil": "casado",
        "clientes.regime_bens": d.CASAMENTO["regime_canonico"],
        "clientes.data_casamento": d.CASAMENTO["data_iso"],
        "clientes.nacionalidade": "brasileiro",
    }
    paragrafos = [
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "REGISTRO CIVIL DAS PESSOAS NATURAIS",
        "CERTIDÃO DE CASAMENTO",
        "",
        "NOMES",
        "",
        R.nome,
        "CPF",
        R.cpf,
        "",
        C.nome,
        "CPF",
        C.cpf,
        "",
        f"MATRÍCULA: {d.CASAMENTO['matricula_civil']}",
        "",
        # Deliberately does NOT start with "NOME"/"NOMES" — a dry-run against
        # `name.find_name_conflitos` showed a line beginning with "NOMES"
        # re-opens `conjuges.py`'s multi-holder collection walk a second
        # time, and this line's own word-wrap (long real-fixture wording,
        # mirrored from the platform's own certidão test corpus) then fed a
        # wrapped fragment into it as a THIRD, bogus "titular" candidate —
        # a rendering artifact of a two-line PDF wrap, not something a real
        # certidão's fixed print layout produces at this exact word.
        "QUALIFICAÇÃO COMPLETA DOS CÔNJUGES (nome de solteiro, nascimento, "
        "naturalidade, nacionalidade, profissão e filiação)",
        f"{R.nome}, nascido em {R.nascimento_extenso}, em {R.naturalidade}, "
        f"de nacionalidade brasileiro, de profissão {R.profissao}, filho de "
        f"{R.pai} e de {R.mae}.",
        f"{C.nome}, nascida em {C.nascimento_extenso}, em {C.naturalidade}, "
        f"de nacionalidade brasileira, de profissão {C.profissao}, filha de "
        f"{C.pai} e de {C.mae}.",
        "",
        "DATA DO CASAMENTO",
        d.CASAMENTO["data_extenso"],
        "",
        "REGIME DE BENS DO CASAMENTO",
        d.CASAMENTO["regime_doc"],
        "",
        "AVERBAÇÕES",
        "Nada consta quanto a separação, divórcio, óbito ou interdição de "
        "qualquer dos cônjuges.",
        "",
        f"Certidão emitida em: {d.CASAMENTO['emissao_extenso']}.",
    ]
    return {
        "id": "certidao_casamento",
        "descricao": "Certidão de casamento conjunta — Ricardo + Camila",
        "tipo_documento": "certidao_casamento",
        "paragrafos": paragrafos,
        "uploads": [
            {
                "alvo": "cliente:titular",
                "campos": {
                    "clientes.nome_oficial": R.nome,
                    "clientes.cpf": R.cpf,
                    "clientes.profissao": R.profissao,
                    **campos_comuns,
                },
            },
            {
                "alvo": "cliente:conjuge",
                "campos": {
                    "clientes.nome_oficial": C.nome,
                    "clientes.cpf": C.cpf,
                    "clientes.profissao": C.profissao,
                    **campos_comuns,
                },
            },
        ],
        "notas": (
            "MESMO arquivo, enviado DUAS vezes na UI — uma vez no card do "
            "Ricardo, uma vez no card da Camila (ver README.md). O "
            "extrator usa o titular esperado de cada card para decidir "
            "qual dos dois nomes/CPFs listados é 'o do card'."
        ),
    }


def _doc_vendedor_certidao_nascimento() -> dict:
    p = F
    paragrafos = [
        "REPÚBLICA FEDERATIVA DO BRASIL",
        "REGISTRO CIVIL DAS PESSOAS NATURAIS",
        "CERTIDÃO DE NASCIMENTO",
        "",
        f"NOME: {p.nome}",
        f"DATA DE NASCIMENTO: {p.nascimento_extenso}",
        f"NATURALIDADE: {p.naturalidade}",
        "SEXO: MASCULINO",
        "FILIAÇÃO",
        f"PAI: {p.pai}",
        f"MAE: {p.mae}",
        "",
        "AVERBAÇÕES",
        "ESTADO CIVIL: SOLTEIRO",
        "",
        "Certidão emitida em: 12/09/2024.",
    ]
    return {
        "id": "vendedor_certidao_nascimento",
        "descricao": "Certidão de nascimento — Fernando, vendedor (solteiro)",
        "tipo_documento": "certidao_nascimento",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": "cliente:vendedor",
            "campos": {
                "clientes.nome_oficial": p.nome,
                "clientes.data_nascimento": p.nascimento_iso,
                "clientes.genero": "Masculino",
                "clientes.estado_civil": "solteiro",
            },
        }],
    }


def _doc_comprovante_endereco() -> dict:
    p = R
    e = p.endereco
    paragrafos = [
        "LUZCERTA DISTRIBUIDORA DE ENERGIA S.A.",
        "FATURA DE ENERGIA ELÉTRICA",
        "",
        f"CLIENTE: {p.nome}",
        f"CPF: {p.cpf}",
        "",
        "ENDEREÇO DE INSTALAÇÃO",
        f"CEP: {e.cep}",
        f"LOGRADOURO: {e.logradouro}",
        f"NÚMERO: {e.numero}",
        f"COMPLEMENTO: {e.complemento}",
        f"BAIRRO: {e.bairro}",
        f"CIDADE: {e.cidade}",
        f"UF: {e.uf}",
        "",
        f"Endereço completo: {e.linha_unica()}.",
        "",
        "MÊS DE REFERÊNCIA: JULHO/2025",
        "VALOR TOTAL: R$ 245,67",
        "VENCIMENTO: 15/08/2025",
    ]
    return {
        "id": "comprovante_endereco",
        "descricao": "Comprovante de endereço (conta de luz) — Ricardo, titular",
        "tipo_documento": "comprovante_endereco",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": "cliente:titular",
            "campos": {
                "clientes.endereco_cep": e.cep,
                "clientes.endereco_logradouro": e.logradouro,
                "clientes.endereco_numero": e.numero,
                "clientes.endereco_complemento": e.complemento,
                "clientes.endereco_bairro": e.bairro,
                "clientes.endereco_cidade": e.cidade,
                "clientes.endereco_uf": e.uf,
            },
        }],
    }


def _acts_imovel_livre() -> str:
    q_fernando = d.qualificacao(F, feminino=False)
    q_ricardo = d.qualificacao(R, feminino=False)
    q_camila = d.qualificacao(C, feminino=True)
    return "\n".join([
        f"R-1 - Em 10 de fevereiro de 2024, registra-se a presente compra e "
        f"venda pela qual OUTORGANTE VENDEDOR: {q_fernando}, vendeu a "
        f"OUTORGADO COMPRADOR: {q_ricardo}, e sua esposa {q_camila}, o "
        f"imóvel objeto desta matrícula, pelo valor de R$ 850.000,00, "
        f"conforme Escritura Pública lavrada em 05/02/2024 no 12º "
        f"Tabelionato de Notas de São Paulo, livro 350, folhas 120.",
        "",
        "R-2 - Em 10 de fevereiro de 2024, registra-se alienação "
        "fiduciária em garantia, pela qual os adquirentes do R-1 alienam "
        "fiduciariamente o imóvel ao CREDOR FIDUCIÁRIO: BANCO ALFA S.A., "
        "conforme Contrato de Financiamento nº 998877, celebrado em "
        "08/02/2024.",
        "",
        "AV-3 - Em 15 de janeiro de 2025, averba-se o cancelamento do R-2 "
        "desta matrícula, em razão da quitação integral da dívida "
        "garantida pela alienação fiduciária, nos termos do termo de "
        "quitação apresentado.",
    ])


def _doc_matricula_livre() -> dict:
    im = IL
    e = im.endereco
    corpo = "\n".join([
        f"{im.oficio.upper()}",
        f"CERTIDÃO DE INTEIRO TEOR - MATRÍCULA Nº {im.numero_matricula_pontuado}",
        "",
        f"IMÓVEL: Um apartamento situado na {e.logradouro}, nº {e.numero}, "
        f"{e.complemento}, Bairro {e.bairro}, no município de {e.cidade}, "
        f"Estado de {e.uf}, CEP {e.cep}, com área privativa de "
        f"{im.area_privativa_m2} m², correspondente a fração ideal de "
        f"{im.fracao_ideal}% no terreno.",
        "",
        f"CADASTRO MUNICIPAL: Contribuinte nº {im.cadastro_municipal}.",
        "",
        f"PROPRIETÁRIOS: {F.nome}, conforme R-1 desta matrícula.",
        "",
        f"REGISTRO ANTERIOR: Matrícula nº 12.345 do {im.oficio}.",
        "",
        _acts_imovel_livre(),
        "",
        f"{im.cidade_cartorio}, 15 de janeiro de 2025.",
        "",
        "O Oficial,",
    ])
    paragrafos = corpo.split("\n")
    return {
        "id": "matricula_imovel_livre",
        "descricao": (
            "Matrícula do imóvel e2e-imv-livre — compra e venda + alienação "
            "fiduciária CANCELADA (situação de ônus esperada: livre)"
        ),
        "tipo_documento": "matricula",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": f"imovel:{im.codigo}",
            # Every one of these is auto-filled SYNCHRONOUSLY by
            # `matriculas/preenchimento_service.preencher_sincrono` right
            # after the transcription lands, PROVIDED the extraction is
            # linked to the imóvel (`vincular_imovel` / the normal
            # upload-to-an-imóvel flow) — no separate confirm click. Values
            # verified 2026-09-23 by running the REAL seed parsers
            # (`find_cartorio`, `find_inscricao_municipal`,
            # `matricula_ato_detalhes.extrair_detalhes_ato`,
            # `frase_titulo_aquisitivo`, `preenchimento_service
            # .derivar_situacao_onus`) directly against this fixture's
            # rendered text — see README.md's dry-run trace.
            "campos": {
                "imovel_dados.numero_matricula": im.numero_matricula,
                "imovel_dados.numero_registro_imoveis": im.oficio.upper(),
                "imovel_dados.prefeitura_cadastro_imobiliario": im.cadastro_municipal,
                "imovel_dados.situacao_onus": "livre",
                "imovel_dados.titulo_aquisitivo_texto": (
                    "adquirido por Escritura Pública lavrada em 05/02/2024 "
                    "no 12º Tabelionato de Notas de São Paulo, Livro 350, "
                    "fls. 120, registrada sob o R-1"
                ),
            },
        }],
        "bonus_campos": {
            # onus_credor: R-2 (alienação fiduciária) is CANCELLED by AV-3,
            # so `estrutura_service.sugerir`'s onus-source suggestion
            # excludes it (per preenchimento_service.py's own docstring
            # table: "onus_fonte — encumbrance acts not cited by a
            # cancelamento") and `imovel_dados.onus_credor` stays NULL —
            # informational (this harness's `campos`/pytest schema asserts
            # non-empty values, so an EXPECTED-EMPTY field is reported here
            # rather than as a `campos` entry) — the real proof this
            # cancellation landed is `situacao_onus == "livre"` above.
            "imovel_dados.onus_credor": None,
            "matricula_ato_detalhes[R-1].data_registro": "2024-02-10",
            "matricula_ato_detalhes[R-1].transmitentes": [
                {"nome": F.nome, "cpf_cnpj": F.cpf},
            ],
            "matricula_ato_detalhes[R-1].adquirentes": [
                {"nome": R.nome, "cpf_cnpj": R.cpf},
                {"nome": C.nome, "cpf_cnpj": C.cpf},
            ],
            "matricula_ato_detalhes[R-2].atos_referidos": [],
            "matricula_ato_detalhes[AV-3].atos_referidos": [{"kind": "R", "numero": 2}],
            "clientes.profissao[vendedor]": F.profissao,
            "_nota": (
                "SOMENTE o profissao do Fernando (vendedor) ainda depende "
                "do clique 'Confirmar' na fila de Qualificações do imóvel "
                "(matriculas/qualificacao_service.confirmar) — ele não tem "
                "certidão de casamento, a ÚNICA outra fonte de profissão "
                "no sistema (ver profession.py). Ricardo e Camila já "
                "recebem profissao automaticamente do upload da certidão "
                "de casamento (ver _doc_certidao_casamento) — não é mais "
                "necessário confirmá-los na fila de Qualificações."
            ),
        },
    }


def _doc_matricula_hipoteca() -> dict:
    im = IH
    e = im.endereco
    q_terceiro = d.qualificacao_solteiro(d.TERCEIRO_VENDEDOR, d.TERCEIRO_VENDEDOR_CPF)
    q_terceira = d.qualificacao_solteiro(d.TERCEIRA_COMPRADORA, d.TERCEIRA_COMPRADORA_CPF)
    corpo = "\n".join([
        f"{im.oficio.upper()}",
        f"CERTIDÃO DE INTEIRO TEOR - MATRÍCULA Nº {im.numero_matricula_pontuado}",
        "",
        f"IMÓVEL: Um apartamento situado na {e.logradouro}, nº {e.numero}, "
        f"{e.complemento}, Bairro {e.bairro}, no município de {e.cidade}, "
        f"Estado de {e.uf}, CEP {e.cep}, com área privativa de "
        f"{im.area_privativa_m2} m², correspondente a fração ideal de "
        f"{im.fracao_ideal}% no terreno.",
        "",
        f"CADASTRO MUNICIPAL: Contribuinte nº {im.cadastro_municipal}.",
        "",
        f"PROPRIETÁRIOS: {d.TERCEIRO_VENDEDOR}, conforme R-1 desta matrícula.",
        "",
        f"REGISTRO ANTERIOR: Matrícula nº 54.321 do {im.oficio}.",
        "",
        f"R-1 - Em 05 de maio de 2023, registra-se a presente compra e "
        f"venda pela qual OUTORGANTE VENDEDOR: {q_terceiro}, vendeu a "
        f"OUTORGADO COMPRADOR: {q_terceira}, o imóvel objeto desta "
        f"matrícula, pelo valor de R$ 620.000,00, conforme Escritura "
        f"Pública lavrada em 02/05/2023 no 4º Tabelionato de Notas de "
        f"Campinas, livro 210, folhas 88.",
        "",
        "R-2 - Em 05 de maio de 2023, registra-se hipoteca em primeiro "
        "grau, pela qual a adquirente do R-1 hipoteca o imóvel ao CREDOR "
        "HIPOTECÁRIO: BANCO BETA S.A., conforme Contrato de "
        "Financiamento nº 445566, celebrado em 03/05/2023, no valor de "
        "R$ 400.000,00.",
        "",
        f"{im.cidade_cartorio}, 20 de maio de 2023.",
        "",
        "O Oficial,",
    ])
    paragrafos = corpo.split("\n")
    return {
        "id": "matricula_imovel_hipoteca",
        "descricao": (
            "Matrícula do imóvel e2e-imv-hipoteca — compra e venda + "
            "HIPOTECA ATIVA (sem cancelamento)"
        ),
        "tipo_documento": "matricula",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": f"imovel:{im.codigo}",
            # See `_doc_matricula_livre`'s comment — same automatic,
            # confirm-free fill, values verified the same way. Here the
            # hipoteca is never cancelled, so `situacao_onus` and
            # `onus_credor` land as ACTIVE values instead of "livre"/empty.
            "campos": {
                "imovel_dados.numero_matricula": im.numero_matricula,
                "imovel_dados.numero_registro_imoveis": im.oficio.upper(),
                "imovel_dados.prefeitura_cadastro_imobiliario": im.cadastro_municipal,
                "imovel_dados.situacao_onus": "hipoteca",
                "imovel_dados.onus_credor": "BANCO BETA S.A.",
                "imovel_dados.titulo_aquisitivo_texto": (
                    "adquirido por Escritura Pública lavrada em 02/05/2023 "
                    "no 4º Tabelionato de Notas de Campinas, Livro 210, "
                    "fls. 88, registrada sob o R-1"
                ),
            },
        }],
        "bonus_campos": {
            "matricula_ato_detalhes[R-1].data_registro": "2023-05-05",
            "matricula_ato_detalhes[R-1].transmitentes": [
                {"nome": d.TERCEIRO_VENDEDOR, "cpf_cnpj": d.TERCEIRO_VENDEDOR_CPF},
            ],
            "matricula_ato_detalhes[R-1].adquirentes": [
                {"nome": d.TERCEIRA_COMPRADORA, "cpf_cnpj": d.TERCEIRA_COMPRADORA_CPF},
            ],
            "matricula_ato_detalhes[R-2].credor": "BANCO BETA S.A.",
        },
    }


def _doc_guia_iptu() -> dict:
    im = IL
    paragrafos = [
        "PREFEITURA DO MUNICÍPIO DE SÃO PAULO",
        "SECRETARIA MUNICIPAL DA FAZENDA",
        "GUIA DE PAGAMENTO DE IPTU — EXERCÍCIO 2025",
        "",
        f"INSCRIÇÃO IMOBILIÁRIA: {im.cadastro_municipal}",
        f"ENDEREÇO DO IMÓVEL: {im.endereco.linha_unica()}",
        "PARCELA ÚNICA",
        "VALOR: R$ 3.245,10",
        "VENCIMENTO: 10/03/2025",
    ]
    return {
        "id": "guia_iptu",
        "descricao": "Guia de IPTU — imóvel e2e-imv-livre",
        "tipo_documento": "guia_iptu",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": f"imovel:{im.codigo}",
            "campos": {
                "imovel_documentos.inscricao_imobiliaria": im.cadastro_municipal,
            },
        }],
        "bonus_campos": {
            "imovel_dados.prefeitura_cadastro_imobiliario": im.cadastro_municipal,
        },
    }


def _doc_cnd_iptu() -> dict:
    im = IL
    paragrafos = [
        "PREFEITURA DO MUNICÍPIO DE SÃO PAULO",
        "SECRETARIA MUNICIPAL DA FAZENDA",
        "CERTIDÃO NEGATIVA DE DÉBITOS — IPTU",
        "",
        "NÚMERO: 2025/0045678",
        f"INSCRIÇÃO IMOBILIÁRIA: {im.cadastro_municipal}",
        "EMITIDA EM: 10/01/2025",
        "VÁLIDA ATÉ: 10/07/2025",
        "RESULTADO: NEGATIVA",
        "",
        "Certificamos, para os devidos fins, que não constam em nome do "
        "referido imóvel débitos relativos ao Imposto Predial e "
        "Territorial Urbano - IPTU.",
    ]
    return {
        "id": "cnd_iptu",
        "descricao": "CND de IPTU (negativa) — imóvel e2e-imv-livre",
        "tipo_documento": "cnd_iptu",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": f"imovel:{im.codigo}",
            "campos": {
                "imovel_documentos.numero": "2025/0045678",
                "imovel_documentos.emitida_em": "2025-01-10",
                "imovel_documentos.validade_ate": "2025-07-10",
                "imovel_documentos.resultado": "negativa",
                "imovel_documentos.inscricao_imobiliaria": im.cadastro_municipal,
            },
        }],
    }


def _doc_cnd_federal_vendedor() -> dict:
    p = F
    paragrafos = [
        "MINISTÉRIO DA FAZENDA",
        "RECEITA FEDERAL DO BRASIL / PROCURADORIA-GERAL DA FAZENDA NACIONAL",
        "CERTIDÃO NEGATIVA DE DÉBITOS RELATIVOS AOS TRIBUTOS FEDERAIS E À "
        "DÍVIDA ATIVA DA UNIÃO",
        "",
        f"NOME: {p.nome}",
        f"CPF: {p.cpf}",
        "CERTIDÃO Nº: 123456789",
        "EMITIDA EM: 01/02/2025",
        "VÁLIDA ATÉ: 31/07/2025",
        "RESULTADO: NEGATIVA",
        "",
        "Ressalvado o direito de a Fazenda Nacional cobrar e inscrever "
        "quaisquer dívidas de responsabilidade do sujeito passivo acima "
        "identificado que vierem a ser apuradas, é certificado que não "
        "constam pendências em seu nome.",
    ]
    return {
        "id": "cnd_federal_vendedor",
        "descricao": "CND Federal (negativa) — Fernando, vendedor",
        "tipo_documento": "cnd_federal",
        "paragrafos": paragrafos,
        "uploads": [{
            "alvo": "certidao:vendedor:cnd_federal",
            "campos": {
                "certidao_resultados.numero": "123456789",
                "certidao_resultados.emitida_em": "2025-02-01",
                "certidao_resultados.validade_ate": "2025-07-31",
                "certidao_resultados.resultado": "negativa",
            },
        }],
    }


DOCUMENTOS: list[dict] = [
    _doc_titular_rg(),
    _doc_conjuge_cin(),
    _doc_vendedor_cnh(),
    _doc_certidao_casamento(),
    _doc_vendedor_certidao_nascimento(),
    _doc_comprovante_endereco(),
    _doc_matricula_livre(),
    _doc_matricula_hipoteca(),
    _doc_guia_iptu(),
    _doc_cnd_iptu(),
    _doc_cnd_federal_vendedor(),
]


def _persona_dict(p: d.Persona) -> dict:
    return {
        "nome": p.nome, "cpf": p.cpf, "rg": p.rg, "rg_orgao": p.rg_orgao,
        "data_nascimento": p.nascimento_iso, "genero": p.genero,
    }


def gerar(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "_gerado_por": "gerar_documentos.py (sw-extraction-contract-gate-2026-09)",
        "_seed": SEED,
        "personas": {
            "titular": _persona_dict(R),
            "conjuge": _persona_dict(C),
            "vendedor": _persona_dict(F),
        },
        "imoveis": {
            "livre": {"codigo": IL.codigo, "numero_matricula": IL.numero_matricula},
            "hipoteca": {"codigo": IH.codigo, "numero_matricula": IH.numero_matricula},
        },
        "documentos": {},
    }

    for doc in DOCUMENTOS:
        pdf_texto = render_text_pdf(doc["paragrafos"], doc["descricao"])
        # `hash(str)` is salted per-process (PYTHONHASHSEED) — NOT stable
        # across runs, which silently broke this generator's determinism
        # claim (the scan variant's rotation/noise differed run to run
        # even though the text layer did not). `zlib.crc32` is a fixed,
        # portable function of the bytes alone.
        doc_seed = SEED + (zlib.crc32(doc["id"].encode("utf-8")) % 10_000)
        pdf_scan = rasterize_as_scan(pdf_texto, seed=doc_seed)

        nome_texto = f"{doc['id']}_texto.pdf"
        nome_scan = f"{doc['id']}_scan.pdf"
        (out_dir / nome_texto).write_bytes(pdf_texto)
        (out_dir / nome_scan).write_bytes(pdf_scan)

        entrada = {
            "descricao": doc["descricao"],
            "tipo_documento": doc["tipo_documento"],
            "uploads": doc["uploads"],
        }
        if "bonus_campos" in doc:
            entrada["bonus_campos"] = doc["bonus_campos"]
        if "pending_spec" in doc:
            entrada["pending_spec"] = doc["pending_spec"]
        if "notas" in doc:
            entrada["notas"] = doc["notas"]

        for nome_arquivo in (nome_texto, nome_scan):
            manifest["documentos"][nome_arquivo] = entrada

    esperado_path = out_dir / "esperado.json"
    esperado_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path,
        default=Path(__file__).parent / "fixtures",
        help="Output directory for the PDFs + esperado.json (default: ./fixtures)",
    )
    args = parser.parse_args(argv)
    manifest = gerar(args.out)
    print(f"Gerados {len(manifest['documentos'])} arquivos-alvo "
          f"({len(DOCUMENTOS)} documentos x 2 variantes) em {args.out}")
    print(f"esperado.json: {args.out / 'esperado.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
