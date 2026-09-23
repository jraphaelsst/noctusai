"""Tests for the audit log service."""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db(insert_data=None):
    """Create a mock admin client for audit_logs table."""
    db = MagicMock()
    builder = MagicMock()
    builder.insert.return_value = builder

    resp = MagicMock()
    resp.data = insert_data if insert_data is not None else []
    builder.execute.return_value = resp

    db.table.return_value = builder
    return db, builder


def _mock_request(ip=None, forwarded_ip=None, user_agent=None):
    """Create a mock FastAPI Request object."""
    req = MagicMock()
    headers_dict = {}
    if forwarded_ip:
        headers_dict["x-forwarded-for"] = forwarded_ip
    if user_agent:
        headers_dict["user-agent"] = user_agent

    mock_headers = MagicMock()
    mock_headers.get = lambda key, default=None: headers_dict.get(key, default)
    req.headers = mock_headers

    if ip:
        req.client = MagicMock()
        req.client.host = ip
    else:
        req.client = None

    return req


# ---------------------------------------------------------------------------
# log() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_basic():
    """log() creates an audit entry with required fields."""
    record = {
        "id": "audit-1",
        "user_id": "user-1",
        "org_id": "org-1",
        "action": "create",
        "resource_type": "subscription",
        "details": {},
    }
    db, builder = _mock_db(insert_data=[record])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        result = await log(
            user_id="user-1",
            org_id="org-1",
            action="create",
            resource_type="subscription",
        )

    assert result == record
    db.table.assert_called_with("audit_logs")
    builder.insert.assert_called_once()
    inserted = builder.insert.call_args[0][0]
    assert inserted["action"] == "create"
    assert inserted["resource_type"] == "subscription"
    assert inserted["user_id"] == "user-1"
    assert inserted["org_id"] == "org-1"
    assert inserted["details"] == {}


