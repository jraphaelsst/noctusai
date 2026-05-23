"""coverage_audit service — fake-driven tests (no network, no keys).

Per noc methodology: seed real data + inject fakes via dependency injection.
No monkeypatching of our own code.
"""
from __future__ import annotations

import pytest

from app.services.coverage_audit import (
    MAP_REDUCE_THRESHOLD_CHARS,
    audit_all,
    audit_module,
)

# ---------------------------------------------------------------------------
# Shared fake chat function factory
# ---------------------------------------------------------------------------

TAG_VOCABULARY = {"[Absorvido]", "[Parcial]", "[Ausente]"}

# Canned LLM response that satisfies the format assertions.
_CANNED_REPORT = """\
## Veredito de cobertura

**Score: 7 / 10**

A metodologia captura o esqueleto do módulo mas perde profundidade operacional.

1. Lacuna A — exercício prático ausente.
2. Lacuna B — tipologia não absorvida.

## Inventário de conteúdo útil nos transcritos (anonimizado)

### Aula 1 — Introdução
**[Absorvido]**

Conceito central absorvido fielmente.

**Conteúdo útil não absorvido:**
- Nenhum.

### Aula 2 — Framework
**[Parcial]**

Estrutura absorvida; mecanismo perdido.

**Conteúdo útil não absorvido:**
- O raciocínio encadeado que fundamenta o framework.

### Aula 3 — Exercício
**[Ausente]**

Exercício prático completamente ausente.

**Conteúdo útil não absorvido:**
- Passo a passo do exercício (5 etapas).

## Lacunas a absorver (acionável)

| # | Lacuna | Aula/bloco fonte | Impacto |
|---|--------|-----------------|---------|
| L1 | Exercício prático | Aula 3 | Alto |
| L2 | Mecanismo do framework | Aula 2 | Médio |

## Observações de anonimização

1. Nomes de pessoas omitidos.
2. Resultados numéricos removidos.
"""

# Canned map-phase response (compact inventory).
_CANNED_INVENTORY = "- Conceito X\n- Framework Y\n- Exercício Z"


def make_fake_chat(calls: list) -> object:
    """Return a fake async chat_fn that records calls and returns canned responses."""

    async def fake_chat(messages, *, model=None, **kw):
        calls.append(messages)
        # Distinguish map calls (short system prompt) from reduce/direct calls.
        system_content = messages[0]["content"] if messages else ""
        if "inventário compacto" in system_content:
            # Map phase.
            return _CANNED_INVENTORY
        return _CANNED_REPORT

    return fake_chat


# ---------------------------------------------------------------------------
# audit_module — small input (direct path, single call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_module_small_input_single_call():
    """Small transcripts → direct path → exactly one chat_fn call."""
    calls = []
    fake_chat = make_fake_chat(calls)

    short_transcript = "Conteúdo curto da aula."  # well under threshold
    assert len(short_transcript) < MAP_REDUCE_THRESHOLD_CHARS

    report = await audit_module(
        "Módulo Teste",
        [short_transcript],
        "Metodologia resumida.",
        chat_fn=fake_chat,
    )

    assert len(calls) == 1, "Small input must produce exactly one chat_fn call"
    assert "Score:" in report
    assert any(tag in report for tag in TAG_VOCABULARY)
    assert "Veredito de cobertura" in report
    assert "Inventário" in report
    assert "Lacunas" in report
    assert "Observações" in report


@pytest.mark.asyncio
async def test_audit_module_returns_module_header():
    """Report must include the module name in the H1 title."""
    calls = []
    fake_chat = make_fake_chat(calls)

    report = await audit_module(
        "Módulo 7: Núcleo de Influência",
        ["Texto."],
        "Metodologia.",
        chat_fn=fake_chat,
    )

    assert "Módulo 7: Núcleo de Influência" in report
    assert report.startswith("# Auditoria de Cobertura")


@pytest.mark.asyncio
async def test_audit_module_anonymization_notice_present():
    """Report must carry the anonymization policy notice."""
    calls = []
    fake_chat = make_fake_chat(calls)

    report = await audit_module("M", ["t."], "m.", chat_fn=fake_chat)

    assert "Política de anonimização" in report


