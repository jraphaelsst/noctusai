"""
Tests for the PostgREST exception handler — ensures PGRST116 errors
(from .single() with 0 rows) are converted to 404 responses, not 500s.

Regression test: Before this handler was added, any endpoint using .single()
on a non-existent record would return 500 instead of 404.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


class TestPostgRESTExceptionHandler:
    """Test the global PostgREST exception handler registered in main.py."""

    def test_pgrst116_returns_404(self, client):
        """
        Regression: .single() on 0 rows should return 404, not 500.
        We simulate this by making a table query raise the PostgREST APIError.
        """
        try:
            from postgrest.exceptions import APIError as PostgRESTError
        except ImportError:
            pytest.skip("postgrest not installed")

        # Create a PGRST116 error (the real error when .single() finds 0 rows)
        exc = PostgRESTError.__new__(PostgRESTError)
        exc.code = "PGRST116"
        exc.message = "JSON object requested, multiple (or no) rows returned"
        exc.args = (exc.message,)

        mock_sb = client.mock_supabase

        # Make notifications table raise PGRST116 when queried
        original_table = mock_sb.table

        def patched_table(name):
            if name == "notifications":
                qb = MagicMock()
                qb.select.return_value = qb
                qb.eq.return_value = qb
                qb.update.return_value = qb
                qb.single.return_value = qb
                qb.execute.side_effect = exc
                return qb
            return original_table(name)

        mock_sb.table = patched_table

        resp = client.patch("/api/notificacoes/nonexistent-id/ler")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"

    def test_other_postgrest_error_returns_500(self, client):
        """Non-PGRST116 PostgREST errors should still return 500."""
        try:
            from postgrest.exceptions import APIError as PostgRESTError
        except ImportError:
            pytest.skip("postgrest not installed")

        exc = PostgRESTError.__new__(PostgRESTError)
        exc.code = "PGRST301"
        exc.message = "Some other PostgREST error"
        exc.args = (exc.message,)

        mock_sb = client.mock_supabase
        original_table = mock_sb.table

        def patched_table(name):
            if name == "notifications":
                qb = MagicMock()
                qb.select.return_value = qb
                qb.eq.return_value = qb
                qb.update.return_value = qb
                qb.single.return_value = qb
                qb.execute.side_effect = exc
                return qb
            return original_table(name)

        mock_sb.table = patched_table

        resp = client.patch("/api/notificacoes/some-id/ler")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
