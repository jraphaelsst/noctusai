import json
import re
from pathlib import Path

import pytest

from app.schemas.store import LandingSettings
from app.services.assets import AssetService
from app.services.settings_service import DEFAULT_SETTINGS, SettingsService, SettingsVersionConflict
from app.stores.protocols import VersionConflict
from noctusai_lib.integrations.storage.fake import FakeStorageBackend
from tests.support.fakes import FakeSettingsStore

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "007_store_core.sql"


def _svc(store=None):
    return SettingsService(store or FakeSettingsStore(), AssetService(FakeStorageBackend()))


def test_empty_ledger_reports_version_0_defaults():
    version, data = _svc().current()
    assert version == 0
    assert data == DEFAULT_SETTINGS


def test_defaults_are_a_valid_settings_document():
    LandingSettings.model_validate(DEFAULT_SETTINGS)


def test_migration_seed_literal_equals_python_defaults():
    """Defaults live in ONE place: the migration's v1 seed is parsed and must
    equal `DEFAULT_SETTINGS` (so they can never drift apart)."""
    sql = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r"\$json\$(.*?)\$json\$", sql, re.S)
    assert match, "migration must seed version 1 with a $json$...$json$ literal"
    assert json.loads(match.group(1)) == DEFAULT_SETTINGS


def test_update_appends_and_never_mutates_history():
    store = FakeSettingsStore()
    svc = _svc(store)
    v1 = svc.update(LandingSettings.model_validate(DEFAULT_SETTINGS), 0, "u1")
    v2 = svc.update(
        LandingSettings.model_validate({**DEFAULT_SETTINGS, "price_cents": 5000}), 1, "u1"
    )
    assert (v1, v2) == (1, 2)
    assert [r["data"]["price_cents"] for r in store.rows] == [4700, 5000]
    assert all(r["created_by"] == "u1" for r in store.rows)


def test_stale_expected_version_conflicts():
    svc = _svc()
    svc.update(LandingSettings.model_validate(DEFAULT_SETTINGS), 0, None)
    with pytest.raises(SettingsVersionConflict):
        svc.update(LandingSettings.model_validate(DEFAULT_SETTINGS), 0, None)


def test_store_level_race_becomes_a_conflict():
    """Two writers computing the same next version: the store's PK refuses the
    loser, and the service surfaces that as a conflict (409), not a 500."""

    class RacingStore(FakeSettingsStore):
        def append(self, **kw):
            raise VersionConflict("lost the race")

    with pytest.raises(SettingsVersionConflict):
        _svc(RacingStore()).update(LandingSettings.model_validate(DEFAULT_SETTINGS), 0, None)
