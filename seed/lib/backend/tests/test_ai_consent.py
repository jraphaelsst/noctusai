"""Unit tests for `noctusai_lib.ai.consent` (Phase 19 X6)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from noctusai_lib.domain.ai import consent as consent_module
from noctusai_lib.domain.ai.consent import (
    AIConsentRequired,
    MandatoryFeatureCannotBeToggled,
    fetch_user_decisions,
    get_catalog,
    get_feature,
    is_granted,
    list_user_consent_view,
    pending_count,
    register_feature,
    require,
    reset_catalog_for_test,
    upsert_decision,
)


@pytest.fixture(autouse=True)
def _isolate_catalog():
    """Reset the module-level catalog so tests don't bleed into each other."""
    reset_catalog_for_test()
    yield
    reset_catalog_for_test()


def _build_db(*, decisions_data=None, upsert_data=None):
    """Mock supabase-shaped client with a chainable .table() builder."""
    sb = MagicMock()
    chain = MagicMock()
    sb.table = MagicMock(return_value=chain)
    chain.select = MagicMock(return_value=chain)
    chain.eq = MagicMock(return_value=chain)
    chain.upsert = MagicMock(return_value=chain)
    if upsert_data is not None:
        chain.execute = MagicMock(return_value=MagicMock(data=upsert_data))
    else:
        chain.execute = MagicMock(return_value=MagicMock(data=decisions_data or []))
    return sb, chain


class TestRegisterCatalog:
    def test_register_and_lookup(self):
        register_feature(
            "erp.lead_score", title="Pontuação", rationale="X.", product="erp"
        )
        assert get_feature("erp.lead_score").title == "Pontuação"
        assert len(get_catalog()) == 1

    def test_re_register_overrides(self):
        register_feature("k", title="A", rationale="A")
        register_feature("k", title="B", rationale="B")
        assert get_feature("k").title == "B"

    def test_get_catalog_sorted_by_product_then_key(self):
        register_feature("z.feature", title="z", rationale="z", product="z")
        register_feature("a.feature", title="a", rationale="a", product="a")
        register_feature("a.feature2", title="a2", rationale="a", product="a")
        keys = [f.key for f in get_catalog()]
        assert keys == ["a.feature", "a.feature2", "z.feature"]

    def test_empty_key_rejected(self):
        with pytest.raises(ValueError):
            register_feature("", title="x", rationale="x")


class TestIsGranted:
    @pytest.mark.asyncio
    async def test_stored_grant_true(self):
        register_feature("k", title="K", rationale="K")
        sb, _ = _build_db(decisions_data=[{"feature_key": "k", "granted": True}])
        assert await is_granted(sb, "user-1", "k") is True

    @pytest.mark.asyncio
    async def test_stored_revoke_overrides_default_grant(self):
        register_feature("k", title="K", rationale="K", default_granted=True)
        sb, _ = _build_db(decisions_data=[{"feature_key": "k", "granted": False}])
        assert await is_granted(sb, "user-1", "k") is False

    @pytest.mark.asyncio
    async def test_no_decision_falls_back_to_default(self):
        register_feature("k", title="K", rationale="K", default_granted=True)
        sb, _ = _build_db(decisions_data=[])
        assert await is_granted(sb, "user-1", "k") is True

    @pytest.mark.asyncio
    async def test_unknown_feature_fails_closed(self):
        sb, _ = _build_db(decisions_data=[])
        assert await is_granted(sb, "user-1", "unknown.feature") is False

    @pytest.mark.asyncio
    async def test_no_db_or_user_returns_false(self):
        assert await is_granted(None, "user-1", "k") is False
        sb, _ = _build_db()
        assert await is_granted(sb, "", "k") is False


class TestRequire:
    @pytest.mark.asyncio
    async def test_passes_when_granted(self):
        register_feature("k", title="K", rationale="K")
        sb, _ = _build_db(decisions_data=[{"feature_key": "k", "granted": True}])
        await require(sb, "user-1", "k")  # does not raise

    @pytest.mark.asyncio
    async def test_raises_with_title_when_not_granted(self):
        register_feature("erp.lead_score", title="Pontuação", rationale="X.")
        sb, _ = _build_db(decisions_data=[])
        with pytest.raises(AIConsentRequired) as exc_info:
            await require(sb, "user-1", "erp.lead_score")
        assert exc_info.value.status_code == 412
        assert exc_info.value.details["feature_key"] == "erp.lead_score"
        assert exc_info.value.details["title"] == "Pontuação"

    @pytest.mark.asyncio
    async def test_unknown_feature_raises_without_title(self):
        sb, _ = _build_db(decisions_data=[])
        with pytest.raises(AIConsentRequired) as exc_info:
            await require(sb, "user-1", "unknown.k")
        assert exc_info.value.details["title"] is None


