# DI-test seam — the no-self-monkeypatch remediation convention

> Formalized 2026-05-18 as the named §3a remediation convention for the
> `test_patch_target` / self-monkeypatch compliance class
> (`projects/platform-compliance-baseline`, the bulk of the fleet's
> high/critical debt). Promotes the existing refactor playbook to a
> first-class, INDEX-discoverable pattern. Self-contained.

## The rule

`monkeypatch.setattr(<our_module>, "<our_fn>", _noop)` ∧
`patch.object(<our_module>, "<our_fn>", ...)` ∧
`patch("our.module.our_fn", ...)` **neuter the very logic the test claims
to verify** — the test then passes whether or not the guard works. The
keeper `check_no_self_monkeypatch` flags these (severity `warning` while a
product's cleanup is in flight, ratcheting to `high` at zero). This class is
the dominant high/critical contributor to the compliance baseline; draining
it shrinks the baseline.

## The fix — three legitimate seams (in priority order)

1. **Dependency Injection (default).** The production call site takes the
   dependency as a kwarg defaulting to `None`; runtime resolves the real
   client, tests inject a fake. The production path never holds the mock.
   Use unless the dependency is reached from 8+ scattered call sites.
2. **`MockRequestBuilder.inserted_payloads` read-side.** For write
   side-effects (notification / audit rows), assert against
   `mock_sb._tables["<t>"].inserted_payloads` after the call instead of
   patching the writer. Production code stays untouched.
3. **Patch the *external* boundary only.** `patch.object(<external SDK>, …)`
   for LLM / transcription / network is allowed — it is not our logic.

`patch.object` of *our own* symbol is never the answer; if you reach for it
the test is asking you to wire a seam differently.

## Class-A — Pydantic-settings via `Depends`

The `settings_override` / `monkeypatch.setattr(settings, "X", "Y")` class. A
product's module-level `settings` instance is read attribute-by-attribute at
request time. Patching a field **supplies a real config value** — not
neutering logic — but the keeper can't tell a settings-field patch from a
guard patch, so it flags every site. The honest fix routes settings through
DI so tests never touch the global.

**Seed primitive (N≥3 — erp / core / daily-life / social-wiring all carry the
`monkeypatch.setattr(settings, …)` shape):** `noctusai_seed.make_get_settings(
settings_instance)` — sibling of `make_get_current_user_org`. Returns a
zero-arg FastAPI dependency yielding the bound instance; routers
`Depends(get_settings)`, tests override via
`app.dependency_overrides[get_settings] = lambda: ProductSettings(field="x")`
(+ teardown `.clear()`) — no monkeypatch of our symbol. Factory + end-to-end
override test: `seed/framework/backend/noctusai_seed/config.py` /
`seed/framework/backend/tests/test_config.py` (shipped 2026-05-25).

**Adoption status:** social-wiring currently wires a **product-local**
`get_settings` (`app/dependencies.py`) + a `build_credential_store(client, *,
encryption_key=…)` kwarg seam — the Class-A landing that drained its baseline.
Migrating those product-local seams to consume `noctusai_seed.make_get_settings`
is the open consume-step (follow-up `seed-config-di-consume`).

## Authoritative depth

Full playbook (worked before/after, the DI kwarg recipe, the
`inserted_payloads` recipe, the decision table, reference adopters such as
`_resolve_core_db` in
`products/therapy-platform/backend/app/services/ai_pipeline.py`) lives in
`§ CONTEXT/PATTERNS/testing.md § No self-monkeypatching — refactor
playbook`. Keeper + colocated regression test:
`check_no_self_monkeypatch` / `TestCheckNoSelfMonkeypatch` in
`mcp/noctusai/tests/test_compliance.py`. Gate context:
`§ CONTEXT/PATTERNS/compliance-regression-baseline.md`.
