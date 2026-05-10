"""``noctus.seed.specify_capability`` — workflow tool for declaring a new
seed capability via guided 6-layer placement decision.

Pure-data return; no files scaffolded. The agent uses the output as a
checklist when manually adding the capability to ``noctusai_lib`` (or
``noctusai_seed`` for framework-level factories). Encodes the seed-first
methodology entry-point: before writing a new helper in a product, run
this to confirm:

1. The capability isn't already present in seed (cross-check with
   ``list_capabilities``).
2. The right layer per the 6-layer layout
   (`KB § PATTERNS/seed-lib-layout.md`).
3. Whether the canonical Protocol+Fake+Real+factory shape applies
   (per `KB § PATTERNS/seed-fake-real-adapter.md` for IO modules).

Companion to ``scan_repetition`` (which surfaces *implicit* capabilities
hiding in product duplication) — this tool surfaces *explicit* ones the
architect is about to add.
"""

from __future__ import annotations


# 6-layer layout per KB § PATTERNS/seed-lib-layout.md. Order matters
# (downward-only deps): primitives → config → testing → integrations →
# domain → api. Each layer's purpose dictates what kinds of capabilities
# fit there.
_LAYER_GUIDANCE: dict[str, dict] = {
    "primitives": {
        "purpose": "Pure data structures, value objects, formatting helpers, "
                   "small calculations. No IO. No framework dependency.",
        "examples": "make_id, format_currency, IsoDate, parse_phone_e164",
        "fits_when": "The capability is a pure function or value type with no "
                     "external dependency. Could run in any Python environment.",
    },
    "config": {
        "purpose": "Configuration loading, env-var resolution, settings "
                   "schema. Read-only consumption of environment.",
        "examples": "ProductSettings, get_supabase_credentials, default_llm_config",
        "fits_when": "The capability resolves environment / configuration. No "
                     "side-effects beyond reading.",
    },
    "testing": {
        "purpose": "Test fixtures, fakes, assertion helpers, mock builders.",
        "examples": "MockRequestBuilder, FakeChatProvider, fixture factories",
        "fits_when": "The capability is consumed by tests, not production code.",
    },
    "integrations": {
        "purpose": "Outbound IO — HTTP clients, vendor SDKs, third-party "
                   "service adapters. Each integration ships in canonical "
                   "Protocol + Fake + Real + factory shape "
                   "(KB § PATTERNS/seed-fake-real-adapter.md).",
        "examples": "google_calendar.{Protocol,FakeAdapter,RealAdapter}, "
                    "whatsapp.WAHASender, llm.chat_completion",
        "fits_when": "The capability calls an external service or system. "
                     "Network IO, vendor SDK use, file-system IO at app boundaries.",
    },
    "domain": {
        "purpose": "Business-logic primitives for cross-product domain "
                   "concepts (metas, scheduling, gamification points). Pure "
                   "computation; product backends compose them with their "
                   "specific data wiring.",
        "examples": "metas.compute_progress, scheduling.engine, "
                    "metas.next_status, sql_templates.set_search_path",
        "fits_when": "The capability is domain logic shared across ≥2 "
                     "products' bounded contexts.",
    },
    "api": {
        "purpose": "FastAPI / HTTP / auth seams that products mount as "
                   "dependencies. Built on integrations + domain.",
        "examples": "SSOSessionCache, scheduler.AsyncIOSchedulerWrapper, "
                    "middleware.create_correlation_middleware, "
                    "auth.create_sso_token_factory",
        "fits_when": "The capability is consumed by FastAPI app code (a dep, "
                     "middleware, router-creator factory).",
    },
}


def _suggest_layer(
    *, needs_io: bool, framework_hook: bool, pure_logic: bool, test_only: bool,
) -> tuple[str, str]:
    """Pick a layer based on the capability's shape. Returns (layer, reason)."""
    if test_only:
        return "testing", "test_only=True → testing"
    if needs_io:
        return "integrations", "needs_io=True → integrations (ships Protocol+Fake+Real+factory)"
    if framework_hook:
        return "api", "framework_hook=True → api (FastAPI dep / middleware / factory)"
    if pure_logic:
        return "primitives", "pure_logic=True with no IO → primitives"
    # Default fallback: domain (cross-product business logic) is the broad
    # home when the answer isn't obvious from the binary flags.
    return "domain", "Default — cross-product business logic with no IO or framework hook"


