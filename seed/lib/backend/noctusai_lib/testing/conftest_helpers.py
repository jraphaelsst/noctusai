"""Conftest helpers for parallel-worktree-safe testing.

When the host venv carries an editable-install of ``noctusai_lib`` (or
``noctusai_seed``) pointing at a sibling worktree, that finder shadows the
local ``sys.path`` entry and tests run against the wrong source tree. This
module ships the canonical shadow-purge helper used by seed-lib + every
product conftest.

Lift history (`projects/seed-shadow-purge-helper-lift/PROJECT.md`):
    * 4 verbatim-ish copies pre-existed (seed/lib + 3 products);
    * 3 carried a bug (inspect class-level ``MAPPING``); 1 (PF) carried the
      correct module-level fallback;
    * unified canonical lives here, supports both shapes defensively.

Generalization (2026-05-11, Engineer SP):
    * Engineer W (XML-FEEDS-VERIFY) surfaced the same shape for the
      ``noctusai_seed`` package — sibling-worktree editable installs can
      shadow ``noctusai_seed`` exactly as they shadow ``noctusai_lib``.
    * The package set is now a parameter (``package_names``) with the
      default ``("noctusai_lib", "noctusai_seed")`` so existing callers
      get both protections without touching their conftests.

Per-package-root fix (2026-05-16, Engineer DEP-A):
    * The ``seed/{lib,framework}`` axis-swap (commits ~fc277e2/fd2376d)
      moved ``noctusai_seed`` to ``seed/framework/backend`` while
      ``noctusai_lib`` stayed at ``seed/lib/backend``. The pre-fix helper
      validated BOTH packages against the SINGLE ``local_lib_root``
      (always ``seed/lib/backend``, passed by every product conftest), so
      the *legitimate* ``noctusai_seed`` finder — correctly mapping to
      ``<repo>/seed/framework/backend/noctusai_seed`` — failed the
      ``startswith(seed/lib/backend)`` check, got dropped, and was purged
      from ``sys.modules`` with no fallback. Result: ``import
      noctusai_seed`` failed for the whole pytest session across every
      product (12× ``test_per_product_cors_sentinel`` + product
      collection errors). Tool moved package roots; this guard was not
      updated in the same change (a tool-code/doc-code coherence gap).
    * Fix: each guarded package is now validated against ITS OWN
      legitimate in-repo editable root, derived from the repo worktree
      that ``local_lib_root`` belongs to (``noctusai_lib`` →
      ``<repo>/seed/lib/backend``, ``noctusai_seed`` →
      ``<repo>/seed/framework/backend``), via ``_DEFAULT_PACKAGE_ROOTS``.
      The genuine shadow-sibling protection is unchanged: a finder is
      still dropped iff its mapping resolves OUTSIDE the package's own
      legitimate root (i.e. it belongs to a *different* worktree). The
      signature is backward compatible — existing callers keep passing
      ``local_lib_root`` positionally; the per-package roots are an
      optional ``package_roots`` arg with a correct default.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Iterable

__all__ = [
    "own_test_env",
    "purge_shadowing_editable_finders",
    "restore_real_llm_providers",
]

_DEFAULT_PACKAGE_NAMES: tuple[str, ...] = ("noctusai_lib", "noctusai_seed")

# Each guarded package's legitimate in-repo editable root, expressed as a
# path RELATIVE to the repo worktree root. ``local_lib_root`` is always
# ``<repo>/seed/lib/backend`` (every product conftest passes it), so the
# repo root is ``local_lib_root.parents[2]``. Post the ``seed/{lib,
# framework}`` axis-swap these two packages live in different subtrees:
#   * ``noctusai_lib``  → ``<repo>/seed/lib/backend``
#   * ``noctusai_seed`` → ``<repo>/seed/framework/backend``
_DEFAULT_PACKAGE_ROOTS: dict[str, tuple[str, ...]] = {
    "noctusai_lib": ("seed", "lib", "backend"),
    "noctusai_seed": ("seed", "framework", "backend"),
}


def purge_shadowing_editable_finders(
    local_lib_root: Path,
    package_names: Iterable[str] = _DEFAULT_PACKAGE_NAMES,
    package_roots: Mapping[str, tuple[str, ...]] | None = None,
) -> None:
    """Drop meta-path finders whose mapping for a guarded package points outside *that package's own* legitimate in-repo root.

    Handles BOTH shapes pip PEP-660 / hand-rolled finders use:

    * **class-level** ``MAPPING`` attribute (legacy / hypothetical);
    * **module-level** ``MAPPING`` dict on the finder's defining module —
      the actual real-world case for pip's
      ``__editable___<pkg>_<version>_finder.py`` shape, where
      ``sys.meta_path.append(_EditableFinder)`` registers the *class* but
      ``MAPPING`` lives on the module.

    Args:
        local_lib_root: the worktree's ``seed/lib/backend`` Path. Its
            third parent (``parents[2]``) is the repo worktree root, from
            which each guarded package's *own* legitimate editable root is
            derived (see ``package_roots``). A finder is dropped iff its
            mapping for a guarded package resolves *outside that package's
            own* legitimate root — i.e. it belongs to a *different*
            worktree. (Pre-2026-05-16 this validated every package against
            ``local_lib_root`` itself, which wrongly dropped the
            legitimate ``noctusai_seed`` finder once the axis-swap moved
            ``noctusai_seed`` to ``seed/framework/backend``.)
        package_names: iterable of package names to guard. Defaults to
            ``("noctusai_lib", "noctusai_seed")`` — both seed-side
            packages can be shadowed by sibling-worktree editable
            installs and need the same defense. Pass a narrower or wider
            tuple if a consumer needs custom coverage.
        package_roots: optional map ``package_name -> relative path tuple``
            giving each package's legitimate editable root *relative to
            the repo worktree root* (``local_lib_root.parents[2]``).
            Defaults to ``_DEFAULT_PACKAGE_ROOTS``
            (``noctusai_lib`` → ``seed/lib/backend``; ``noctusai_seed`` →
            ``seed/framework/backend``). A guarded package with no entry
            here (and not the special ``noctusai_lib`` fallback) is
            validated against ``local_lib_root`` directly — preserving
            the pre-fix behaviour for any custom package a consumer
            guards. Pass an explicit map for non-default layouts.

    Side-effects (by design — meant for conftest top-level use):

    * mutates ``sys.meta_path`` (drops shadowing finders);
    * drops cached entries for every guarded package from ``sys.modules``
      so they re-resolve through the local source tree on next import.

    Idempotent: calling twice in one process is safe (second call is a
    no-op when shadowing was already cleared).

    A finder whose ``__module__`` resolves to a module without ``MAPPING``
    is preserved (same effect as ``getattr`` returning ``None``) — the
    contract is "drop shadowing finders", not "drop unrecognized finders".

    Drop semantics with multiple packages: each guarded package is checked
    against ITS OWN legitimate root (per ``package_roots``), not one shared
    root. If a finder's mapping mentions ANY guarded package and that
    package's entry resolves outside *that package's own* legitimate root,
    the finder is dropped. This is the safe choice — a single editable
    finder typically maps one package, so the multi-package check is
    effectively an OR across independent finders. Critically, a finder
    whose mapping resolves to a real in-repo package root is NEVER dropped
    merely because that root differs from ``local_lib_root`` (the
    axis-swap bug).
    """
    local_lib_resolved = local_lib_root.resolve()
    local_target = str(local_lib_resolved)
    # Repo worktree root: ``local_lib_root`` is ``<repo>/seed/lib/backend``,
    # so the repo root is its third parent. Guard against unexpectedly
    # shallow paths (custom callers) by falling back to ``local_lib_root``.
    try:
        repo_root = local_lib_resolved.parents[2]
    except IndexError:  # pragma: no cover - defensive; real callers pass seed/lib/backend
        repo_root = local_lib_resolved
    roots_map = _DEFAULT_PACKAGE_ROOTS if package_roots is None else dict(package_roots)

    def _legitimate_root(pkg: str) -> str:
        """Resolve ``pkg``'s own legitimate in-repo editable root.

        Falls back to ``local_lib_root`` for any guarded package without a
        ``package_roots`` entry — this preserves the pre-fix behaviour for
        bespoke packages a consumer might guard, while the two default
        seed packages get their correct per-package roots.
        """
        rel = roots_map.get(pkg)
        if rel is None:
            return local_target
        return str((repo_root.joinpath(*rel)).resolve())

    package_tuple = tuple(package_names)
    keep: list = []
    for finder in sys.meta_path:
        # Class-level MAPPING (legacy / hypothetical):
        mapping = getattr(finder, "MAPPING", None)
        if mapping is None:
            # Module-level MAPPING (pip's __editable___pkg_finder.py shape):
            mod_name = getattr(finder, "__module__", None)
            mod = sys.modules.get(mod_name) if mod_name else None
            mapping = getattr(mod, "MAPPING", None)
        drop = False
        if isinstance(mapping, dict):
            for pkg in package_tuple:
                if pkg in mapping:
                    target = str(Path(mapping[pkg]).resolve())
                    pkg_root = _legitimate_root(pkg)
                    if not target.startswith(pkg_root):
                        # Editable finder bound to a DIFFERENT worktree
                        # (its mapping resolves outside this package's own
                        # legitimate in-repo root) — drop it. A finder
                        # pointing at this worktree's correct root for the
                        # package (even if that root is not
                        # ``local_lib_root``) is preserved.
                        drop = True
                        break
        if drop:
            continue
        keep.append(finder)
    sys.meta_path[:] = keep
    # Also drop any already-imported entries for guarded packages so they
    # re-resolve through our local source tree on next import.
    for name in list(sys.modules):
        for pkg in package_tuple:
            if name == pkg or name.startswith(f"{pkg}."):
                del sys.modules[name]
                break


def own_test_env(
    values: "dict[str, str]",
    clear: "tuple[str, ...] | list[str]" = (),
    environ: "dict[str, str] | None" = None,
) -> "dict[str, str]":
    """Force the suite's environment to exactly what the suite declares.

    **Use this instead of ``os.environ.setdefault`` in a conftest.** Every
    product conftest reached for ``setdefault`` — it reads as a safe "provide a
    default" — but its actual meaning is *"whatever the developer happens to
    have exported wins"*, and that is never what a test wants.

    THE INCIDENT (p-studio, 2026-08-19)
    -----------------------------------
    ``os.environ.setdefault("ASAAS_WEBHOOK_TOKEN", "token-de-webhook-de-teste")``.
    The repo's own ``.env`` carries ``ASAAS_WEBHOOK_TOKEN=`` — present, empty.
    Any process that loads it (the MCP server, hence ``predeploy_check``)
    exports the key, ``setdefault`` sees it as already-set and does nothing, and
    the suite runs with an EMPTY expected token: 15 of 20 webhook tests fail on
    a 503 that has nothing to do with what they assert. Run from a plain shell
    they all pass. The suite was reporting on the developer's shell, not on the
    code.

    THE SHARPER EDGE
    ----------------
    Flakiness was the least of it. The same file did
    ``setdefault("SUPABASE_SERVICE_ROLE_KEY", "")`` and
    ``setdefault("PROVEDOR_COBRANCA", "fake")``. Export the real values — which
    the platform ``.env`` holds — and the suite builds a **real service-role
    Supabase client** and a **real payment-provider adapter**. A test run in the
    wrong shell could reach production. "Defaults" that yield to ambient
    credentials are not a convenience; they are an open door.

    So this helper ASSIGNS, and additionally ``clear``s the keys whose mere
    presence changes behaviour (``ENCRYPTION_KEY``: set ⇒ the credential path
    runs; unset ⇒ it does not).

    Args:
        values: keys assigned unconditionally — the suite's declared world.
        clear: keys REMOVED if present. For vars where "set at all" is the
            switch, an empty string is not the same as absent.
        environ: the mapping to mutate (defaults to ``os.environ``). Injected
            so this is testable without mutating the real process env.

    Returns:
        The ``{key: previous_value}`` map of everything changed — enough to
        restore, and enough for a test to assert on.
    """
    import os

    env = os.environ if environ is None else environ
    before: "dict[str, str]" = {}

    for key in clear:
        if key in env:
            before[key] = env[key]
            del env[key]
    for key, value in values.items():
        if env.get(key) != value:
            before.setdefault(key, env.get(key, ""))
        env[key] = value
    return before


#: The provider modules whose import side-effect IS the real registration.
_REAL_LLM_PROVIDER_MODULES = (
    "noctusai_lib.integrations.llm.providers.openai_provider",
    "noctusai_lib.integrations.llm.providers.anthropic_provider",
    "noctusai_lib.integrations.llm.providers.gemini_provider",
)


def restore_real_llm_providers() -> None:
    """Re-register the REAL LLM providers, discarding every test double.

    **Call this in teardown of any test that registers a provider.** The
    registry (``noctusai_lib.integrations.llm.registry._PROVIDERS``) is a
    module-global dict and ``register()`` overwrites silently, by design, so a
    fake installed for one test stays installed for the whole process. pytest
    cannot undo it: nothing was patched, a plain dict was mutated.

    THE INCIDENT (2026-08-20)
    ------------------------
    Two fixtures in ``test_llm_providers.py`` registered ``"nobatch"`` and
    ``"countingbatch"`` and cleared only the provider CACHE on teardown, never
    the registry. ``test_llm_endpoints.py`` asserts every registered provider
    has catalog entries — true of the three real ones, false of a fake — so it
    failed with *"Provider 'nobatch' is registered but has zero catalog
    entries"* whenever ``pytest-randomly`` happened to order it after them. On
    other seeds it passed. That is not flakiness; it is an ordering bug wearing
    flakiness as a costume, and it reddened CI at random.

    The worse shape is a fake registered under a REAL name (``register("openai",
    _FakeClass)``): nothing looks wrong afterwards, and every later test that
    thinks it is exercising the OpenAI provider is exercising a stub.

    Restoring by RE-IMPORT rather than by saving/restoring the dict is
    deliberate — the registration lives in each provider module's import
    side-effect, so re-running that is what makes the registry authoritative
    again rather than merely non-empty.
    """
    import importlib

    from noctusai_lib.integrations.llm.registry import _reset_for_testing

    _reset_for_testing()
    for module_name in _REAL_LLM_PROVIDER_MODULES:
        module = importlib.import_module(module_name)
        importlib.reload(module)
