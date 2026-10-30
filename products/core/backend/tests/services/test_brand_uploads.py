"""Brand upload intake: extension AND bytes must agree; SVG refused; caps."""
from __future__ import annotations

import json

import pytest

from app.services.brand import uploads as U

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"x" * 32
WOFF2 = b"wOF2" + b"\x00" * 32


@pytest.mark.parametrize("name,data,kind", [
    ("logo.png", PNG, U.KIND_IMAGE), ("logo.JPG", JPG, U.KIND_IMAGE), ("l.webp", WEBP, U.KIND_IMAGE),
    ("manual.pdf", PDF, U.KIND_PDF), ("guia.md", "# Marca\nCor: azul".encode(), U.KIND_MARKDOWN),
    ("Lora-Regular.woff2", WOFF2, U.KIND_FONT),
])
def test_accepted(name, data, kind):
    assert U.classify(name, data).kind == kind


@pytest.mark.parametrize("name,data,codigo", [
    ("logo.svg", PNG, "svg_recusado"),
    ("logo.png", b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>", "svg_recusado"),
    ("guia.md", b"  <?xml version='1.0'?><svg/>", "svg_recusado"),
    ("logo.png", PDF, "conteudo_invalido"),         # bytes contradict the extension
    ("manual.pdf", PNG, "conteudo_invalido"),
    ("guia.md", PDF, "conteudo_invalido"),           # binary posing as markdown
    ("guia.md", b"\xff\xfe\x00bad", "conteudo_invalido"),
    ("font.woff2", PNG, "conteudo_invalido"),
    ("run.exe", b"MZ\x90\x00", "tipo_nao_suportado"),
    ("empty.png", b"", "arquivo_vazio"),
])
def test_refused(name, data, codigo):
    with pytest.raises(U.UploadRefused) as exc:
        U.classify(name, data)
    assert exc.value.codigo == codigo


def test_size_caps():
    with pytest.raises(U.UploadRefused) as one:
        U.classify("big.pdf", b"%PDF" + b"x" * U.MAX_FILE_BYTES)
    assert one.value.codigo == "arquivo_grande"
    with pytest.raises(U.UploadRefused) as many:
        U.check_batch([(f"{i}.png", PNG) for i in range(U.MAX_FILES + 1)])
    assert many.value.codigo == "arquivos_demais"
    chunk = b"%PDF" + b"x" * (9 * 1024 * 1024)
    with pytest.raises(U.UploadRefused) as total:
        U.check_batch([("a.pdf", chunk), ("b.pdf", chunk), ("c.pdf", chunk)])
    assert total.value.codigo == "lote_grande"


def test_filenames_are_sanitised_and_never_paths():
    assert U.safe_name("../../etc/passwd.md") == "passwd.md"
    assert U.safe_name("C:\\x\\logo<script>.png") == "logo_script_.png"


def test_descriptions_must_name_uploaded_files():
    assert U.parse_descriptions(json.dumps({"logo.png": "versão escura"}), ["logo.png"]) == {"logo.png": "versão escura"}
    for raw in ("not json", json.dumps(["x"]), json.dumps({"other.png": "x"}),
                json.dumps({"logo.png": "x" * (U.MAX_DESCRIPTION_CHARS + 1)})):
        with pytest.raises(U.UploadRefused):
            U.parse_descriptions(raw, ["logo.png"])


@pytest.mark.parametrize("name,desc,slot", [
    ("favicon.png", "", "favicon"), ("simbolo.png", "", "logo_mark"),
    ("logo-negativo.png", "", "logo_dark"), ("logo.png", "", "logo_light"),
    ("img1.png", "versão para fundo escuro", "logo_dark"), ("foto.jpg", "", None),
])
def test_slot_hints(name, desc, slot):
    assert U.slot_for_image(name, desc) == slot


def test_font_family_from_name():
    assert U.font_family_from_name("Lora-Regular.woff2") == "Lora"
    assert U.font_family_from_name("Cormorant_Garamond-600.woff2") == "Cormorant Garamond"