# ---------------------------------------------------------------------------
# audit_module — large input (map-reduce path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_module_large_input_map_reduce():
    """Large transcripts → map-reduce path → N+1 chat_fn calls (N transcripts + 1 reduce)."""
    calls = []
    fake_chat = make_fake_chat(calls)

    # Build transcripts that together exceed the threshold.
    chunk = "A" * (MAP_REDUCE_THRESHOLD_CHARS // 2 + 1)
    transcripts = [chunk, chunk]  # combined = 2x the half-threshold+1 > threshold

    assert sum(len(t) for t in transcripts) > MAP_REDUCE_THRESHOLD_CHARS

    report = await audit_module(
        "Módulo Grande",
        transcripts,
        "Metodologia.",
        chat_fn=fake_chat,
        delay_seconds=0,
    )

    # 2 map calls + 1 reduce call = 3 total.
    assert len(calls) == 3, (
        f"Map-reduce for 2 transcripts must produce 3 calls; got {len(calls)}"
    )
    assert "Score:" in report
    assert any(tag in report for tag in TAG_VOCABULARY)


@pytest.mark.asyncio
async def test_audit_module_map_reduce_vs_direct_call_counts():
    """Verify that large input triggers more calls than small input."""
    small_calls: list = []
    large_calls: list = []

    fake_small = make_fake_chat(small_calls)
    fake_large = make_fake_chat(large_calls)

    short = "Conteúdo breve."
    chunk = "X" * (MAP_REDUCE_THRESHOLD_CHARS // 3 + 1)
    long_transcripts = [chunk, chunk, chunk]  # 3 chunks > threshold

    await audit_module("M Small", [short], "met.", chat_fn=fake_small)
    await audit_module("M Large", long_transcripts, "met.", chat_fn=fake_large, delay_seconds=0)

    assert len(small_calls) == 1
    assert len(large_calls) == 4  # 3 map + 1 reduce


# ---------------------------------------------------------------------------
# audit_all — filesystem integration
# ---------------------------------------------------------------------------


def _seed_module(
    data_dir,
    module_folder: str,
    methodology_filename: str,
    transcript_text: str = "Aula 1: conceito importante.",
    methodology_text: str = "# Metodologia\n\nConteúdo absorvido.",
):
    """Create a minimal data dir layout for one module."""
    t_dir = data_dir / "transcripts" / module_folder
    t_dir.mkdir(parents=True)
    (t_dir / "aula-1.md").write_text(transcript_text, encoding="utf-8")

    m_dir = data_dir / "methodology"
    m_dir.mkdir(parents=True, exist_ok=True)
    (m_dir / methodology_filename).write_text(methodology_text, encoding="utf-8")


@pytest.mark.asyncio
async def test_audit_all_writes_report_file(tmp_path):
    """audit_all writes modulo-<slug>.md under doc/analysis/ for each module."""
    _seed_module(tmp_path, "7 NUCLEO DE INFLUENCIA", "7 NUCLEO DE INFLUENCIA.md")

    calls: list = []
    fake_chat = make_fake_chat(calls)

    results = await audit_all(tmp_path, chat_fn=fake_chat, delay_seconds=0)

    assert len(results) == 1
    module_name, report_path = next(iter(results.items()))

    assert module_name == "7 NUCLEO DE INFLUENCIA"
    assert report_path.exists()
    assert report_path.name == "modulo-7.md"
    # Confirm it's under doc/analysis/ relative to repo root (tmp_path.parent).
    assert report_path == tmp_path.parent / "doc" / "analysis" / "modulo-7.md"

    content = report_path.read_text(encoding="utf-8")
    assert "Score:" in content
    assert "Veredito de cobertura" in content


@pytest.mark.asyncio
async def test_audit_all_only_filter(tmp_path):
    """The `only` filter restricts modules to those whose names contain the substring."""
    _seed_module(tmp_path, "5 HEADLINES", "5 HEADLINES.md")
    _seed_module(tmp_path, "7 NUCLEO", "7 NUCLEO.md")

    calls: list = []
    fake_chat = make_fake_chat(calls)

    results = await audit_all(tmp_path, only="nucleo", chat_fn=fake_chat, delay_seconds=0)

    assert list(results.keys()) == ["7 NUCLEO"]


@pytest.mark.asyncio
async def test_audit_all_multiple_modules(tmp_path):
    """audit_all processes all modules in sorted order and returns all paths."""
    _seed_module(tmp_path, "1 PLANO", "1 PLANO.md")
    _seed_module(tmp_path, "2 ALGORITMO", "2 ALGORITMO.md")
    _seed_module(tmp_path, "3 ASSUNTOS VIRAIS", "3 ASSUNTOS VIRAIS.md")

    calls: list = []
    fake_chat = make_fake_chat(calls)

    results = await audit_all(tmp_path, chat_fn=fake_chat, delay_seconds=0)

    assert len(results) == 3
    assert "1 PLANO" in results
    assert "2 ALGORITMO" in results
    assert "3 ASSUNTOS VIRAIS" in results

    for module_name, path in results.items():
        assert path.exists()
        assert path.suffix == ".md"


@pytest.mark.asyncio
async def test_audit_all_raises_without_transcripts_dir(tmp_path):
    """audit_all raises FileNotFoundError if transcripts/ is absent."""
    with pytest.raises(FileNotFoundError, match="Transcripts directory"):
        await audit_all(tmp_path, chat_fn=make_fake_chat([]), delay_seconds=0)


@pytest.mark.asyncio
async def test_audit_all_raises_when_only_filter_matches_nothing(tmp_path):
    """audit_all raises FileNotFoundError when only filter matches no modules."""
    _seed_module(tmp_path, "1 PLANO", "1 PLANO.md")

    with pytest.raises(FileNotFoundError, match="matching"):
        await audit_all(
            tmp_path, only="nonexistent", chat_fn=make_fake_chat([]), delay_seconds=0
        )


@pytest.mark.asyncio
async def test_audit_all_missing_methodology_raises(tmp_path):
    """If methodology file for a module is missing, audit_all propagates FileNotFoundError."""
    t_dir = tmp_path / "transcripts" / "5 HEADLINES"
    t_dir.mkdir(parents=True)
    (t_dir / "aula-1.md").write_text("conteúdo", encoding="utf-8")
    (tmp_path / "methodology").mkdir(parents=True)
    # Intentionally no methodology file for "5 HEADLINES".

    with pytest.raises(FileNotFoundError, match="methodology"):
        await audit_all(tmp_path, chat_fn=make_fake_chat([]), delay_seconds=0)
