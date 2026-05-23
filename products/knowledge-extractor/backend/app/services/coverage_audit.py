"""Step 2 — transcript→methodology coverage audit.

For each module, compares the raw transcripts (source of truth) against the
consolidated methodology and produces an anonymized markdown report that scores
coverage and tags each lesson [Absorvido] / [Parcial] / [Ausente].

Token-safe map-reduce: when the combined transcript text for a module exceeds
MAP_REDUCE_THRESHOLD_CHARS, each transcript is first compressed to a compact
anonymized inventory (map), then all inventories are reduced with the methodology
into the final report. This prevents 30 k TPM-tier overflow on large modules.

LLM injection follows the same pattern as `methodology_service` so the service
is fully testable without network.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.integrations.llm import chat_completion
from app.logging_config import get_logger
from app.services.text_utils import strip_code_fence

logger = get_logger(__name__)

# Type alias — mirrors methodology_service.ChatFn (DRY: reuse the same alias shape).
ChatFn = Callable[..., Awaitable[str]]

# When combined transcript text exceeds this threshold, map-reduce is used.
# ~12 k chars ≈ ~3 k tokens, safely below the 30 k TPM per-call budget when the
# methodology text and system prompt are also counted.
MAP_REDUCE_THRESHOLD_CHARS = 12_000

# ---------------------------------------------------------------------------
# Shared privacy/atemporality policy — same intent as methodology_service._POLICY.
# Appended to every system prompt so the LLM never echoes names or results.
# ---------------------------------------------------------------------------
_POLICY = (
    " Regras OBRIGATÓRIAS: (1) NÃO cite nomes de pessoas, perfis, @s, marcas, "
    "clientes ou alunos — anonimize/omita (privacidade). (2) NÃO inclua números de "
    "resultado/desempenho (views, seguidores, faturamento, 'X de Y vídeos', "
    "crescimento) — resultados passados enganam. (3) Converta todo exemplo "
    "específico em PADRÃO/FÓRMULA generalizável. (4) Números intrínsecos ao método "
    "('os 3 segundos', 'os 7 gatilhos') podem ficar. Apenas a metodologia, crua."
)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_MAP_SYSTEM = (
    "Você é um analista que lê um TRANSCRITO bruto de aula e extrai um inventário "
    "compacto e anonimizado de conteúdo metodológico útil. Português do Brasil. "
    "Liste os conceitos, frameworks, exercícios e táticas distintos presentes no "
    "transcrito — um item por linha, sem sub-estrutura, sem julgamento de cobertura. "
    "Seja exaustivo mas conciso (sem paráfrase desnecessária)." + _POLICY
)

_MAP_USER = """\
Transcrito da aula (anonimizado ao processar):
{transcript}

Retorne SOMENTE a lista de itens metodológicos (sem seções, sem markdown elaborado).
"""

_REDUCE_SYSTEM = (
    "Você é um auditor especialista que avalia a cobertura de uma metodologia "
    "consolidada a partir das TRANSCRIÇÕES brutas de aulas de um curso de social "
    "media. Português do Brasil. Sua saída é um relatório de auditoria estruturado "
    "em markdown, detalhado e acionável." + _POLICY
)

_REDUCE_USER = """\
## Módulo auditado
{module}

## Inventário de conteúdo metodológico dos transcritos (fonte da verdade)
{inventories}

## Metodologia consolidada (o que foi absorvido)
{methodology}

---

Produza um relatório de auditoria em português do Brasil com as seguintes seções
**exatamente na ordem abaixo** (use os títulos em negrito como cabeçalhos H2):

## Veredito de cobertura

**Score: X / 10**

Parágrafo de síntese explicando o nível de cobertura. Liste as lacunas mais graves
numeradas. Seja específico: o que o transcrito contém que a metodologia não captura.

## Inventário de conteúdo útil nos transcritos (anonimizado)

Para cada aula / bloco temático identificado nos inventários, crie uma subseção
(`###`) e classifique com uma tag em negrito:
- **[Absorvido]** — conteúdo fielmente capturado na metodologia.
- **[Parcial]** — absorvido parcialmente; explique o que se perdeu.
- **[Ausente]** — não aparece na metodologia; descreva o conteúdo ausente.

Sob cada tag, inclua uma subseção **Conteúdo útil não absorvido** (se houver) com
bullet points descritivos e acionáveis.

## Lacunas a absorver (acionável)

Tabela markdown com colunas: `# | Lacuna | Aula/bloco fonte | Impacto`
(Impacto: Alto / Médio / Baixo). Ordenar por impacto decrescente.

## Observações de anonimização

