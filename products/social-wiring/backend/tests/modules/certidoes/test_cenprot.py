"""CENPROT manual-upload structuring — `app.modules.certidoes.cenprot`.

Every identifier here is SYNTHETIC: `123.456.789-09` is the canonical
documentation CPF (valid check digits, belongs to nobody), the protocolo is
a counting sequence. Never paste a real screenshot's values into this file.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.modules.certidoes import cenprot
from app.modules.certidoes.cenprot import CenprotLeitura, estruturar_cenprot

CPF = "12345678909"
CNPJ = "11222333000181"
PROTOCOLO = "0123456789"


def _tela(
    *,
    protocolo: str = "0123456789",
    documento: str = "123.456.789-09",
    relogio: str = "14:32\n17/06/2026",
) -> str:
    """The shape of a CENPROT-SP screenshot transcript: browser chrome, the
    result body, then the OS taskbar clock (time above date)."""
    return (
        "cenprotsp.org.br/consulta\n"
        "CENPROT-SP — Consulta Gratuita de Protestos\n"
        f"Protocolo da Consulta: {protocolo}\n"
        f"Documento Pesquisado: {documento}\n"
        "Não constam protestos em nome do documento pesquisado.\n"
        f"{relogio}\n"
    )


def _segunda(texto):
    return AsyncMock(return_value=texto)


async def _estruturar(texto1, texto2, *, tipo_documento="cpf", documento=CPF):
    return await estruturar_cenprot(
        texto_leitura1=texto1,
        pdf_bytes=b"%PDF-1.4",
        nome_display="CENPROT",
        org_id=None,
        tipo_documento_esperado=tipo_documento,
        documento_esperado=documento,
        ler_segunda_vez=_segunda(texto2),
    )


# ---------------------------------------------------------------------------
# _extrair — the pure label-anchored parse
# ---------------------------------------------------------------------------


class TestExtrair:
    def test_le_os_tres_campos_ancorados_no_rotulo(self):
        assert cenprot._extrair(_tela()) == CenprotLeitura(
            protocolo=PROTOCOLO, documento_pesquisado=CPF, data="17/06/2026"
        )

    def test_separadores_inseridos_pelo_ocr_sao_descartados(self):
        leitura = cenprot._extrair(_tela(protocolo="01234 567-89"))
        assert leitura.protocolo == PROTOCOLO

    def test_cnpj_pesquisado(self):
        leitura = cenprot._extrair(_tela(documento="11.222.333/0001-81"))
        assert leitura.documento_pesquisado == CNPJ

    def test_texto_vazio_ou_none_nao_levanta(self):
        assert cenprot._extrair(None) == CenprotLeitura()
        assert cenprot._extrair("") == CenprotLeitura()

    def test_sem_rotulo_nao_adivinha_numero(self):
        # A bare 10-digit run with no "Protocolo da Consulta" label is not
        # the protocolo — the label IS the source of truth.
        leitura = cenprot._extrair("0123456789\nDocumento Pesquisado: 123.456.789-09")
        assert leitura.protocolo is None

    def test_data_ancorada_no_relogio_vence_outras_datas(self):
        texto = _tela() + "Atualizado em 01/01/2020\n"
        assert cenprot._extrair(texto).data == "17/06/2026"

    def test_data_solta_so_quando_unica(self):
        uma = _tela(relogio="17/06/2026")
        assert cenprot._extrair(uma).data == "17/06/2026"
        duas = _tela(relogio="17/06/2026") + "01/01/2020\n"
        assert cenprot._extrair(duas).data is None


class TestDataIso:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("17/06/2026", "2026-06-17"),
            ("31/02/2026", None),
            ("17/13/2026", None),
            (None, None),
            ("17-06-2026", None),
        ],
    )
    def test_converte_ou_recusa(self, entrada, esperado):
        assert cenprot._data_iso(entrada) == esperado


# ---------------------------------------------------------------------------
# estruturar_cenprot — identity first, then two-read agreement
# ---------------------------------------------------------------------------


class TestEstruturarCenprot:
    @pytest.mark.asyncio
    async def test_duas_leituras_concordantes_gravam_numero_e_data(self):
        r = await _estruturar(_tela(), _tela())
        assert r.numero == PROTOCOLO
        assert r.emitida_em == "2026-06-17"
        assert r.avisos == ()

    @pytest.mark.asyncio
    async def test_protocolo_divergente_nao_e_gravado(self):
        r = await _estruturar(_tela(), _tela(protocolo="0123456780"))
        assert r.numero is None
        assert r.emitida_em == "2026-06-17"
        assert any("Protocolo da Consulta" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_data_divergente_nao_e_gravada(self):
        r = await _estruturar(_tela(), _tela(relogio="14:32\n18/06/2026"))
        assert r.numero == PROTOCOLO
        assert r.emitida_em is None
        assert any("relógio" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_data_concordante_mas_invalida_e_recusada_com_aviso(self):
        r = await _estruturar(
            _tela(relogio="14:32\n31/02/2026"), _tela(relogio="14:32\n31/02/2026")
        )
        assert r.emitida_em is None
        assert any("não é uma data válida" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_documento_de_outra_pessoa_bloqueia_tudo(self):
        # Two reads agreeing on a protocolo attached to the WRONG person's
        # screenshot is exactly as wrong as a misread digit.
        r = await _estruturar(_tela(), _tela(), documento="52998224725")
        assert r.numero is None
        assert r.emitida_em is None
        assert any("Documento Pesquisado" in a for a in r.avisos)

    @pytest.mark.asyncio
    async def test_digito_verificador_invalido_bloqueia_tudo(self):
        ruim = _tela(documento="123.456.789-00")
        r = await _estruturar(ruim, ruim, documento="12345678900")
        assert (r.numero, r.emitida_em) == (None, None)

    @pytest.mark.asyncio
    async def test_uma_leitura_valida_do_documento_basta(self):
        # The document carries its own check digits + must equal the one on
        # file — one read passing both is trusted, so an OCR slip in the
        # OTHER read's documento does not cost the protocolo.
        r = await _estruturar(_tela(), _tela(documento="123.456.789-00"))
        assert r.numero == PROTOCOLO

    @pytest.mark.asyncio
    async def test_cnpj_valida_contra_cnpj(self):
        tela = _tela(documento="11.222.333/0001-81")
        r = await _estruturar(tela, tela, tipo_documento="cnpj", documento=CNPJ)
        assert r.numero == PROTOCOLO

    @pytest.mark.asyncio
    async def test_segunda_leitura_que_falha_nao_levanta_e_nada_e_gravado(self):
        r = await estruturar_cenprot(
            texto_leitura1=_tela(),
            pdf_bytes=b"%PDF-1.4",
            nome_display="CENPROT",
            org_id=None,
            tipo_documento_esperado="cpf",
            documento_esperado=CPF,
            ler_segunda_vez=AsyncMock(side_effect=RuntimeError("quota")),
        )
        assert (r.numero, r.emitida_em) == (None, None)
        assert r.avisos  # says why, never silent

    @pytest.mark.asyncio
    async def test_avisos_nunca_carregam_o_valor_extraido(self):
        # 🔴 PRIVACY: diagnostics only — never the CPF or the protocolo.
        casos = [
            await _estruturar(_tela(), _tela(protocolo="0123456780")),
            await _estruturar(_tela(), _tela(), documento="52998224725"),
            await _estruturar(_tela(), _tela(relogio="14:32\n18/06/2026")),
        ]
        for r in casos:
            for aviso in r.avisos:
                for valor in (CPF, "123.456.789-09", PROTOCOLO, "0123456780",
                              "17/06/2026", "18/06/2026"):
                    assert valor not in aviso
