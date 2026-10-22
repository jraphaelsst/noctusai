"""Font-shifted PDF text layer: decode a constant shift, else route to OCR."""

from noctusai_lib.integrations.media.camada_deslocada import decifrar_camada_deslocada
from noctusai_lib.integrations.media.pdf_text import _classify_page

LIMPO = (
    "DADOS DO PROPONENTE nome cpf data de nascimento estado civil profissao renda "
    "endereco cidade bairro cep telefone email conta banco agencia valor do imovel "
    "prazo da parcela taxa total mensal"
)


def _cifrar(texto: str, shift: int) -> str:
    return "".join(chr(ord(c) - shift) if 33 <= ord(c) <= 126 else c for c in texto)


def test_shift_unico_e_decifrado():
    cifrado = _cifrar(LIMPO, 29)
    assert cifrado != LIMPO
    texto, shift, ocr = decifrar_camada_deslocada(cifrado)
    assert (shift, ocr) == (29, False)
    assert texto == LIMPO


def test_texto_limpo_passa_intacto():
    assert decifrar_camada_deslocada(LIMPO) == (LIMPO, None, False)


def test_gibberish_sem_shift_vai_para_ocr():
    lixo = " ".join("xq%sz%s" % ("k" * (i % 5 + 1), "vwj"[i % 3] * (i % 7 + 1)) for i in range(60))
    texto, shift, ocr = decifrar_camada_deslocada(lixo)
    assert (shift, ocr) == (None, True)
    assert _classify_page(lixo, 0.0) == (False, "enciphered text layer")
