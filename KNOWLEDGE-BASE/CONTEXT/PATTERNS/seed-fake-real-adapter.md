# Seed Fake+Real Adapter — the canonical shape for IO-touching seed modules

> Established by `integrations/google_calendar/` and `integrations/google_maps/` (2026-05-03 absorption from the sibling `whatsapp-google-scheduling` repo). Surfaced as a named pattern 2026-05-03 during `media-scheduling-port` Phase 0.5 after the Phase 0 audit found three other seed modules (`whatsapp`, `redis`, `chatbot.buffer`) lacked the shape and the user named the gap.
>
> **One-line statement.** Every seed module that touches IO ships in **Protocol + Fake + Real + factory** shape. Pure-logic / pure-crypto / pure-shaping modules are exempt. Half-shipped (Protocol+Real only or Protocol+Fake only) generates consumer-side forks at the seed level.

---

## What this pattern is

The shape:

```
integrations/<name>/   (or domain/<name>/ for IO-touching domain modules)
├── __init__.py          # Public surface + get_<name>_adapter(...) factory
├── types.py             # Value objects + <Name>Client / <Name>Adapter Protocol(s)
├── mappers.py           # Pure-function shape converters (when applicable)
├── fake_adapter.py      # Deterministic in-memory implementation
├── <vendor>_adapter.py  # Real-runtime adapter (one per backend)
├── credentials.py       # (when applicable) per-tenant credential resolver Protocol + dataclasses
└── settings.py          # (when applicable) Pydantic settings
```

The factory:

```python
def get_<name>_adapter(<minimal_signal_kwargs>) -> <Protocol>:
    """Return a real adapter when a credentials/url/key signal is present;
    Fake otherwise. Mirrors get_calendar_adapter() and get_routing_adapter()."""
    if not <signal>:
        return Fake<Name>Adapter()
    return Real<Name>Adapter(<signal>)
```

The Protocol — defined in `types.py`, exported from `__init__.py`:

```python
@runtime_checkable
class <Name>Client(Protocol):
    """Surface every <name> connector implements. Both Fake and Real
    satisfy this Protocol naturally."""

    def operation(self, ...) -> ...: ...
```

---

## Why this shape

Three problems the pattern solves at once:

1. **Verify-the-seed-ships-it without forking.** A module that ships only Protocol + Real forces consumers to BYO Fake (every test re-implements the in-memory stub). A module that ships only Protocol + Fake forces consumers to BYO Real (every product re-implements the vendor adapter). The Protocol+Fake+Real+factory ships ALL THREE — the consumer chooses based on environment, no fork required.

2. **Test ergonomics by import-shortcut.** Consumers do `from noctusai_lib.integrations.<name> import Fake<Name>Adapter` and instantiate. No conftest hunt, no third-party-library-name memorization.

3. **Pattern discoverability.** Once the shape is set, future seed modules trivially follow. The directory listing alone tells the next agent what to author. New IO-touching seed modules don't need to re-decide on file layout — the pattern says where everything goes.

---

## Reference modules (read these to see the pattern)

- **`seed/lib/backend/noctusai_lib/integrations/google_calendar/`** — gold-standard reference. Has `CalendarAdapter` Protocol, `FakeCalendarAdapter`, two real adapters (`ServiceAccount` + `OAuth`), `CalendarCredentialResolver` Protocol + dataclasses, `get_calendar_adapter()` factory.
- **`seed/lib/backend/noctusai_lib/integrations/google_maps/`** — same shape, simpler (one real adapter). `RoutingAdapter` Protocol, `StaticRoutingAdapter` (Fake), `GoogleMapsRoutingAdapter` (Real), `get_routing_adapter()` factory.
- **`seed/lib/backend/noctusai_lib/integrations/whatsapp/`** — backfilled 2026-05-03 to match: `WhatsAppClient` Protocol in `types.py`, `WahaClient` Real, `FakeWahaClient` Fake (bi-directional — `sent_messages` + `inject_inbound`), `get_whatsapp_client()` factory.

