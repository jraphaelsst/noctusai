"""Step 2 — methodology extraction.

Synthesizes the per-lesson summaries into reusable knowledge, in two levels:
1. per-module methodology (one synthesis per module's summaries), then
2. the unified course methodology (synthesis over the module-level outputs).

The LLM call is injected (`chat_fn`) so the orchestration is testable without
network — defaults to the real `chat_completion` seam.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.integrations.llm import chat_completion
from app.logging_config import get_logger
from app.services.text_utils import strip_code_fence

logger = get_logger(__name__)

ChatFn = Callable[..., Awaitable[str]]

# Shared privacy/atemporality policy — appended to both system prompts.
_POLICY = (
    " Regras OBRIGATÓRIAS: (1) NÃO cite nomes de pessoas, perfis, @s, marcas, "
    "clientes ou alunos — anonimize/omita (privacidade). (2) NÃO inclua números de "
    "resultado/desempenho (views, seguidores, faturamento, 'X de Y vídeos', "
    "crescimento) — resultados passados enganam. (3) Converta todo exemplo "
    "específico em PADRÃO/FÓRMULA generalizável. (4) Números intrínsecos ao método "
    "('os 3 segundos', 'os 7 gatilhos') podem ficar. Apenas a metodologia, crua."
)

# Provenance footer appended to each methodology doc — documents how it was made.
_PROVENANCE = """

---

## Procedência (como este material foi produzido)

- **Transcrição:** o áudio das aulas foi transcrito automaticamente pela engine de transcrição da OpenAI.
- **Resumos por aula:** gerados pela OpenAI (modelo gpt-4o) com um prompt de extração de metodologia *crua* — anonimizada (sem nomes de pessoas, perfis ou marcas) e atemporal (sem métricas de desempenho); exemplos convertidos em modelos/fórmulas reutilizáveis.
- **Avaliação e curadoria (Claude):** os resumos da OpenAI foram comparados às transcrições brutas; aulas fundamentais foram refinadas manualmente para recuperar nuances perdidas, mantendo a anonimização.
- **Síntese:** a metodologia foi consolidada pela OpenAI (gpt-4o) por módulo e montada neste manual.
- **Auditoria:** verificado sem nomes de pessoas/marcas e sem números de resultado.
"""


_MODULE_SYSTEM = (
    "Você é um especialista que destila a metodologia de um curso de social media a "
    "partir dos RESUMOS DETALHADOS das aulas. Português do Brasil, fiel e EXAUSTIVO "
    "nos detalhes acionáveis (mecanismos, frameworks, táticas, fórmulas de "
    "headline), porém puro e reutilizável." + _POLICY
)

_MODULE_USER = """\
Módulo: "{module}"

Abaixo estão os RESUMOS DETALHADOS das aulas deste módulo. Extraia a METODOLOGIA
do módulo em markdown DETALHADO e acionável, integrando e aprofundando todo o
conteúdo (não resuma em clichês). Seções:

## Visão geral do módulo
## Conceitos e princípios (com o mecanismo / o porquê)
## Framework / passo a passo (detalhado)
## Padrões e fórmulas (templates de headline/conteúdo, generalizados)
## Táticas e regras de execução
## Como aplicar (acionável)

Resumos detalhados das aulas:
{summaries}
"""

_COURSE_SYSTEM = (
    "Você é um estrategista que sintetiza a metodologia COMPLETA e DETALHADA de um "
    "curso de social media num manual reutilizável e atemporal. Português do "
    "Brasil, fiel, profundo e acionável." + _POLICY
)

_COURSE_USER = """\
Abaixo estão as metodologias detalhadas de cada módulo. Sintetize a METODOLOGIA
COMPLETA E UNIFICADA do método, como um manual rico e acionável (não superficial),
em markdown. Preserve mecanismos, frameworks, táticas e fórmulas; integre os
módulos numa progressão coerente:

# Manual da Metodologia

## Visão geral e filosofia
## Os pilares do método
## Encontrando assuntos virais (pesquisa)
## Headlines e a ciência da atenção (os gatilhos, um a um)
## Elementos de um conteúdo notável
## Identidade e posicionamento (núcleo de influência)
## Padrões e fórmulas de headline (biblioteca de templates)
## Framework end-to-end (do zero ao post)
## Checklist acionável
## Glossário de termos

