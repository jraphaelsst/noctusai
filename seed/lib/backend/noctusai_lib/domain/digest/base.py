"""`BaseDigestService` — template-method orchestrator for digest pipelines.

Background
----------
The four narrative-using digest services
(`core/audit_digest_service`, `daily-life/weekly_review_service`,
`mailing/campaign_debrief_service`, `personal-finance/monthly_narrative_service`)
all share the same five-step shape:

    fetch a window of raw rows
      → aggregate into structured input for the LLM
      → generate a narrative
      → render html+text bodies
      → assemble Digest(subject, html, text)

After the 2026-05-03 `digest-helpers-absorption` project, the
`narrative()`, `render_digest_pair()`, and `build_and_send()` *helpers*
already live in `noctusai_lib.domain.digest`. What was still per-product
is the **orchestration shape** — each service replicated the
`fetch → aggregate → narrative → render → assemble` flow as a
hand-rolled `build_X(...)` function.

`BaseDigestService` formalizes the orchestration as a template-method
class. Each per-product service subclasses it and implements:

- `_fetch_window(window)`  — pull raw rows from supabase
- `_aggregate(raw)`         — shape into structured input for the LLM
- `_generate_narrative(agg, window)` — call `narrative(...)` with
  product-specific prompts
- `_render_bodies(agg, narrative)`  — call `render_digest_pair(...)`
  with the product-specific Jinja context
- `_build_subject(agg)`     — assemble the email subject line
- `_initial_recipients(raw)` — optional override for the rare fan-out
  path (core/audit_digest fans out to all admins). Default returns `[]`.

The base class's `run(window)` method orchestrates: it threads
`window` to `_fetch_window`, passes the raw envelope through `_aggregate`,
calls `_generate_narrative`, calls `_render_bodies`, builds the `Digest`,
and returns a `DigestResult` envelope.

Public-API preservation
-----------------------
**Each service keeps its existing module-level free-functions**
(`build_review`, `build_digest`, `build_debrief`, `build_narrative`,
`send_X`, plus `_aggregate`, `_render_bodies`, `_fetch_window`) so
existing routers and tests keep importing from the same paths. The
free-functions are thin wrappers that:

- instantiate `XDigestService(client=db, org_id=...)`
- call `await svc.run(window=DigestWindow(...))`
- adapt `DigestResult` to the legacy tuple shape

The class delegates to the same module-level helpers — they're the
single source of truth for the per-product `_aggregate`/`_render_bodies`
logic, exactly preserving what the existing tests target.

Excluded by accept-with-rationale
---------------------------------
- `erp-imobiliario/metas_digest_service` — no LLM narrative path,
  takes `top_rankings` from the router, returns a custom legacy dict
  shape. See `KB § PATTERNS/accept-with-rationale.md` (entry: "ERP
  metas digest does NOT use `noctusai_lib.domain.digest`"). Forcing
  it through the base would either bloat the contract with
  optional-LLM branches or destroy the bespoke return shape the
  gamification UI consumes.
- `daily-life/daily_brief_service` — produces a chip (≤32 chars) +
  summary (≤200 chars) for an in-app badge, NOT html+text email
  bodies. Different delivery surface; different LLM budget; method
  names overlap (`_aggregate`, `_fetch_window`) only coincidentally.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from noctusai_lib.integrations.email.digest import Digest

from .narrative import narrative as _narrative_helper
from .types import DigestResult, DigestWindow


class BaseDigestService(ABC):
    """Template-method orchestrator for narrative-using digest services.

    Subclasses implement `_fetch_window`, `_aggregate`,
    `_generate_narrative`, `_render_bodies`, `_build_subject` (and
    optionally `_initial_recipients`). The base's `run(window)` method
    threads the window through the pipeline and returns a
    `DigestResult` envelope.

    Example (sketch):

        class WeeklyReviewService(BaseDigestService):
            async def _fetch_window(self, window): ...
            def _aggregate(self, raw): ...
            async def _generate_narrative(self, agg, window): ...
            def _render_bodies(self, agg, narrative): ...
            def _build_subject(self, agg, window): ...

        svc = WeeklyReviewService(client=db, org_id="org-1")
        result = await svc.run(DigestWindow(period_days=7,
                                            extra={"user_id": "u1"}))
        # result.digest, result.narrative, result.summary
    """

    def __init__(
        self,
        *,
        client: Any,
        org_id: Optional[str] = None,
    ) -> None:
        """Construct.

        Args:
            client: Supabase-shaped client used by `_fetch_window`.
                Typed `Any` because each subclass interacts with its
                own table-set; tightening would lock in the supabase
                SDK shape.
            org_id: Optional organization id threaded to the LLM
                helper for org-level credential resolution. Some
                products operate on user-scoped data and pass None.
        """
        self.client = client
        self.org_id = org_id

    # ------------------------------------------------------------------
    # Template method — the orchestrator.
    # ------------------------------------------------------------------

    async def run(self, window: DigestWindow) -> DigestResult:
        """Orchestrate fetch → aggregate → narrative → render → assemble.

        Returns a `DigestResult(digest, narrative, summary, recipients)`.
        Never raises on LLM failure — `_generate_narrative` is expected
        to delegate to `noctusai_lib.domain.digest.narrative()` which
        handles fallbacks. Raises on DB / Jinja / unexpected errors —
        the per-product wrapper decides how to surface those.
        """
        raw = await self._fetch_window(window)
        agg = self._aggregate(raw)
        narrative_text = await self._generate_narrative(agg, window)
        html, text = self._render_bodies(agg, narrative_text)
        subject = self._build_subject(agg, window)
        digest = Digest(subject=subject, text=text, html=html)
        summary = self._build_summary(agg, narrative_text, window)
        recipients = self._initial_recipients(raw)
        return DigestResult(
            digest=digest,
            narrative=narrative_text,
            summary=summary,
            recipients=recipients,
        )

    # ------------------------------------------------------------------
    # Abstract — each subclass MUST implement.
    # ------------------------------------------------------------------

    @abstractmethod
    async def _fetch_window(self, window: DigestWindow) -> Any:
        """Fetch raw rows for the given window. Return any per-product
        envelope (dict / tuple / dataclass) — the base just hands it to
        `_aggregate` unchanged.

        Typed `Any` because the four adopters return four different
        shapes (dict for weekly_review; 3-tuple for audit_digest;
        Optional[3-tuple] for campaign_debrief; 2-tuple for
        monthly_narrative). Forcing a Protocol here would either
        require data-shape forks per subclass or an `Any` escape hatch
        — neither buys typing value.
        """
        raise NotImplementedError

    @abstractmethod
    def _aggregate(self, raw: Any) -> Any:
        """Shape `raw` into the structured input the LLM and renderer
        consume. Return type is per-subclass — passed unchanged to
        `_generate_narrative` and `_render_bodies`."""
        raise NotImplementedError

    @abstractmethod
    async def _generate_narrative(
        self, agg: Any, window: DigestWindow
    ) -> str:
        """Generate the LLM narrative. Subclasses delegate to
        `noctusai_lib.domain.digest.narrative()` with per-product
        `system` + `user_prompt` strings + `cache=True/False` choice
        (LGPD posture)."""
        raise NotImplementedError

    @abstractmethod
    def _render_bodies(self, agg: Any, narrative: str) -> tuple[str, str]:
        """Render `(html, text)` digest bodies. Subclasses delegate to
        `noctusai_lib.domain.digest.render_digest_pair()` with the
        per-product Jinja context."""
        raise NotImplementedError

    @abstractmethod
    def _build_subject(self, agg: Any, window: DigestWindow) -> str:
        """Build the email subject line. Per-product convention
        (e.g. `f"[NoctusAI] Digest semanal — {org_name}"`)."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Concrete — sensible defaults; subclasses override only when needed.
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        agg: Any,
        narrative: str,
        window: DigestWindow,
    ) -> dict[str, Any]:
        """Build the `summary: dict` returned in `DigestResult`.

        Default returns `{"narrative": narrative}`. Subclasses override
        to surface per-product domain payload (savings rate, top
        actions, click rate, etc.) — the dict shape is not constrained
        by the base; the per-product wrapper extracts what its router
        needs.
        """
        return {"narrative": narrative}

    def _initial_recipients(self, raw: Any) -> list[dict[str, Any]]:
        """Return the recipient list to fan out to.

        Default returns `[]`. Override for fan-out paths
        (core/audit_digest pulls all admins from the supabase org and
        fans the digest to each). Most subclasses keep the default
        because their per-product wrapper takes a single `recipient`
        argument.
        """
        return []

    # ------------------------------------------------------------------
    # Convenience — re-export the seed-level narrative helper so
    # subclasses can call `await self._narrative(...)` without touching
    # the lib import. Pure pass-through; provided as a discoverable
    # surface, not as logic.
    # ------------------------------------------------------------------

    @staticmethod
    async def _narrative(
        *,
        system: str,
        user_prompt: str,
        model: str,
        cache: bool,
        org_id: Optional[str],
        fallback: str,
        max_tokens: int = 600,
        temperature: float = 0.0,
    ) -> str:
        """Pass-through to `noctusai_lib.domain.digest.narrative(...)`.

        Provided so a subclass can write `self._narrative(...)` instead
        of importing the module-level helper. Identical signature +
        behaviour."""
        return await _narrative_helper(
            system=system,
            user_prompt=user_prompt,
            model=model,
            cache=cache,
            org_id=org_id,
            fallback=fallback,
            max_tokens=max_tokens,
            temperature=temperature,
        )