---

## Modules exempt from the shape (and why)

Some seed modules don't touch IO and therefore don't need a Fake — their "Fake" would exercise the same code as the Real:

- **`domain.scheduling`** — pure logic. `ZeroTravelLookup` is the implicit Fake (the default `TravelLookup` Protocol implementation). The Conflict and Scorer Protocols already have `Default*` implementations. The module is stateless math.
- **`security.webhook_signatures`** — pure crypto. `verify_hmac_sha256(body, signature, secret)` doesn't touch IO. The factory `webhook_endpoint(...)` is a FastAPI dep factory, not an adapter.
- **`domain.ai.tool_audit`** — `make_audit_writer(db, table_class)` IS the abstraction. The "Fake" is just calling it with a SQLite session; the closure is the adapter. There's no separate "Fake" version that would exercise different code.

**The exemption test:** *"Would a Fake here exercise different code than the Real?"* If no, exempt. If yes, ship Fake+Real per the canonical shape.

---

## Modules that backfilled to the shape (audit trail)

| Date | Module | Backfill | Driving project |
|---|---|---|---|
| 2026-05-03 | `integrations.whatsapp` | Added `WhatsAppClient` Protocol in `types.py` + `FakeWahaClient` (bi-directional) + `get_whatsapp_client()` factory | `media-scheduling-port` Phase 0.5 (G1) |
| 2026-05-03 | `integrations.redis` | Added `make_fake_redis_client()` (wraps `fakeredis.FakeStrictRedis`); added `fakeredis>=2.20.0` to `pyproject.toml` deps | `media-scheduling-port` Phase 0.5 (G2) |
| 2026-05-03 | `domain.chatbot.buffer` | Added `make_in_memory_buffer_client()` (re-exports the redis fake for import-shortcut UX); `RedisBufferClient` Protocol was already in place | `media-scheduling-port` Phase 0.5 (G3) |
| 2026-05-03 | (DRY cleanup) | Hard-deleted `domain.conversation` — stale fork of `domain.chatbot` (only test files referenced; recurrence rule N=2 fired structurally inside seed) | `media-scheduling-port` Phase 0.5 (G4) |

---

## Companion sub-rule on `feedback_verify_seed_ships_it.md`

The "verify the seed ships it" rule used to ask: *does the runtime adapter exist?* It now asks two questions:

1. Does the runtime adapter exist?
2. Does it exist in the canonical Protocol + Fake + Real + factory shape?

Both must be YES. A Protocol+Real (no Fake) is half-shipped — consumers can't write tests against it without third-party libraries. A Protocol+Fake (no Real) is half-shipped — consumers fork the vendor adapter into product code. Both half-shipped shapes generate consumer-side forks; the canonical shape prevents forks at the seed level.

---

## Authoring checklist for a NEW seed IO module

Before you commit a new IO-touching seed module, walk this:

- [ ] `types.py` — value objects + `<Name>Client` (or `<Name>Adapter`) Protocol decorated `@runtime_checkable`
- [ ] `<vendor>_adapter.py` — real-runtime adapter; lazy-imports vendor SDK; satisfies the Protocol
- [ ] `fake_adapter.py` — deterministic in-memory; satisfies the Protocol; bi-directional if read+write surface (records writes, accepts injected reads)
- [ ] `__init__.py` — exports Protocol + Fake + Real + factory in `__all__`; docstring includes provenance (lifted-from + lifted-by + lifted-when when absorbed from external code)
- [ ] `get_<name>_adapter(...)` factory — minimal signal kwargs (api_key, base_url, credentials); returns Real when signal present, Fake otherwise
- [ ] Tests at `seed/lib/backend/tests/integrations/<name>/test_fake_adapter.py` — cover send/receive paths + Protocol conformance (`isinstance(client, <Name>Client)`)
- [ ] Vendor SDK dep added to `seed/lib/backend/pyproject.toml` (lazy-loaded inside the real adapter)

---

