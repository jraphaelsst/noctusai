"""Tests for the recurring transaction scheduler."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_executar_recorrentes_job_no_data():
    """Job completes gracefully when no active recurrences exist."""
    db = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    resp = MagicMock()
    resp.data = []
    builder.execute.return_value = resp
    db.table.return_value = builder

    with patch("app.scheduler.get_admin_client", return_value=db):
        from app.scheduler import executar_recorrentes_job
        await executar_recorrentes_job()


@pytest.mark.asyncio
async def test_executar_recorrentes_job_iterates_orgs():
    """Job iterates distinct org_ids and calls RecorrentesService for each."""
    db = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    resp = MagicMock()
    resp.data = [
        {"org_id": "org-1"},
        {"org_id": "org-2"},
        {"org_id": "org-1"},  # duplicate — should be deduped
    ]
    builder.execute.return_value = resp
    db.table.return_value = builder

    mock_service = MagicMock()
    mock_service.executar_pendentes = AsyncMock(return_value={
        "executadas": 3,
        "pendentes_processadas": 2,
        "erros": 0,
    })

    with (
        patch("app.scheduler.get_admin_client", return_value=db),
        patch("app.scheduler.RecorrentesService", return_value=mock_service) as MockClass,
    ):
        from app.scheduler import executar_recorrentes_job
        await executar_recorrentes_job()

    # Should be called for 2 unique orgs
    assert MockClass.call_count == 2
    assert mock_service.executar_pendentes.call_count == 2

    # Verify both org_ids were used
    called_org_ids = {call.args[1] for call in MockClass.call_args_list}
    assert called_org_ids == {"org-1", "org-2"}


@pytest.mark.asyncio
async def test_executar_recorrentes_job_handles_org_error():
    """Job continues to next org if one org fails."""
    db = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    resp = MagicMock()
    resp.data = [{"org_id": "org-1"}, {"org_id": "org-2"}]
    builder.execute.return_value = resp
    db.table.return_value = builder

    call_count = {"n": 0}

    async def _executar_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("DB error")
        return {"executadas": 1, "pendentes_processadas": 1, "erros": 0}

    mock_service = MagicMock()
    mock_service.executar_pendentes = AsyncMock(side_effect=_executar_side_effect)

    with (
        patch("app.scheduler.get_admin_client", return_value=db),
        patch("app.scheduler.RecorrentesService", return_value=mock_service),
    ):
        from app.scheduler import executar_recorrentes_job
        # Should not raise — errors are caught per-org
        await executar_recorrentes_job()

    assert mock_service.executar_pendentes.call_count == 2