def specify_capability(
    name: str,
    description: str = "",
    *,
    needs_io: bool = False,
    framework_hook: bool = False,
    pure_logic: bool = False,
    test_only: bool = False,
) -> dict:
    """Plan a new seed capability — 6-layer placement decision + checklist.

    Args:
        name: Proposed capability name (e.g. "format_brl_currency",
            "WhatsAppSender", "create_sso_token_factory").
        description: One-sentence description of what the capability does.
        needs_io: True when the capability calls an external service /
            network / vendor SDK. Forces ``integrations`` layer + canonical
            Protocol+Fake+Real+factory shape.
        framework_hook: True when the capability is a FastAPI dep,
            middleware, or app-factory hook. Forces ``api`` layer.
        pure_logic: True when the capability is pure computation / data
            shape with no external dependency. Suggests ``primitives``.
        test_only: True when the capability is consumed only by tests.
            Forces ``testing`` layer.

    Returns:
        ``{
          "name": str,
          "suggested_layer": str,             # one of 6 layers
          "layer_reason": str,                # why this layer
          "import_path_template": str,        # e.g. "noctusai_lib.primitives.<module>.<name>"
          "checklist": [...],                 # ordered steps the agent walks
          "shape_requirements": [...],        # canonical shape (e.g. Protocol+Fake+Real+factory)
          "cross_check": str,                 # call list_capabilities first
          "next_step": str,
        }``
    """
    layer, reason = _suggest_layer(
        needs_io=needs_io,
        framework_hook=framework_hook,
        pure_logic=pure_logic,
        test_only=test_only,
    )
    layer_guidance = _LAYER_GUIDANCE[layer]

    shape_requirements: list[str] = []
    if layer == "integrations":
        shape_requirements.extend([
            "Ships Protocol (typing.Protocol with the public methods) — defines the contract.",
            "Ships FakeAdapter (in-memory implementation for tests + dev — no real IO).",
            "Ships RealAdapter (production implementation — calls the actual external service).",
            "Ships factory function (e.g. `create_<name>_adapter()`) selecting Fake or Real "
            "based on config / env. Mirror the shape used by `integrations/google_calendar` "
            "and `integrations/google_maps`.",
            "Reference doc: KB § PATTERNS/seed-fake-real-adapter.md.",
        ])
    elif layer == "api":
        shape_requirements.extend([
            "Module-level slots default None; populated by `configure_<name>_module(...)` "
            "called from `create_product_app()` lifespan hook.",
            "Dep readers grab the populated value at REQUEST time, never import time.",
            "Reference: feedback_fastapi_dep_factory in memory.",
        ])
    elif layer == "primitives":
        shape_requirements.extend([
            "No external imports beyond stdlib + pydantic / typing.",
            "No IO. No framework dependency.",
            "Doctests OK; full test coverage in tests/primitives/.",
        ])

    checklist: list[str] = [
        f"1. Run `noctus.seed.list_capabilities`; grep for '{name}' or near-name matches "
        "in the relevant layer. STOP if it already exists — extend or use the existing one.",
        f"2. Place at `seed/lib/backend/noctusai_lib/{layer}/<module>.py`. "
        f"({layer_guidance['purpose']})",
    ]
    if shape_requirements:
        checklist.append(
            f"3. Implement the canonical shape required for the {layer} layer (see "
            "`shape_requirements` field)."
        )
    checklist.extend([
        f"{len(checklist)+1}. Add tests at `seed/lib/backend/tests/{layer}/test_<module>.py`. "
        "Cover happy path + edge cases + (for integrations) Fake⇄Real parity.",
        f"{len(checklist)+1}. Wire from a consuming product: import from "
        f"`noctusai_lib.{layer}.<module>` — confirm runtime behavior matches contract.",
        f"{len(checklist)+1}. If 2+ products will consume immediately, skip the wait — extend "
        "the seed in this same project per the framework-first rule "
        "(`KB § 01-PHILOSOPHY.md § Framework first, products second`).",
    ])

    return {
        "name": name,
        "description": description,
        "suggested_layer": layer,
        "layer_reason": reason,
        "layer_purpose": layer_guidance["purpose"],
        "layer_examples": layer_guidance["examples"],
        "layer_fits_when": layer_guidance["fits_when"],
        "import_path_template": f"noctusai_lib.{layer}.<module>.{name}",
        "shape_requirements": shape_requirements,
        "checklist": checklist,
        "cross_check": (
            "Run `noctus.seed.list_capabilities` BEFORE implementing — the seed may "
            f"already ship `{name}` or a near-name match (case insensitive, "
            "underscore-vs-hyphen variants)."
        ),
        "next_step": (
            f"After writing, re-run `noctus.seed.list_capabilities` to confirm "
            f"`noctusai_lib.{layer}.<module>.{name}` surfaces in the catalog."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.specify_capability",
        description=(
            "Workflow planner for adding a new seed capability. Pure-data "
            "return; no files scaffolded. Picks the right layer of the "
            "6-layer noctusai_lib layout (primitives/config/testing/"
            "integrations/domain/api) based on flags (needs_io, "
            "framework_hook, pure_logic, test_only). Returns checklist + "
            "shape requirements (canonical Protocol+Fake+Real+factory for "
            "IO modules). Always cross-check with list_capabilities first "
            "to avoid duplicating existing helpers."
        ),
    )
    def _specify(
        name: str,
        description: str = "",
        needs_io: bool = False,
        framework_hook: bool = False,
        pure_logic: bool = False,
        test_only: bool = False,
    ) -> dict:
        return specify_capability(
            name=name,
            description=description,
            needs_io=needs_io,
            framework_hook=framework_hook,
            pure_logic=pure_logic,
            test_only=test_only,
        )