@pytest.mark.asyncio
async def test_log_with_resource_id():
    """log() includes resource_id when provided."""
    record = {"id": "audit-2", "resource_id": "sub-99"}
    db, builder = _mock_db(insert_data=[record])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        result = await log(
            user_id="user-1",
            org_id="org-1",
            action="delete",
            resource_type="license",
            resource_id="sub-99",
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["resource_id"] == "sub-99"
    assert result == record


@pytest.mark.asyncio
async def test_log_with_details():
    """log() includes custom details dict."""
    db, builder = _mock_db(insert_data=[{"id": "audit-3"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="update",
            resource_type="plan",
            details={"old_plan": "free", "new_plan": "pro"},
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["details"] == {"old_plan": "free", "new_plan": "pro"}


@pytest.mark.asyncio
async def test_log_without_user_id():
    """log() omits user_id for system actions (None)."""
    db, builder = _mock_db(insert_data=[{"id": "audit-4"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id=None,
            org_id="org-1",
            action="system_cleanup",
            resource_type="session",
        )

    inserted = builder.insert.call_args[0][0]
    assert "user_id" not in inserted


@pytest.mark.asyncio
async def test_log_without_org_id():
    """log() omits org_id when None."""
    db, builder = _mock_db(insert_data=[{"id": "audit-5"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id=None,
            action="login",
            resource_type="user",
        )

    inserted = builder.insert.call_args[0][0]
    assert "org_id" not in inserted


@pytest.mark.asyncio
async def test_log_extracts_ip_from_client():
    """log() extracts IP from request.client.host."""
    db, builder = _mock_db(insert_data=[{"id": "audit-6"}])
    req = _mock_request(ip="192.168.1.100")

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="login",
            resource_type="user",
            request=req,
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["ip_address"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_log_prefers_x_forwarded_for():
    """log() prefers X-Forwarded-For header over client.host."""
    db, builder = _mock_db(insert_data=[{"id": "audit-7"}])
    req = _mock_request(ip="127.0.0.1", forwarded_ip="203.0.113.50, 10.0.0.1")

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="login",
            resource_type="user",
            request=req,
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["ip_address"] == "203.0.113.50"


@pytest.mark.asyncio
async def test_log_extracts_user_agent():
    """log() extracts user-agent from request headers."""
    db, builder = _mock_db(insert_data=[{"id": "audit-8"}])
    req = _mock_request(ip="10.0.0.1", user_agent="Mozilla/5.0 TestBrowser")

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="login",
            resource_type="user",
            request=req,
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["user_agent"] == "Mozilla/5.0 TestBrowser"


@pytest.mark.asyncio
async def test_log_truncates_long_user_agent():
    """log() truncates user-agent strings longer than 500 chars."""
    db, builder = _mock_db(insert_data=[{"id": "audit-9"}])
    long_ua = "A" * 600
    req = _mock_request(ip="10.0.0.1", user_agent=long_ua)

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="login",
            resource_type="user",
            request=req,
        )

    inserted = builder.insert.call_args[0][0]
    assert len(inserted["user_agent"]) == 500


@pytest.mark.asyncio
async def test_log_backwards_compatible_omits_all_053_columns():
    """A caller that never touches the migration-053 kwargs must not have
    them appear in the insert payload at all — backwards compatibility."""
    db, builder = _mock_db(insert_data=[{"id": "audit-11"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="create",
            resource_type="subscription",
        )

    inserted = builder.insert.call_args[0][0]
    for column in (
        "product_slug", "method", "route_template", "path_params", "status_code",
        "correlation_id", "role", "actor_kind", "client_hint", "duration_ms",
        "before_snapshot",
    ):
        assert column not in inserted


@pytest.mark.asyncio
async def test_log_includes_053_columns_when_provided():
    db, builder = _mock_db(insert_data=[{"id": "audit-12"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="update",
            resource_type="license",
            resource_id="lic-1",
            product_slug="core",
            method="PATCH",
            route_template="/api/orgs/{org_id}/licenses/{license_id}",
            path_params={"org_id": "org-1", "license_id": "lic-1"},
            status_code=200,
            correlation_id="corr-1",
            role="admin",
            actor_kind="user",
            client_hint="web/chrome",
            duration_ms=42,
            before_snapshot={"status": "active"},
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["product_slug"] == "core"
    assert inserted["method"] == "PATCH"
    assert inserted["route_template"] == "/api/orgs/{org_id}/licenses/{license_id}"
    assert inserted["path_params"] == {"org_id": "org-1", "license_id": "lic-1"}
    assert inserted["status_code"] == 200
    assert inserted["correlation_id"] == "corr-1"
    assert inserted["role"] == "admin"
    assert inserted["actor_kind"] == "user"
    assert inserted["client_hint"] == "web/chrome"
    assert inserted["duration_ms"] == 42
    assert inserted["before_snapshot"] == {"status": "active"}


@pytest.mark.asyncio
async def test_log_actor_kind_agent_for_autonomous_actions():
    """An agent-originated action must be distinguishable from a user's."""
    db, builder = _mock_db(insert_data=[{"id": "audit-13"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id=None,
            org_id="org-1",
            action="publish",
            resource_type="agent_version",
            actor_kind="agent",
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["actor_kind"] == "agent"


@pytest.mark.asyncio
async def test_log_status_code_zero_is_included_not_treated_as_falsy():
    """status_code=0 / duration_ms=0 are valid values — `is not None`, not truthiness."""
    db, builder = _mock_db(insert_data=[{"id": "audit-14"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="noop",
            resource_type="session",
            status_code=0,
            duration_ms=0,
        )

    inserted = builder.insert.call_args[0][0]
    assert inserted["status_code"] == 0
    assert inserted["duration_ms"] == 0


@pytest.mark.asyncio
async def test_log_returns_empty_dict_on_failure():
    """log() returns {} when insert returns no data."""
    db, builder = _mock_db(insert_data=[])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        result = await log(
            user_id="user-1",
            org_id="org-1",
            action="create",
            resource_type="subscription",
        )

    assert result == {}


@pytest.mark.asyncio
async def test_log_no_request():
    """log() works correctly without a request object."""
    db, builder = _mock_db(insert_data=[{"id": "audit-10"}])

    with patch("app.services.audit_service.get_admin_client", return_value=db):
        from app.services.audit_service import log

        await log(
            user_id="user-1",
            org_id="org-1",
            action="create",
            resource_type="api_key",
        )

    inserted = builder.insert.call_args[0][0]
    assert "ip_address" not in inserted
    assert "user_agent" not in inserted
