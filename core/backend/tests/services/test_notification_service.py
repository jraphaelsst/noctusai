"""Tests for the notification service."""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db(users_data=None, insert_data=None):
    """Create a mock admin client with table routing."""
    db = MagicMock()
    tables = {}

    def _table(name):
        if name not in tables:
            tables[name] = MagicMock()
        return tables[name]

    db.table = _table

    # noctus_users
    users_builder = MagicMock()
    users_builder.select.return_value = users_builder
    users_builder.eq.return_value = users_builder
    users_builder.neq.return_value = users_builder

    users_resp = MagicMock()
    users_resp.data = users_data if users_data is not None else []
    users_builder.execute.return_value = users_resp
    tables["noctus_users"] = users_builder

    # notifications
    notif_builder = MagicMock()
    notif_builder.insert.return_value = notif_builder

    notif_resp = MagicMock()
    notif_resp.data = insert_data if insert_data is not None else []
    notif_builder.execute.return_value = notif_resp
    tables["notifications"] = notif_builder

    return db, tables


# ---------------------------------------------------------------------------
# create() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_basic():
    """create() inserts a notification and returns the record."""
    record = {
        "id": "notif-1",
        "user_id": "user-1",
        "type": "system",
        "title": "Test",
        "message": "Hello",
        "metadata": {},
        "read": False,
    }
    db, tables = _mock_db(insert_data=[record])

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import create

        result = await create(
            user_id="user-1",
            org_id="org-1",
            type="system",
            title="Test",
            message="Hello",
        )

    assert result == record
    notif_builder = tables["notifications"]
    notif_builder.insert.assert_called_once()
    inserted = notif_builder.insert.call_args[0][0]
    assert inserted["user_id"] == "user-1"
    assert inserted["org_id"] == "org-1"
    assert inserted["type"] == "system"
    assert inserted["title"] == "Test"
    assert inserted["message"] == "Hello"
    assert inserted["read"] is False
    assert inserted["metadata"] == {}


@pytest.mark.asyncio
async def test_create_with_metadata():
    """create() includes custom metadata."""
    db, tables = _mock_db(insert_data=[{"id": "notif-2"}])

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import create

        await create(
            user_id="user-1",
            org_id=None,
            type="usage_alert",
            title="Limite",
            message="80% usado",
            metadata={"usage_pct": 80},
        )

    inserted = tables["notifications"].insert.call_args[0][0]
    assert inserted["metadata"] == {"usage_pct": 80}


@pytest.mark.asyncio
async def test_create_without_org_id():
    """create() omits org_id when None."""
    db, tables = _mock_db(insert_data=[{"id": "notif-3"}])

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import create

        await create(
            user_id="user-1",
            org_id=None,
            type="system",
            title="Info",
            message="General info",
        )

    inserted = tables["notifications"].insert.call_args[0][0]
    assert "org_id" not in inserted


@pytest.mark.asyncio
async def test_create_returns_empty_dict_on_failure():
    """create() returns {} when insert returns no data."""
    db, tables = _mock_db(insert_data=[])

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import create

        result = await create(
            user_id="user-1",
            org_id="org-1",
            type="system",
            title="Fail",
            message="Will fail",
        )

    assert result == {}


# ---------------------------------------------------------------------------
# notify_team() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_team_sends_to_all_members():
    """notify_team() creates a notification for each org member."""
    members = [{"id": "user-1"}, {"id": "user-2"}, {"id": "user-3"}]
    created = [
        {"id": "n1", "user_id": "user-1"},
        {"id": "n2", "user_id": "user-2"},
        {"id": "n3", "user_id": "user-3"},
    ]
    db, tables = _mock_db(users_data=members, insert_data=created)

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import notify_team

        result = await notify_team(
            org_id="org-1",
            type="subscription_change",
            title="Plano atualizado",
            message="Seu plano foi alterado para Pro",
        )

    assert len(result) == 3
    # Verify bulk insert with all rows
    notif_builder = tables["notifications"]
    notif_builder.insert.assert_called_once()
    rows = notif_builder.insert.call_args[0][0]
    assert len(rows) == 3
    assert {r["user_id"] for r in rows} == {"user-1", "user-2", "user-3"}
    for row in rows:
        assert row["org_id"] == "org-1"
        assert row["type"] == "subscription_change"
        assert row["read"] is False


@pytest.mark.asyncio
async def test_notify_team_excludes_user():
    """notify_team() excludes the specified user (e.g. the actor)."""
    members = [{"id": "user-2"}, {"id": "user-3"}]
    created = [{"id": "n1"}, {"id": "n2"}]
    db, tables = _mock_db(users_data=members, insert_data=created)

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import notify_team

        result = await notify_team(
            org_id="org-1",
            type="team_invite",
            title="Novo membro",
            message="Um novo membro entrou",
            exclude_user_id="user-1",
        )

    # Verify .neq was called to exclude the user
    users_builder = tables["noctus_users"]
    users_builder.neq.assert_called_once_with("id", "user-1")
    assert len(result) == 2


@pytest.mark.asyncio
async def test_notify_team_no_members():
    """notify_team() returns empty list when org has no members."""
    db, tables = _mock_db(users_data=[], insert_data=[])

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import notify_team

        result = await notify_team(
            org_id="org-empty",
            type="system",
            title="Test",
            message="No one to notify",
        )

    assert result == []
    # Should NOT attempt to insert notifications
    tables["notifications"].insert.assert_not_called()


@pytest.mark.asyncio
async def test_notify_team_with_metadata():
    """notify_team() includes metadata in all notification rows."""
    members = [{"id": "user-1"}]
    created = [{"id": "n1"}]
    db, tables = _mock_db(users_data=members, insert_data=created)

    with patch("app.services.notification_service.get_admin_client", return_value=db):
        from app.services.notification_service import notify_team

        await notify_team(
            org_id="org-1",
            type="system",
            title="Manutenção",
            message="Sistema em manutenção",
            metadata={"scheduled_at": "2026-04-10T03:00:00Z"},
        )

    rows = tables["notifications"].insert.call_args[0][0]
    assert rows[0]["metadata"] == {"scheduled_at": "2026-04-10T03:00:00Z"}
