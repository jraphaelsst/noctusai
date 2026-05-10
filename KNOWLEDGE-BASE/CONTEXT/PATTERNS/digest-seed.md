# Digest service template-method pattern

> Four products grew the same digest-service shape: window of data → fetch → aggregate → narrate via LLM → render bodies → return. The shape is canonical orchestration; per-product LLM prompts + Jinja context-dict keys remain the domain-binding boundary. Lifted into `noctusai_lib.domain.digest.BaseDigestService` 2026-05-10.

## Surface

```python
from noctusai_lib.domain.digest import BaseDigestService, DigestWindow, DigestResult

class WeeklyReviewService(BaseDigestService):
    """Daily Life weekly-review digest."""

    # Required overrides (5 abstract slots):
    async def _fetch_window(self, window: DigestWindow) -> Any: ...
    async def _aggregate(self, raw: Any) -> Any: ...
    async def _generate_narrative(self, aggregated: Any) -> str: ...
    async def _render_bodies(self, narrative: str, aggregated: Any) -> tuple[str, str]: ...
    def _build_subject(self, aggregated: Any) -> str: ...

    # Concrete defaults you MAY override:
    def _build_summary(self, aggregated: Any) -> str: ...
    async def _initial_recipients(self, ...) -> list[str]: ...
```

## Types

- **`DigestWindow`** — loose envelope (`start`, `end`, `org_id`, `extra: dict`). `extra` carries non-uniform per-product context (e.g. `campaign_id` for mailing) so subclasses pass opaque envelopes between their own methods without forcing a sealed schema on the base.
- **`DigestResult`** — uniform return: `(digest, narrative, summary, recipients)`. The base's `run(window)` template method returns this shape; per-service top-level wrappers may repackage at the edge for legacy callers.

## Adopters (4)

- `core/audit_digest_service.py` → `AuditDigestService`
- `daily-life/weekly_review_service.py` → `WeeklyReviewService`
- `mailing/campaign_debrief_service.py` → `CampaignDebriefService` (uses internal `_CampaignNotFound` sentinel for the Optional-return path; wrapper translates back to `None`)
- `personal-finance/monthly_narrative_service.py` → `MonthlyNarrativeService`

**Public APIs preserved verbatim.** Every existing module-level `build_X` / `send_X` function still exists at the same import path with its original signature + return-tuple shape. Class delegates internally; **27 test imports across 4 services untouched**. This is the **internal-uniform / edge-adapt** pattern — when public APIs differ in subtle ways (3-tuple vs dict vs Optional[3-tuple] vs 4-tuple), normalize internally + adapt at the edge.

## When to use it

- Window-of-data → narrative report → multi-format output
- LLM-narrated (the shared shell handles the LLM call shape)
- HTML + plaintext bodies for delivery (email shape)
- Empty-window short-circuit acceptable

## When NOT to use it (catalogued non-fits)

- **No LLM narrative.** ERP's `metas_digest_service.py` reads `top_rankings` from the router and returns a custom legacy dict shape consumed by gamification UI. Pre-existing accept-with-rationale entry; not a digest.
- **Different delivery surface.** Daily-life's `daily_brief_service.py` produces a chip (≤32 chars) + summary (≤200 chars) for an in-app badge, NOT html+text email bodies. Different LLM budget (`max_tokens=120`), bespoke truncation logic. Method-name overlap (`_aggregate`, `_fetch_window`) is **coincidental** — same lesson as the test-suites N=4 byte-identical filter.
- **Real-time / one-shot / single-row.** No window concept → not a digest.
- **Custom return-tuple shape.** If your service returns 4-tuples or product-specific dicts, the `DigestResult` shape doesn't fit cleanly — prefer accept-with-rationale over force-fit.

## The orchestration template

```python
async def run(self, window: DigestWindow) -> DigestResult:
    raw = await self._fetch_window(window)
    aggregated = await self._aggregate(raw)
    narrative = await self._generate_narrative(aggregated)
    html, plaintext = await self._render_bodies(narrative, aggregated)
    summary = self._build_summary(aggregated)
    subject = self._build_subject(aggregated)
    recipients = await self._initial_recipients(window, aggregated)
    return DigestResult(
        digest=Digest(subject=subject, html=html, plaintext=plaintext),
        narrative=narrative,
        summary=summary,
        recipients=recipients,
    )
```

The base is **pure orchestration — no IO**. Per `KB § PATTERNS/seed-fake-real-adapter.md`, the exemption test fires: a Fake here would exercise the same code as the Real. No Fake adapter needed.

## Why typed `Any` on extension points

Each `_fetch_window` returns a different envelope (dict / 3-tuple / Optional[3-tuple] / 2-tuple); each `_aggregate` returns a different shape (3-tuple / dict / 2-tuple / 4-tuple). Forcing a typed Protocol on either would either require data-shape forks per subclass or an `Any` escape hatch. The 4 services share **orchestration shape, not data shape** — the typed contract is on `DigestResult` (the public boundary) + on the orchestration sequence, not on the intermediate envelopes.

## Cross-references

- `noctusai_lib.integrations.llm` — LLM client used by `_generate_narrative` overrides
- `KB § PATTERNS/llm-usage.md` — token tracking + provider routing
- `KB § PATTERNS/accept-with-rationale.md § Per-product _render_bodies + _generate_narrative digest wrappers retained at N=4` — the wrappers are now methods of `XDigestService(BaseDigestService)` subclasses; the *boundary rationale* (per-product LLM prompts + Jinja context-dict keys) stands
- Source: `seed/lib/backend/noctusai_lib/domain/digest/base.py`