Metodologias por módulo:
{modules}
"""


async def synthesize_module(
    module: str,
    summaries: list[str],
    *,
    chat_fn: ChatFn = chat_completion,
    model: Optional[str] = None,
) -> str:
    """Extract one module's methodology from its lesson summaries."""
    joined = "\n\n---\n\n".join(summaries)
    messages = [
        {"role": "system", "content": _MODULE_SYSTEM},
        {"role": "user", "content": _MODULE_USER.format(module=module, summaries=joined)},
    ]
    return strip_code_fence(await chat_fn(messages, model=model))


async def synthesize_course(
    module_syntheses: dict[str, str],
    *,
    chat_fn: ChatFn = chat_completion,
    model: Optional[str] = None,
) -> str:
    """Synthesize the unified course methodology from the per-module outputs."""
    blocks = [f"### {module}\n\n{text}" for module, text in module_syntheses.items()]
    messages = [
        {"role": "system", "content": _COURSE_SYSTEM},
        {"role": "user", "content": _COURSE_USER.format(modules="\n\n".join(blocks))},
    ]
    return strip_code_fence(await chat_fn(messages, model=model))


async def extract_methodology(
    data_dir: Path,
    *,
    chat_fn: ChatFn = chat_completion,
    model: Optional[str] = None,
    delay_seconds: int = 20,
) -> dict:
    """Read the (rich, anonymized) summaries; synthesize per-module + course methodology.

    Outputs: `data/methodology/<module>.md` and `data/METHODOLOGY.md`.

    Sources the v3 summaries (not raw transcripts): they already recover the detail
    the original terse summaries lost, and stay well under the OpenAI per-minute
    token limit (full per-module transcripts overflow a 30k TPM tier). `delay_seconds`
    paces calls to respect the aggregate per-minute limit.
    """
    summaries_dir = data_dir / "summaries"
    out_dir = data_dir / "methodology"

    modules: dict[str, list[str]] = {}
    for spath in sorted(summaries_dir.rglob("*.md")):
        rel = spath.relative_to(summaries_dir)
        module = rel.parent.as_posix() if rel.parent != Path(".") else "(uncategorized)"
        modules.setdefault(module, []).append(spath.read_text(encoding="utf-8"))

    if not modules:
        raise FileNotFoundError(
            f"No summaries found under {summaries_dir}. Run transcription first."
        )

    module_syntheses: dict[str, str] = {}
    for i, module in enumerate(sorted(modules)):
        if i > 0 and delay_seconds:
            await asyncio.sleep(delay_seconds)
        logger.info(
            "synthesizing module methodology: %s (%d summaries)",
            module, len(modules[module]),
        )
        text = await synthesize_module(module, modules[module], chat_fn=chat_fn, model=model)
        module_syntheses[module] = text
        mpath = out_dir / f"{module}.md"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(f"# Metodologia — {module}\n\n{text}\n{_PROVENANCE}", encoding="utf-8")

    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    logger.info("synthesizing unified course overview")
    overview = await synthesize_course(module_syntheses, chat_fn=chat_fn, model=model)

    # The master doc = synthesized at-a-glance overview + the FULL rich per-module
    # methodologies appended. (Re-synthesizing into one doc re-compresses the
    # detail into one-liners; assembling preserves it.)
    course_path = data_dir / "METHODOLOGY.md"
    course_path.write_text(
        _assemble_manual(overview, module_syntheses) + _PROVENANCE, encoding="utf-8"
    )

    return {
        "modules": list(module_syntheses),
        "module_files": [str(out_dir / f"{m}.md") for m in module_syntheses],
        "course_file": str(course_path),
    }


def _assemble_manual(overview: str, module_syntheses: dict[str, str]) -> str:
    """Master manual = at-a-glance overview + full per-module methodologies appended."""
    parts = [overview.strip(), "\n\n---\n\n# Detalhamento por Módulo"]
    for module in sorted(module_syntheses):
        parts.append(f"\n\n---\n\n{module_syntheses[module].strip()}")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Deterministic manual assembler (no LLM — reads on-disk per-module files)
# ---------------------------------------------------------------------------

# Filenames excluded from the numbered-module section.
_ASSEMBLER_EXCLUDE = frozenset(
    {"_FRONT.md", "_BACK.md", "REFERENCIAS.md", "ESTRUTURAS-DE-POST.md"}
)
# Any filename whose stem starts with "ESQUEMA" is also excluded (covers
# ESQUEMA-BASE-DE-CONHECIMENTO.md and any future variants).
_ESQUEMA_PREFIX = "ESQUEMA"