class TestUpsertDecision:
    @pytest.mark.asyncio
    async def test_grant_sets_granted_at_and_snapshots_rationale(self):
        register_feature(
            "k", title="K", rationale="Avaliar perfis automaticamente.", product="erp"
        )
        sb, chain = _build_db(upsert_data=[{
            "id": "row-1", "feature_key": "k", "granted": True,
            "rationale_pt": "Avaliar perfis automaticamente.",
        }])
        await upsert_decision(sb, "user-1", "k", granted=True, org_id="org-1")
        # Inspect what was upserted.
        call_args = chain.upsert.call_args
        payload = call_args[0][0]
        assert payload["granted"] is True
        assert payload["rationale_pt"] == "Avaliar perfis automaticamente."
        assert payload["org_id"] == "org-1"
        assert payload["granted_at"] is not None
        assert call_args[1]["on_conflict"] == "user_id,feature_key"

    @pytest.mark.asyncio
    async def test_revoke_sets_revoked_at(self):
        register_feature("k", title="K", rationale="X.")
        sb, chain = _build_db(upsert_data=[{}])
        await upsert_decision(sb, "user-1", "k", granted=False)
        payload = chain.upsert.call_args[0][0]
        assert payload["granted"] is False
        assert payload["revoked_at"] is not None
        assert "granted_at" not in payload


class TestListUserConsentView:
    @pytest.mark.asyncio
    async def test_merges_catalog_with_decisions(self):
        register_feature(
            "a", title="A", rationale="ra", product="erp", default_granted=False
        )
        register_feature(
            "b", title="B", rationale="rb", product="pf", default_granted=True
        )
        sb, _ = _build_db(decisions_data=[{
            "feature_key": "a", "granted": True,
            "granted_at": "2026-01-01T00:00:00Z", "revoked_at": None,
        }])
        view = await list_user_consent_view(sb, "user-1")
        assert len(view) == 2

        a_row = next(r for r in view if r["key"] == "a")
        assert a_row["granted"] is True
        assert a_row["decision_recorded"] is True

        b_row = next(r for r in view if r["key"] == "b")
        assert b_row["granted"] is True  # default_granted
        assert b_row["decision_recorded"] is False


class TestPendingCount:
    def test_counts_undecided_features(self):
        view = [
            {"decision_recorded": True},
            {"decision_recorded": False},
            {"decision_recorded": False},
            {"decision_recorded": True},
        ]
        assert pending_count(view) == 2


# ---------------------------------------------------------------------------
# consent_required FastAPI dep factory (consent-guard-rollout Phase 1)
# ---------------------------------------------------------------------------

from noctusai_lib.domain.ai.consent import (
    configure_consent_module,
    consent_required,
    is_consent_module_configured,
    reset_consent_module_for_test,
)


@pytest.fixture
def _isolate_consent_module():
    """Reset the wired factories so each test starts from a clean slate."""
    reset_consent_module_for_test()
    yield
    reset_consent_module_for_test()


class TestConfigureConsentModule:
    def test_unconfigured_by_default(self, _isolate_consent_module):
        assert is_consent_module_configured() is False

    def test_configure_wires_both_factories(self, _isolate_consent_module):
        configure_consent_module(
            get_current_user=lambda: ("user", "token"),
            admin_client_factory=lambda: MagicMock(),
        )
        assert is_consent_module_configured() is True

    def test_configure_with_None_disables(self, _isolate_consent_module):
        configure_consent_module(
            get_current_user=lambda: ("u", "t"),
            admin_client_factory=lambda: MagicMock(),
        )
        assert is_consent_module_configured() is True

        configure_consent_module(get_current_user=None, admin_client_factory=None)
        assert is_consent_module_configured() is False

    def test_reset_for_test_clears(self, _isolate_consent_module):
        configure_consent_module(
            get_current_user=lambda: ("u", "t"),
            admin_client_factory=lambda: MagicMock(),
        )
        reset_consent_module_for_test()
        assert is_consent_module_configured() is False


