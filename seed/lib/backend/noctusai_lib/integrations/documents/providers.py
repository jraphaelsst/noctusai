"""Which vendor + which model reads a document — the ONE place the pins live.

A document read has two LLM rungs, and each is pinned exactly once here:

1. **Transcription (vision)** — `OCR_MODELS`. A scanned page → its verbatim
   text. Consumed by `transcription.LadderDocumentTranscriber` and, through
   it, by every identity / matrícula / certidão / imóvel-document reader,
   plus `media.RealMediaResolver`'s image and PDF paths.
2. **Analysis (chat over the document's text)** — `DOCUMENT_ANALYSIS_MODELS`.
   The structured-JSON read (número / emissão / validade / resultado /
   inscrição) and the certidão's free-text summary. Consumed by social-
   wiring's `certidoes.service` and `imovel_hub.documentos_service`.

Both maps are keyed by provider because a model id is not portable across
vendors: `gpt-4.1-mini` sent to Anthropic is a 404 that reads like a broken
key. Selecting a provider MUST select its model unless the caller overrides
both.

WHY THE DEFAULT IS ANTHROPIC (owner directive, 2026-09-22)
-----------------------------------------------------------
"OpenAI has no credit — swap the mechanism fully to Claude, preferably the
cheapest one that does the job." Before this, an org that never saved an
`llm_vision_provider` / `llm_chat_provider` row fell through to "openai" and
every identity / document read came back `insufficient_quota`. The canonical
answer for DOCUMENT reads is now Claude — a seed-level default (the
seed-canonical-defaults rule), not a per-product override. It is still a
MANUAL switch: an org that explicitly picked "openai" or "gemini" keeps it,
and nothing here ever fails over from one vendor to another (a missing key is
a named `missing_credentials` error, never a silent swap).

This does NOT move the process-wide `LLMConfig.default_provider` (still
"openai", `noctusai_seed.llm_defaults`): non-document chat (email copy,
media generation, chatbots) is a different purchase, and embeddings cannot
move at all — Anthropic has no embeddings endpoint.

WHY HAIKU 4.5 ON BOTH RUNGS — MEASURED, NOT ASSUMED (2026-09-22)
----------------------------------------------------------------
The 11 scan variants of the synthetic e2e fixture set
(`products/social-wiring/backend/tests/e2e_extracao/fixtures/*_scan.pdf`)
were read once per model through this module's real transcriber, fed into the
seed identity / matrícula parsers and social-wiring's structured-JSON reads,
and scored against `esperado.json`:

    rung / model                 fields ok/wrong/missing   mean text sim   USD
    OCR+parsers  haiku-4-5       42 / 0 / 0                0.998           0.034
    OCR+parsers  opus-5          42 / 0 / 0                1.000           0.398
    OCR+JSON     haiku-4-5       10 / 0 / 0                0.999    (chat) 0.004
    OCR+JSON     opus-5          10 / 0 / 0                1.000    (chat) 0.023
    JSON isolated (text-layer input): haiku 10/10, opus 10/10.

Haiku matched the stronger model on every scored field at ~1/11th the OCR
cost, so it is pinned on both rungs. The residual text-similarity gap
(0.998 vs 1.000) is punctuation/spacing that no parser consumed. Re-measure
on real documents before moving a pin back up; change the pin HERE only.

The measurement ran against the dated snapshot `claude-haiku-4-5-20251001`;
the pin is the alias `claude-haiku-4-5`, which resolves to that snapshot and
is the id the rest of the fleet (and the pricing catalog,
`llm.models`) already uses — a dated id would be a second, unpriced spelling
of the same model.

🔴 Real-document measurement is still OWED: the synthetic set is clean
typeset print. The same harness over prod's uploaded documents was blocked
on a read permission 2026-09-22 — see the delivery note for that dispatch.
"""
from __future__ import annotations

__all__ = [
    "DEFAULT_DOCUMENT_PROVIDER",
    "DOCUMENT_ANALYSIS_MODELS",
    "DOCUMENT_PROVIDERS",
    "OCR_MODELS",
]

#: The vendor a document read uses when the org chose nothing. See the module
#: docstring for why this is Anthropic and why it is not a fallback.
DEFAULT_DOCUMENT_PROVIDER = "anthropic"

#: Rung 1 — the vision model that transcribes a scanned page, PER PROVIDER.
OCR_MODELS: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    # Cheapest Claude that read every synthetic scan field correctly — see
    # the module docstring's measurement table.
    "anthropic": "claude-haiku-4-5",
    # Gemini's flash tier is the cheapest of the three; it stays as a third
    # manual option so an agency out of credit at one vendor is never left
    # with a single alternative.
    "gemini": "gemini-2.0-flash",
}

#: Rung 2 — the chat model that reads a document's TEXT (structured JSON
#: fields, certidão summary), PER PROVIDER. Separate from `OCR_MODELS` because
#: the two capabilities are priced and tuned separately, even where today the
#: same id is pinned on both.
DOCUMENT_ANALYSIS_MODELS: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-2.0-flash",
}

#: Every vendor a document read can be routed to — the `allowed` set a
#: `resolve_llm_provider("vision" | "chat", ...)` call for documents passes.
DOCUMENT_PROVIDERS: tuple[str, ...] = tuple(OCR_MODELS)