Lista de observações sobre o que foi anonimizado / omitido neste relatório e por quê.
"""

# Prompt path for small input (fits in one call — no map phase needed).
_DIRECT_SYSTEM = (
    "Você é um auditor especialista que avalia a cobertura de uma metodologia "
    "consolidada a partir das TRANSCRIÇÕES brutas de aulas de um curso de social "
    "media. Português do Brasil. Sua saída é um relatório de auditoria estruturado "
    "em markdown, detalhado e acionável." + _POLICY
)

_DIRECT_USER = """\
## Módulo auditado
{module}

## Transcritos das aulas (fonte da verdade — anonimizar ao processar)
{transcripts}

## Metodologia consolidada (o que foi absorvido)
{methodology}

---

Produza um relatório de auditoria em português do Brasil com as seguintes seções
**exatamente na ordem abaixo** (use os títulos em negrito como cabeçalhos H2):

## Veredito de cobertura

**Score: X / 10**

Parágrafo de síntese explicando o nível de cobertura. Liste as lacunas mais graves
numeradas. Seja específico: o que o transcrito contém que a metodologia não captura.

## Inventário de conteúdo útil nos transcritos (anonimizado)

Para cada aula / bloco temático, crie uma subseção (`###`) e classifique:
- **[Absorvido]** — conteúdo fielmente capturado na metodologia.
- **[Parcial]** — absorvido parcialmente; explique o que se perdeu.
- **[Ausente]** — não aparece na metodologia; descreva o conteúdo ausente.

Sob cada tag, inclua **Conteúdo útil não absorvido** (se houver) com bullets
descritivos e acionáveis.

## Lacunas a absorver (acionável)

Tabela markdown com colunas: `# | Lacuna | Aula/bloco fonte | Impacto`
(Impacto: Alto / Médio / Baixo). Ordenar por impacto decrescente.

## Observações de anonimização

Lista de observações sobre o que foi anonimizado / omitido neste relatório e por quê.
"""

# Header prepended to every generated report.
_REPORT_HEADER = """\
> **Política de anonimização:** este documento não contém nomes de pessoas, perfis
> ou marcas presentes nos transcritos brutos; resultados numéricos foram omitidos;
> exemplos concretos foram convertidos em modelos/padrões reutilizáveis.

---

"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def audit_module(
    module: str,
    transcripts: list[str],
    methodology_text: str,
    *,
    chat_fn: ChatFn = chat_completion,
    model: Optional[str] = None,
    delay_seconds: int = 0,
) -> str:
    """Audit one module's transcript coverage against the consolidated methodology.

    Returns an anonymized markdown report (Veredito + score /10, Inventário tagged
    [Absorvido]/[Parcial]/[Ausente], Lacunas acionáveis, Observações).

    Token-safe map-reduce: if combined transcripts exceed MAP_REDUCE_THRESHOLD_CHARS,
    each transcript is first mapped to a compact inventory, then all inventories are
    reduced into the final report. Otherwise a single call is made.
    """
    combined = "\n\n---\n\n".join(transcripts)

    if len(combined) > MAP_REDUCE_THRESHOLD_CHARS:
        report = await _audit_map_reduce(
            module=module,
            transcripts=transcripts,
            methodology_text=methodology_text,
            chat_fn=chat_fn,
            model=model,
            delay_seconds=delay_seconds,
        )
    else:
        report = await _audit_direct(
            module=module,
            combined=combined,
            methodology_text=methodology_text,
            chat_fn=chat_fn,
            model=model,
        )

    return f"# Auditoria de Cobertura — {module}\n\n{_REPORT_HEADER}{report}"