## Authoring checklist for a NEW seed DOMAIN module that touches IO

Same as above, with `integrations/<name>/` → `domain/<name>/`. Domain modules sometimes don't ship a `<vendor>_adapter.py` because they consume IO via an integration module — in that case the domain module ships:

- Protocol for the IO seam (e.g. `RedisBufferClient` in `chatbot.buffer`)
- Re-export factory for the Fake (e.g. `make_in_memory_buffer_client()` re-exports the redis fake)

This avoids forcing the domain module to know about `fakeredis` directly.

---

## Anti-patterns

### "We ship a Protocol; consumers can BYO Fake"

The Protocol-only seed module is half-shipped. Consumers don't write the same Fake — every test rolls a slightly different one, with subtle behavioral drift. The first time two products' tests have to share assertions on the same Fake's behavior, the drift surfaces as inconsistent failures. Cost of fixing it later = pull every consumer's BYO Fake into seed + reconcile differences. Cost of getting it right first = author one Fake at the same time as the Real.

### "Tests use `unittest.mock.MagicMock` instead of a Fake"

Mocking the seed module's surface is the consumer-side fork in disguise. Each test file has a 5-line `MagicMock` setup recreating partial behavior; bugs slip through because `MagicMock` returns truthy for any unconfigured method. Ship the Fake; tests use it; confidence in seed conformance compounds.

### "We pass a real adapter into tests because the Fake doesn't support our edge case"

Fake gap → extend the Fake, don't shortcut to the Real. The Fake's job is to mirror the Real's observable behavior; if it doesn't, that's a Fake bug worth fixing once. Reaching for the Real in tests breaks deterministic CI.

### "The factory takes 10 kwargs and inspects them all"

The factory's job is one decision: real or fake. Push other configuration into the adapter constructors. Factory: `if not api_key: return Fake; return Real(api_key, **kwargs)`. Adapter: takes whatever rich config it needs. Don't conflate "build the adapter" with "decide which kind".

### "The Real uses a primitive the Fake doesn't run"

**The test fake is part of the seed contract.** If the production primitive doesn't run on the test fake, the seed module is half-shipped — consumers' tests will silently fail to exercise the Real's actual code path.

Concrete: Engineer I's first draft of `RedisQuotaTracker` used a server-side Lua `EVAL` script for atomic check-and-consume — the textbook Redis pattern. Tests blew up on `fakeredis` 2.x because `fakeredis` ships Lua support behind an optional `lupa` runtime dep that's not installed. Pivot: WATCH/MULTI/EXEC + retry-on-WatchError (optimistic concurrency, native to both `redis-py` and `fakeredis`). Same atomicity guarantees, identical test coverage, no extra dep.

The rule: when picking a primitive for a seed module, **first check the Fake supports it**. If the Fake can't run the primitive, either (a) extend the Fake (add the primitive to its supported surface), (b) pick a different primitive that runs on both, or (c) accept that you've half-shipped and document why. Never pick a primitive that "happens to work in production but not in tests" — that's the half-shipped trap dressed up.

Surfaced 2026-05-04 by `seed-hardening-from-youtube-crawler` Phase 3.3 (Engineer I).

---

## Cross-references

- `KB § 03-SEED-ARCHITECTURE.md § Verify-the-seed-ships-it test` — the rule that drives this pattern
- `KB § PATTERNS/seed-lib-layout.md` — the 6-layer module taxonomy this pattern lives within
- `KB § PATTERNS/scheduling-seed.md` — example of an IO-EXEMPT seed module (`domain.scheduling`)
- `KB § PATTERNS/whatsapp-chatbot-seed.md` — wiring recipe for the chatbot/whatsapp combo
- `feedback_verify_seed_ships_it.md` (memory) — the agent-side rule (sub-rule about SHAPE added 2026-05-03)
- `feedback_seed_fake_real_pattern.md` (memory) — this pattern's agent-side rule
- `feedback_recurrence_rule.md` (memory) — sub-rule about seed-internal recurrence (added 2026-05-03)
