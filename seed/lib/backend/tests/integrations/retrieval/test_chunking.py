"""chunk_markdown: pure, deterministic, heading-aware."""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.retrieval import chunk_markdown

DOC = """# Clientes

Como cadastrar um cliente novo.

Abra o menu e toque em Novo cliente.

## Marcas

Cada cliente pode ter varias marcas.

# Cobranca

Gere a cobranca do mes.
"""


def test_headings_become_the_chunk_topic_path():
    chunks = chunk_markdown(DOC)
    assert [c.heading for c in chunks] == ["Clientes", "Clientes > Marcas", "Cobranca"]
    assert [c.position for c in chunks] == [0, 1, 2]
    assert "Novo cliente" in chunks[0].content and "Marcas" not in chunks[0].content


def test_blank_text_yields_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("  \n\n ") == []


def test_deterministic_hashes():
    assert chunk_markdown(DOC) == chunk_markdown(DOC)
    assert chunk_markdown(DOC)[0].content_hash != chunk_markdown(DOC)[1].content_hash


def test_paragraphs_pack_up_to_max_chars_and_never_exceed_it():
    text = "\n\n".join(f"paragrafo numero {i} " + "x" * 80 for i in range(20))
    chunks = chunk_markdown(text, max_chars=300, overlap=20)
    assert len(chunks) > 1
    assert all(len(c.content) <= 300 for c in chunks)
    joined = "\n".join(c.content for c in chunks)
    assert all(f"paragrafo numero {i} " in joined for i in range(20))


def test_oversized_paragraph_is_window_split_with_overlap():
    para = "".join(f"{i:04d}" for i in range(400))  # 1600 chars, no blank line
    chunks = chunk_markdown(para, max_chars=500, overlap=100)
    assert len(chunks) >= 3
    assert all(len(c.content) <= 500 for c in chunks)
    assert chunks[0].content[-100:] == chunks[1].content[:100]


def test_fenced_code_block_is_never_split_on_its_blank_lines():
    text = "# Api\n\nintro\n\n```\nlinha1\n\nlinha2\n```\n"
    chunks = chunk_markdown(text, max_chars=400)
    assert any("linha1\n\nlinha2" in c.content for c in chunks)


def test_hash_inside_fence_is_not_a_heading():
    text = "# A\n\n```\n# not a heading\n```\n"
    assert [c.heading for c in chunk_markdown(text)] == ["A"]


@pytest.mark.parametrize("max_chars,overlap", [(10, 0), (200, 100), (200, -1)])
def test_invalid_params_are_refused(max_chars, overlap):
    with pytest.raises(ValueError):
        chunk_markdown("x", max_chars=max_chars, overlap=overlap)
