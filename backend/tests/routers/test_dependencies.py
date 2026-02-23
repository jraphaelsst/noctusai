"""
Tests for shared dependencies: auth, logging, client creation.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.dependencies import get_current_user, log_action, get_user_client, get_admin_client
from tests.conftest import MockSupabaseClient, MockUser, MockUserResponse


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_authorization_header(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_bearer_format(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await get_current_user("InvalidToken")

    @pytest.mark.asyncio
    async def test_empty_bearer(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await get_current_user("Bearer ")

    @pytest.mark.asyncio
    async def test_valid_token(self):
        with patch("app.dependencies.get_supabase_client") as mock_client:
            admin = MockSupabaseClient()
            admin.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser("uid-123")))
            mock_client.return_value = admin

            user, token = await get_current_user("Bearer valid-token")
            assert user.id == "uid-123"
            assert token == "valid-token"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        from fastapi import HTTPException
        with patch("app.dependencies.get_supabase_client") as mock_client:
            admin = MockSupabaseClient()
            admin.auth.get_user = MagicMock(side_effect=Exception("Invalid"))
            mock_client.return_value = admin

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user("Bearer bad-token")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_null_user_returns_401(self):
        from fastapi import HTTPException
        with patch("app.dependencies.get_supabase_client") as mock_client:
            admin = MockSupabaseClient()
            mock_resp = MagicMock()
            mock_resp.user = None
            admin.auth.get_user = MagicMock(return_value=mock_resp)
            mock_client.return_value = admin

            with pytest.raises(HTTPException):
                await get_current_user("Bearer token-no-user")


class TestLogAction:
    def test_log_action_success(self):
        with patch("app.dependencies.get_admin_client") as mock_admin:
            client = MockSupabaseClient()
            mock_admin.return_value = client

            # Should not raise
            log_action("user-1", "criar", "cliente", "entity-1", "Test log")

    def test_log_action_failure_silent(self):
        with patch("app.dependencies.get_admin_client") as mock_admin:
            mock_client = MockSupabaseClient()
            # Make the insert raise an exception
            mock_table = MagicMock()
            mock_table.insert.return_value.execute.side_effect = Exception("DB down")
            mock_client.table = MagicMock(return_value=mock_table)
            mock_admin.return_value = mock_client

            # Should not raise even on failure
            log_action("user-1", "criar", "cliente", "entity-1", "Test")

    def test_log_action_with_details(self):
        with patch("app.dependencies.get_admin_client") as mock_admin:
            client = MockSupabaseClient()
            mock_admin.return_value = client

            log_action("user-1", "editar", "ativo", "a-1", "Edited", {"campo": "valor"})


class TestClientCreation:
    def test_get_user_client(self):
        with patch("app.dependencies.get_supabase_client") as mock:
            mock.return_value = MockSupabaseClient()
            client = get_user_client("test-token")
            mock.assert_called_with("test-token")

    def test_get_admin_client(self):
        with patch("app.dependencies.get_supabase_client") as mock:
            mock.return_value = MockSupabaseClient()
            client = get_admin_client()
            mock.assert_called_with()  # no args = admin
