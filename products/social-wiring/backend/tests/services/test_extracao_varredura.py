"""`app.services.extracao_varredura` — the shared recovery-sweep skeleton.

WHAT THIS PINS (2026-09-28 fix, verified by an audit against origin/dev)
-------------------------------------------------------------------------
`candidatos`'s retryable-error leg used to retry ANY `erro` row below the
attempt cap, regardless of what actually failed — so a document refused
for carrying a sensitive DPS (`documento_sensivel_dps`, never worth a
retry: a second pass re-reads the EXACT same document) was retried on
every sweep run, paying for a vision call and repeating the very LGPD
exposure the refusal existed to avoid. Now filtered through
`extracao_retentativa.retentavel`, the one definition of which codes ARE
worth a retry.

- a PERMANENT error code (`ERROS_PERMANENTES`) is never re-selected;
- an unknown OR genuinely-retryable code is still picked up (unchanged);
- the other two candidate legs (stale non-terminal, never-started) are
  pinned in each real adopter's own sweep tests
  (`tests/modules/empresas/test_sweep_service.py`) — this file is this
  shared module's OWN unit coverage.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.services import extracao_varredura

ORG_ID = str(uuid4())
TABLE = "docs_teste_varredura"
COLUNAS = (
    "id, org_id, owner_id, tipo_documento, extracao_status, "
    "extracao_tentativas, extracao_em, created_at, extracao_erro"
)


def _old(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _row(id_=None, **over) -> dict:
    row = {
        "id": id_ or str(uuid4()), "org_id": ORG_ID, "owner_id": str(uuid4()),
        "tipo_documento": "alfa", "extracao_status": "erro",
        "extracao_tentativas": 1, "extracao_em": _old(60),
        "created_at": _old(90), "extracao_erro": None, "deleted_at": None,
    }
    row.update(over)
    return row


async def _noop_extrair_fn(*args, **kwargs) -> dict:
    return {"status": "ok"}


def _config(*, extrair_fn=_noop_extrair_fn) -> extracao_varredura.SweepConfig:
    return extracao_varredura.SweepConfig(
        table=TABLE, owner_col="owner_id", colunas=COLUNAS, extrair_fn=extrair_fn,
    )


@pytest.fixture
def client():
    # A synthetic table, no backing migration — schema validation off,
    # same posture `tests/services/test_extracao_job.py` takes.
    return MockSupabaseClient()


class TestRetentavelFiltersTheErrorLeg:
    def test_a_permanent_error_code_is_never_a_candidate(self, client):
        client.table(TABLE).insert(_row(extracao_erro="documento_sensivel_dps")).execute()
        assert extracao_varredura.candidatos(client, _config(), limite=50) == []

    def test_an_error_code_with_a_message_is_still_matched_by_its_head(self, client):
        """`codigo_de_erro` reads the code BEFORE the first `:` — a message
        must not defeat the match."""
        client.table(TABLE).insert(
            _row(extracao_erro="documento_sensivel_dps: contém marcadores de DPS")
        ).execute()
        assert extracao_varredura.candidatos(client, _config(), limite=50) == []

    def test_an_unknown_or_retryable_code_is_still_a_candidate(self, client):
        client.table(TABLE).insert(_row(extracao_erro="storage: timeout")).execute()
        assert len(extracao_varredura.candidatos(client, _config(), limite=50)) == 1

    def test_a_null_error_is_treated_as_unknown_therefore_retryable(self, client):
        """A pre-154 row with no code yet still gets a chance — `retentavel`
        treats `None` as retryable (see its own docstring)."""
        client.table(TABLE).insert(_row(extracao_erro=None)).execute()
        assert len(extracao_varredura.candidatos(client, _config(), limite=50)) == 1

    @pytest.mark.asyncio
    async def test_varrer_never_retries_a_permanent_error(self, client):
        client.table(TABLE).insert(_row(extracao_erro="documento_sensivel_dps")).execute()
        called: list[int] = []

        async def _extrair_fn(*args, **kwargs) -> dict:
            called.append(1)
            return {"status": "ok"}

        result = await extracao_varredura.varrer(client, None, _config(extrair_fn=_extrair_fn))
        assert result == {"encontrados": 0, "retomados": 0, "esgotados": 0, "falhas": 0}
        assert called == []

    @pytest.mark.asyncio
    async def test_varrer_does_retry_a_retryable_error(self, client):
        client.table(TABLE).insert(_row(extracao_erro="storage: timeout")).execute()
        called: list[int] = []

        async def _extrair_fn(*args, **kwargs) -> dict:
            called.append(1)
            return {"status": "ok"}

        result = await extracao_varredura.varrer(client, None, _config(extrair_fn=_extrair_fn))
        assert result == {"encontrados": 1, "retomados": 1, "esgotados": 0, "falhas": 0}
        assert called == [1]
