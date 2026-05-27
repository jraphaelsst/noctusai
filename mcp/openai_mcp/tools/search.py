"""openai.search.kb + openai.search.code — semantic search over the noc
KB and codebase.

Implementation: facade over the existing `noctusai/tools/noctus/dev/
kb_embeddings.py` + `code_embeddings.py` (which already index KB + code
into local SQLite + sqlite-vec). This connector exposes them as a clean
`openai.search.*` surface so any agent can call them without needing
the noctusai MCP loaded — and so the search lives semantically next to
the embedding service that powers it.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from mcp.types import Tool

from _kit.errors import typed_error

from ..types import SearchHit, SearchInput, SearchOutput

logger = logging.getLogger(__name__)


def _add_noctusai_to_path() -> None:
    """Put `mcp/noctusai/` on sys.path so we can import the existing
    embedding modules. Idempotent."""
    here = Path(__file__).resolve()
    noctusai_root = here.parents[2] / "noctusai"
    if str(noctusai_root) not in sys.path:
        sys.path.insert(0, str(noctusai_root))


def _normalize_hits(raw_hits: list, score_key: str = "score") -> list[SearchHit]:
    """Map both kb_embeddings.search() and code_embeddings.search() output
    shapes onto the unified SearchHit schema. KB hits expose `path` +
    `chunk_text` + `score`; code hits add `symbol`."""
    out: list[SearchHit] = []
    for h in raw_hits:
        out.append(SearchHit(
            path=h.get("path") or h.get("file_path") or "",
            symbol=h.get("symbol") or h.get("symbol_name"),
            chunk_text=h.get("chunk_text") or h.get("text") or "",
            score=float(h.get(score_key, 0.0)),
        ))
    return out


async def handle_search_kb(args: dict) -> dict:
    try:
        inp = SearchInput(**args)
    except Exception as exc:
        return {"error": typed_error(exc, status=422)}
    _add_noctusai_to_path()
    try:
        from tools.noctus.dev import kb_embeddings as kbe  # type: ignore[import]
    except ImportError as exc:
        return {"error": typed_error(exc, status=503)}
    try:
        # Ensure LLM is configured so the embedding query works.
        _ensure_llm_for_search()
        raw = kbe.search(inp.query, top_k=inp.top_k)
    except Exception as exc:
        return {"error": typed_error(exc, status=502)}
    hits = _normalize_hits(raw)
    if inp.min_score > 0.0:
        hits = [h for h in hits if h.score >= inp.min_score]
    return SearchOutput(ok=True, query=inp.query, hits=hits).model_dump()


async def handle_search_code(args: dict) -> dict:
    try:
        inp = SearchInput(**args)
    except Exception as exc:
        return {"error": typed_error(exc, status=422)}
    _add_noctusai_to_path()
    try:
        from tools.noctus.dev import code_embeddings as cee  # type: ignore[import]
    except ImportError as exc:
        return {"error": typed_error(exc, status=503)}
    try:
        _ensure_llm_for_search()
        raw = cee.search(inp.query, top_k=inp.top_k)
    except Exception as exc:
        return {"error": typed_error(exc, status=502)}
    hits = _normalize_hits(raw)
    if inp.min_score > 0.0:
        hits = [h for h in hits if h.score >= inp.min_score]
    return SearchOutput(ok=True, query=inp.query, hits=hits).model_dump()


_LLM_READY = False


def _ensure_llm_for_search() -> None:
    """Configure noctusai_lib's LLM client if not already (the embedding
    query path requires it). Idempotent; matches the noctusai CLI's
    `_ensure_llm_configured` helper but local to this connector."""
    global _LLM_READY
    if _LLM_READY:
        return
    import os
    try:
        from noctusai_lib import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config
        try:
            get_llm_config()
            _LLM_READY = True
            return
        except RuntimeError:
            pass
        configure_llm(LLMConfig(
            key_provider=lambda provider, org_id=None: os.environ.get(
                f"{provider.upper()}_API_KEY"
            ),
        ))
        _LLM_READY = True
    except ImportError:
        pass  # silent — handler will report 503


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="openai.search.kb",
            description=(
                "Semantic search over the noc knowledge base (KNOWLEDGE-BASE/**/*.md). "
                "Returns top-k hits ranked by cosine similarity to the query. "
                "Useful for: 'where is the canonical pattern for X', 'what KB "
                "doc covers Y'. Use openai.search.code for source-tree search."
            ),
            inputSchema=SearchInput.model_json_schema(),
        ),
        Tool(
            name="openai.search.code",
            description=(
                "Semantic search over the noc codebase (mcp/**/*.py + "
                "noctusai_lib/**/*.py + products/seed/**). Returns top-k hits "
                "with file path + symbol name + chunk text + cosine score. "
                "Useful for: 'where do we implement X', 'show me how Y is wired'."
            ),
            inputSchema=SearchInput.model_json_schema(),
        ),
    ]


HANDLERS: dict[str, Any] = {
    "openai.search.kb": handle_search_kb,
    "openai.search.code": handle_search_code,
}


def register(server) -> None:
    pass