_REFS_SECTION = """\
## Referências e Esquema

- **Base bibliográfica completa:** [`methodology/REFERENCIAS.md`](methodology/REFERENCIAS.md)
- **Esquema da base de conhecimento:** [`methodology/ESQUEMA-BASE-DE-CONHECIMENTO.md`](methodology/ESQUEMA-BASE-DE-CONHECIMENTO.md)
"""


def _leading_int(name: str) -> int:
    """Return the leading integer of *name* (filename stem), or -1 if none.

    Examples::

        "1 PLANO PARA CRESCER NO INSTAGRAM.md" → 1
        "10-MEDICAO-E-FEEDBACK.md"             → 10
        "REFERENCIAS.md"                        → -1
    """
    m = re.match(r"^(\d+)", name)
    return int(m.group(1)) if m else -1


def _is_numbered_module(path: "Path") -> bool:  # noqa: F821  (forward ref for type hint)
    """True iff the file belongs in the Detalhamento section."""
    name = path.name
    if name in _ASSEMBLER_EXCLUDE:
        return False
    if path.stem.upper().startswith(_ESQUEMA_PREFIX):
        return False
    return _leading_int(name) >= 0


def assemble_manual_from_files(data_dir: "Path") -> str:  # noqa: F821
    """Build the full METHODOLOGY.md content deterministically from on-disk files.

    Layout::

        _FRONT.md content
        \\n\\n---\\n\\n# Detalhamento por Módulo
        (each numbered module file, numeric order, joined with \\n\\n---\\n\\n)
        \\n\\n---\\n\\n
        ESTRUTURAS-DE-POST.md content
        \\n\\n---\\n\\n
        ## Referências e Esquema  (short pointer section)
        _BACK.md content

    Excludes _FRONT.md / _BACK.md / REFERENCIAS.md / ESQUEMA-* / ESTRUTURAS-*
    from the numbered-module concatenation.

    Args:
        data_dir: Path to the ``data/`` directory (parent of ``methodology/``).

    Returns:
        The assembled manual as a UTF-8 string.

    Raises:
        FileNotFoundError: if ``_FRONT.md``, ``_BACK.md``, or
            ``ESTRUTURAS-DE-POST.md`` are missing from ``data/methodology/``.
    """
    methodology_dir = data_dir / "methodology"

    front_path = methodology_dir / "_FRONT.md"
    back_path = methodology_dir / "_BACK.md"
    estruturas_path = methodology_dir / "ESTRUTURAS-DE-POST.md"

    for required in (front_path, back_path, estruturas_path):
        if not required.exists():
            raise FileNotFoundError(
                f"Required file missing for manual assembly: {required}"
            )

    front = front_path.read_text(encoding="utf-8").rstrip()
    back = back_path.read_text(encoding="utf-8").rstrip()
    estruturas = estruturas_path.read_text(encoding="utf-8").rstrip()

    # Collect and sort numbered module files
    numbered = sorted(
        (p for p in methodology_dir.iterdir() if p.is_file() and _is_numbered_module(p)),
        key=lambda p: _leading_int(p.name),
    )

    sep = "\n\n---\n\n"

    parts: list[str] = [front]
    parts.append(sep + "# Detalhamento por Módulo")
    for mod_path in numbered:
        parts.append(sep + mod_path.read_text(encoding="utf-8").rstrip())
    parts.append(sep + estruturas)
    parts.append(sep + _REFS_SECTION.rstrip())
    parts.append(sep + back)

    return "\n".join(parts) + "\n"


def build_manual(data_dir: "Path") -> "Path":  # noqa: F821
    """Write the assembled manual to ``data_dir/METHODOLOGY.md`` and return the path.

    Deterministic and idempotent: calling it twice produces the same file.

    Args:
        data_dir: Path to the ``data/`` directory.

    Returns:
        The ``Path`` to the written ``METHODOLOGY.md``.
    """
    content = assemble_manual_from_files(data_dir)
    out_path = data_dir / "METHODOLOGY.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


__all__ = [
    "extract_methodology",
    "synthesize_module",
    "synthesize_course",
    "assemble_manual_from_files",
    "build_manual",
]