class TestConsentRequired:
    def test_factory_does_NOT_raise_when_unconfigured(self, _isolate_consent_module):
        # Boot-order: routers are imported BEFORE create_product_app runs.
        # The factory must be lenient at decorator-evaluation time and defer
        # the configuration check to request time.
        dep = consent_required("erp.lead_score")
        assert callable(dep)

    def test_returns_callable_with_introspectable_name(self, _isolate_consent_module):
        dep = consent_required("erp.lead_score")
        # Name surfaces in FastAPI debug output — should encode the feature key.
        assert dep.__name__ == "consent_required__erp_lead_score"

    def test_dep_name_handles_dashes_in_product_slug(self, _isolate_consent_module):
        dep = consent_required("daily-life.weekly_review")
        assert dep.__name__ == "consent_required__daily_life_weekly_review"

    @pytest.mark.asyncio
    async def test_dep_raises_runtime_error_when_unconfigured_at_request_time(
        self, _isolate_consent_module
    ):
        # Configuration check runs at request time — the dep raises clearly
        # if the module was never configured.
        dep = consent_required("erp.lead_score")
        with pytest.raises(RuntimeError, match="configure_consent_module"):
            await dep(authorization="Bearer tok")

    @pytest.mark.asyncio
    async def test_dep_passes_when_user_has_granted_consent(self, _isolate_consent_module):
        # Storage shape: one stored row with granted=True
        register_feature("erp.lead_score", title="Lead Score", rationale="X.")
        sb, _ = _build_db(decisions_data=[{
            "feature_key": "erp.lead_score", "granted": True,
            "granted_at": "2026-01-01T00:00:00Z", "revoked_at": None,
        }])

        configure_consent_module(
            get_current_user=lambda authorization=None: (MagicMock(id="user-42"), "tok"),
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("erp.lead_score")

        result = await dep(authorization="Bearer tok")
        assert result is None  # passes silently

    @pytest.mark.asyncio
    async def test_dep_raises_412_when_user_revoked(self, _isolate_consent_module):
        register_feature("erp.lead_score", title="Lead Score", rationale="X.")
        sb, _ = _build_db(decisions_data=[{
            "feature_key": "erp.lead_score", "granted": False,
            "granted_at": None, "revoked_at": "2026-01-02T00:00:00Z",
        }])

        configure_consent_module(
            get_current_user=lambda authorization=None: (MagicMock(id="user-42"), "tok"),
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("erp.lead_score")

        with pytest.raises(AIConsentRequired) as exc_info:
            await dep(authorization="Bearer tok")
        assert exc_info.value.status_code == 412
        assert exc_info.value.details["feature_key"] == "erp.lead_score"

    @pytest.mark.asyncio
    async def test_dep_uses_default_grant_when_no_stored_decision(self, _isolate_consent_module):
        register_feature("mailing.subjects", title="Subjects", rationale="X.", default_granted=True)
        sb, _ = _build_db(decisions_data=[])  # empty — no stored decision

        configure_consent_module(
            get_current_user=lambda authorization=None: (MagicMock(id="u"), "t"),
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("mailing.subjects")

        result = await dep(authorization="Bearer t")
        assert result is None

    @pytest.mark.asyncio
    async def test_dep_fails_closed_for_unknown_feature(self, _isolate_consent_module):
        # Feature not in catalog + no stored row → fail-closed (raises 412)
        sb, _ = _build_db(decisions_data=[])
        configure_consent_module(
            get_current_user=lambda authorization=None: (MagicMock(id="u"), "t"),
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("unknown.feature")

        with pytest.raises(AIConsentRequired):
            await dep(authorization="Bearer t")

    @pytest.mark.asyncio
    async def test_dep_raises_412_when_user_id_missing(self, _isolate_consent_module):
        # If get_current_user produces something without an id, fail-closed.
        register_feature("k", title="K", rationale="X.", default_granted=True)
        sb, _ = _build_db(decisions_data=[])
        configure_consent_module(
            get_current_user=lambda authorization=None: (object(), "tok"),
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("k")

        with pytest.raises(AIConsentRequired):
            await dep(authorization="Bearer t")

    @pytest.mark.asyncio
    async def test_dep_handles_dict_user_shape(self, _isolate_consent_module):
        # Custom auth providers may return user as dict instead of object.
        register_feature("k", title="K", rationale="X.", default_granted=True)
        sb, _ = _build_db(decisions_data=[])
        configure_consent_module(
            get_current_user=lambda authorization=None: ({"id": "u-9"}, "tok"),
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("k")

        result = await dep(authorization="Bearer t")
        assert result is None

    @pytest.mark.asyncio
    async def test_dep_supports_async_get_current_user(self, _isolate_consent_module):
        # Seed's real get_current_user is async; ensure we await its result.
        register_feature("k", title="K", rationale="X.", default_granted=True)
        sb, _ = _build_db(decisions_data=[])

        async def async_user_dep(authorization=None):
            return (MagicMock(id="async-user"), "tok")

        configure_consent_module(
            get_current_user=async_user_dep,
            admin_client_factory=lambda: sb,
        )
        dep = consent_required("k")

        result = await dep(authorization="Bearer t")
        assert result is None


# ---------------------------------------------------------------------------
# Non-toggleable (locked-on infrastructure) features — §7.6 / 2026-04-27
# ---------------------------------------------------------------------------


class TestNonToggleableFeature:
    def test_register_feature_accepts_toggleable_kwarg(self):
        f = register_feature(
            "erp.embeddings",
            title="Embeddings",
            rationale="Infraestrutura de busca semântica.",
            toggleable=False,
        )
        assert f.toggleable is False
        assert get_feature("erp.embeddings").toggleable is False

    def test_register_feature_defaults_toggleable_true(self):
        f = register_feature("k", title="K", rationale="R")
        assert f.toggleable is True

    @pytest.mark.asyncio
    async def test_is_granted_short_circuits_to_true_for_non_toggleable(self):
        register_feature(
            "erp.embeddings", title="X", rationale="Y", toggleable=False,
            default_granted=False,  # explicitly False — short-circuit must override
        )
        # Even with a stored revoke decision, non-toggleable returns True.
        sb, _ = _build_db(decisions_data=[{
            "feature_key": "erp.embeddings", "granted": False,
            "granted_at": None, "revoked_at": "2026-01-01T00:00:00Z",
        }])
        assert await is_granted(sb, "user-1", "erp.embeddings") is True

    @pytest.mark.asyncio
    async def test_require_passes_silently_for_non_toggleable(self):
        register_feature(
            "erp.embeddings", title="X", rationale="Y", toggleable=False,
        )
        sb, _ = _build_db(decisions_data=[])
        # Should not raise — `require` calls `is_granted` which short-circuits.
        await require(sb, "user-1", "erp.embeddings")

    @pytest.mark.asyncio
    async def test_upsert_decision_raises_for_non_toggleable(self):
        register_feature(
            "erp.embeddings", title="Embeddings", rationale="Y", toggleable=False,
        )
        sb, _ = _build_db(upsert_data=[{}])
        with pytest.raises(MandatoryFeatureCannotBeToggled) as exc_info:
            await upsert_decision(sb, "user-1", "erp.embeddings", granted=False)
        assert exc_info.value.status_code == 403
        assert exc_info.value.details["feature_key"] == "erp.embeddings"
        assert exc_info.value.details["title"] == "Embeddings"

    @pytest.mark.asyncio
    async def test_upsert_decision_still_works_for_toggleable(self):
        register_feature("k", title="K", rationale="R")  # default toggleable=True
        sb, _ = _build_db(upsert_data=[{}])
        # Should not raise.
        await upsert_decision(sb, "user-1", "k", granted=True)

    @pytest.mark.asyncio
    async def test_list_view_includes_toggleable_field(self):
        register_feature("a", title="A", rationale="R-a", default_granted=True)
        register_feature("b", title="B", rationale="R-b", toggleable=False)
        sb, _ = _build_db(decisions_data=[])
        view = await list_user_consent_view(sb, "user-1")
        a = next(r for r in view if r["key"] == "a")
        b = next(r for r in view if r["key"] == "b")
        assert a["toggleable"] is True
        assert b["toggleable"] is False

    @pytest.mark.asyncio
    async def test_list_view_non_toggleable_always_granted_no_decision(self):
        register_feature("locked", title="L", rationale="R", toggleable=False)
        sb, _ = _build_db(decisions_data=[])
        view = await list_user_consent_view(sb, "user-1")
        row = next(r for r in view if r["key"] == "locked")
        assert row["granted"] is True
        assert row["decision_recorded"] is False

    def test_pending_count_excludes_non_toggleable(self):
        view = [
            {"decision_recorded": False, "toggleable": True},   # pending — counted
            {"decision_recorded": False, "toggleable": False},  # locked — NOT counted
            {"decision_recorded": True, "toggleable": True},    # decided — not counted
            {"decision_recorded": False, "toggleable": True},   # pending — counted
        ]
        assert pending_count(view) == 2

    def test_pending_count_handles_missing_toggleable_key_as_true(self):
        # Backward-compat — old views without `toggleable` field default to
        # treating the feature as toggleable (the previous behavior).
        view = [
            {"decision_recorded": False},            # no toggleable key — counts
            {"decision_recorded": False, "toggleable": False},
        ]
        assert pending_count(view) == 1
