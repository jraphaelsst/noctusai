"""Catch-up pass: resolve `situacao_cadastral` for empresas the automatic
(c2) fill at Crednet-creation time (`card_hub.crednet_service._resolver_
situacao_publica`) missed — a row created BEFORE this shipped, or one
whose lookup transiently failed at creation time.

Owner decision, this dispatch (2026-09-30): "the system resolves itself;
humans only when it truly can't" — and a company's `situação cadastral` is
PUBLIC data (`empresas.cnpj` is `NOT NULL` on every row — migration 167 —
so the whole selection criterion is simply `situacao_cadastral IS NULL`).

🔴 DELIBERATELY NOT BUILT ON `app.services.extracao_varredura`
-------------------------------------------------------------------
That module is the S2-contract formalization of "recover a DOCUMENT
extraction stuck in `pendente`/`processando`/a retryable `erro`" — its
whole candidate-selection shape (`extracao_status`, `extracao_tentativas`,
`extracao_erro` + `extracao_retentativa.retentavel`) is a state machine
tied to a document that was uploaded and started reading. An empresa with
a NULL `situacao_cadastral` has no document backing this pass at all —
forcing this onto `extracao_varredura`'s shape would mean inventing fake
`extracao_*` columns for a row family that has none, not a genuine THIRD
occurrence of the shape the recurrence rule targets.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.integrations.cnpj_registry.errors import CnpjRegistryError

from app.modules.empresas import dados_service
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "empresas"

#: Bounded per run (task requirement — "bounded per run") — a public API
#: call per row, no retry/backoff machinery here (this is a best-effort
#: catch-up; a row this run misses is picked up by the NEXT hourly run,
#: same "eventually resolved, never blocking" posture the whole feature
#: has). Conservative relative to `empresas.sweep_service`'s own default
#: (50) since each row here is potentially TWO outbound HTTP calls
#: (BrasilAPI + a ReceitaWS fallback), against public infrastructure this
#: platform does not control the capacity of.
DEFAULT_LIMITE = 25


def _t(client: Any, table: str):
    return table_reads.table(client, table)


async def resolver_pendentes(client: Any, lookup: Any, *, limite: int = DEFAULT_LIMITE) -> dict:
    """One bounded pass over every `empresas` row with `situacao_cadastral
    IS NULL`, oldest-first, resolved via the public CNPJ registry lookup.

    Never raises: one row's lookup failure (a transient BrasilAPI/ReceitaWS
    outage, or a confirmed not-found) is logged and skipped, never stopping
    the run — the office's own Cartão CNPJ upload, or a later run of this
    same pass, still resolves it. `aplicar_consulta_publica`'s own fill-
    empty contract makes re-running this pass over the SAME row idempotent:
    a row a Cartão CNPJ resolved in between simply reads `situacao_
    cadastral IS NOT NULL` already and is not selected again.

    Returns `{"encontrados": int, "resolvidos": int, "falhas": int}` —
    `encontrados` is what `extraction_sweep.make_sweep_job`'s own wrapper
    keys on to decide whether a run is worth a log line (same contract
    every OTHER sweep's return dict already provides).
    """
    pendentes = (
        _t(client, TABLE)
        .select("id, org_id, cnpj")
        .is_("situacao_cadastral", "null")
        .order("created_at")
        .limit(limite)
        .execute()
    ).data or []

    resolvidos = 0
    falhas = 0
    for empresa in pendentes:
        try:
            leitura = await lookup.lookup(empresa["cnpj"])
        except CnpjRegistryError as exc:
            falhas += 1
            # Recoverable, not a failure (`KB § PATTERNS/backend/
            # logging.md`): the NEXT hourly run, or an office Cartão CNPJ
            # upload in the meantime, still resolves this row.
            logger.warning(
                "consulta_publica_service: lookup failed for empresa %s (%s): %s",
                empresa["id"], empresa["cnpj"], exc,
            )
            continue
        resultado = dados_service.aplicar_consulta_publica(
            client, empresa["org_id"], empresa["id"], leitura,
        )
        if resultado["status"] == dados_service.CONSULTA_PUBLICA_APLICADO:
            resolvidos += 1

    return {"encontrados": len(pendentes), "resolvidos": resolvidos, "falhas": falhas}


__all__ = ["DEFAULT_LIMITE", "TABLE", "resolver_pendentes"]