async def audit_all(
    data_dir: Path,
    *,
    chat_fn: ChatFn = chat_completion,
    only: Optional[str] = None,
    model: Optional[str] = None,
    delay_seconds: int = 20,
) -> dict[str, Path]:
    """Audit all modules found under data_dir/transcripts/ against data_dir/methodology/.

    For each module folder under `data_dir/transcripts/`, reads its *.md files as
    transcripts, reads the matching `data_dir/methodology/<module>.md`, calls
    `audit_module`, and writes the report to `doc/analysis/modulo-<n>.md` relative
    to the repo root (Path('doc/analysis')).

    `only` filters modules by case-insensitive substring match on the folder name.

    Returns {module_name: report_path}.
    """
    transcripts_dir = data_dir / "transcripts"
    methodology_dir = data_dir / "methodology"
    # Reports go to doc/analysis/ relative to the repo root.
    # data_dir is typically <repo_root>/data, so repo root is data_dir.parent.
    doc_dir = data_dir.parent / "doc" / "analysis"
    doc_dir.mkdir(parents=True, exist_ok=True)

    if not transcripts_dir.is_dir():
        raise FileNotFoundError(
            f"Transcripts directory not found: {transcripts_dir}. "
            "Run transcription first."
        )

    # Collect module folders (direct children of transcripts_dir).
    module_dirs = sorted(
        p for p in transcripts_dir.iterdir() if p.is_dir()
    )

    if only:
        module_dirs = [d for d in module_dirs if only.lower() in d.name.lower()]

    if not module_dirs:
        raise FileNotFoundError(
            f"No module folders found under {transcripts_dir}"
            + (f" matching '{only}'" if only else "")
            + "."
        )

    results: dict[str, Path] = {}

    for i, module_dir in enumerate(module_dirs):
        if i > 0 and delay_seconds:
            await asyncio.sleep(delay_seconds)

        module_name = module_dir.name
        transcript_files = sorted(module_dir.glob("*.md"))

        if not transcript_files:
            logger.warning("module %s: no *.md transcripts found, skipping", module_name)
            continue

        transcripts = [f.read_text(encoding="utf-8") for f in transcript_files]

        # Find matching methodology file — exact stem match, then fuzzy prefix match.
        methodology_text = _load_methodology(methodology_dir, module_name)

        logger.info(
            "auditing module: %s (%d transcripts, %d chars combined)",
            module_name,
            len(transcripts),
            sum(len(t) for t in transcripts),
        )

        report = await audit_module(
            module_name,
            transcripts,
            methodology_text,
            chat_fn=chat_fn,
            model=model,
            delay_seconds=0,  # pacing is handled at the audit_all level
        )

        # Write to doc/analysis/modulo-<n>.md.
        # Derive a short slug: take a leading digit sequence from the folder name,
        # or fall back to a sanitized version of the full name.
        slug = _module_slug(module_name)
        report_path = doc_dir / f"modulo-{slug}.md"
        report_path.write_text(report, encoding="utf-8")
        results[module_name] = report_path
        logger.info("wrote audit report: %s", report_path)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _audit_direct(
    module: str,
    combined: str,
    methodology_text: str,
    *,
    chat_fn: ChatFn,
    model: Optional[str],
) -> str:
    """Single-call path: all transcripts fit in one request."""
    messages = [
        {"role": "system", "content": _DIRECT_SYSTEM},
        {
            "role": "user",
            "content": _DIRECT_USER.format(
                module=module,
                transcripts=combined,
                methodology=methodology_text,
            ),
        },
    ]
    return strip_code_fence(await chat_fn(messages, model=model))


async def _audit_map_reduce(
    module: str,
    transcripts: list[str],
    methodology_text: str,
    *,
    chat_fn: ChatFn,
    model: Optional[str],
    delay_seconds: int,
) -> str:
    """Map-reduce path: compress each transcript first, then reduce to report."""
    inventories: list[str] = []

    for idx, transcript in enumerate(transcripts):
        if idx > 0 and delay_seconds:
            await asyncio.sleep(delay_seconds)

        messages = [
            {"role": "system", "content": _MAP_SYSTEM},
            {
                "role": "user",
                "content": _MAP_USER.format(transcript=transcript),
            },
        ]
        inventory = strip_code_fence(await chat_fn(messages, model=model))
        inventories.append(inventory)

    if delay_seconds:
        await asyncio.sleep(delay_seconds)

    # Reduce: numbered inventories → final report.
    numbered = "\n\n".join(
        f"### Inventário {i + 1}\n{inv}" for i, inv in enumerate(inventories)
    )
    messages = [
        {"role": "system", "content": _REDUCE_SYSTEM},
        {
            "role": "user",
            "content": _REDUCE_USER.format(
                module=module,
                inventories=numbered,
                methodology=methodology_text,
            ),
        },
    ]
    return strip_code_fence(await chat_fn(messages, model=model))


def _load_methodology(methodology_dir: Path, module_name: str) -> str:
    """Load the methodology file for a module; raises FileNotFoundError if absent."""
    # Exact stem match first.
    exact = methodology_dir / f"{module_name}.md"
    if exact.is_file():
        return exact.read_text(encoding="utf-8")

    # Fuzzy: find a file whose stem starts with the same leading digit(s).
    leading = _leading_digits(module_name)
    if leading:
        candidates = sorted(methodology_dir.glob("*.md"))
        for c in candidates:
            if _leading_digits(c.stem) == leading:
                return c.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"No methodology file found for module '{module_name}' in {methodology_dir}. "
        "Expected a file whose name starts with the same digit(s) as the module folder."
    )


def _leading_digits(name: str) -> str:
    """Return the leading digit sequence from a string (e.g. '7 Foo' → '7')."""
    result = []
    for ch in name.strip():
        if ch.isdigit():
            result.append(ch)
        else:
            break
    return "".join(result)


def _module_slug(module_name: str) -> str:
    """Derive a short slug for the report filename.

    '7 CONSTRUINDO SEU NUCLEO' → '7'
    'modulo-3'                 → '3'
    'Foobar'                   → 'foobar'
    """
    digits = _leading_digits(module_name)
    if digits:
        return digits
    return module_name.lower().replace(" ", "-")


__all__ = ["audit_module", "audit_all", "MAP_REDUCE_THRESHOLD_CHARS"]
