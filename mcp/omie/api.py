"""The Omie HTTP client — one envelope covers the entire API.

Every Omie resource speaks the identical shape::

    POST https://app.omie.com.br/api/v1/<family>/<resource>/
    {"call": "<Method>", "app_key": "...", "app_secret": "...",
     "param": [ { ...method params... } ]}

That uniformity is the whole leverage of this connector: **one** correct
transport covers all 134 endpoints and 461 methods, so the tool layer is
about ergonomics and safety rather than per-resource plumbing.

Three things this layer owns that a naive wrapper gets wrong:

1. **Faults are not HTTP statuses.** Omie answers failures with a
   `faultstring` body under an arbitrary status — and it can do so with
   HTTP 200. So the success path is inspected for a fault too, not just
   the error path (`errors.fault_from_body` / `classify_fault`).
2. **Writes are guarded twice** — an environment can be pinned
   `readonly`, and any mutating `call` additionally requires
   `confirm=true`. Omie has no undo and no sandbox; an accidental
   `ExcluirCliente` against a live company is unrecoverable.
3. **Throttle before sending.** Omie blocks a method for 30 minutes after
   10 consecutive failures, so retries are bounded and rate-limited
   (`ratelimit`), never a hot loop.

`_kit.transport.request_json` is sync (stdlib urllib); it runs in a
worker thread via `asyncio.to_thread` so the concurrency limiter is real
and the event loop is never blocked.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

from _kit.transport import request_json as _http_request_json

from .errors import (
    OmieApiError,
    OmieEmptyPage,
    OmieRateLimited,
    OmieReadOnlyEnvironment,
    ConfirmationRequiredError,
    classify_fault,
    fault_from_body,
)
from .ratelimit import limiter
from .settings import OmieEnvironment, get_settings

#: Verb prefixes that mutate data in Omie. Derived from the harvested
#: catalog's verb distribution — kept as a prefix rule (not a method list)
#: so a method added by Omie tomorrow is guarded by default, not missed.
MUTATING_PREFIXES = (
    "Incluir", "Alterar", "Excluir", "Upsert", "Associar", "Cancelar",
    "Importar", "Gerar", "Enviar", "Faturar", "Encerrar", "Reabrir",
    "Estornar", "Desassociar", "Trocar", "Ativar", "Desativar",
)
#: Read verbs — everything else is treated as mutating (fail-safe default).
READ_PREFIXES = ("Listar", "Consultar", "Obter", "Pesquisar", "Verificar", "Resumo")

MAX_PAGE_SIZE = 100  # Omie hard ceiling
_RETRY_STATUSES = {425, 429, 500, 502, 503, 504}


def is_mutating(call: str) -> bool:
    """True when `call` writes. Unknown verbs count as mutating.

    Fail-safe on purpose: a new Omie verb we've never seen should trip the
    confirm guard, not slip past it.
    """
    if call.startswith(READ_PREFIXES):
        return False
    return True if call.startswith(MUTATING_PREFIXES) else True


def normalize_path(path: str) -> str:
    """Accept `geral/clientes`, `/geral/clientes/`, or a full URL → `/geral/clientes/`."""
    p = (path or "").strip()
    p = re.sub(r"^https?://[^/]+", "", p)
    p = re.sub(r"^/?api/v1/", "", p.lstrip("/"))
    p = p.strip("/")
    return f"/{p}/" if p else "/"


class OmieClient:
    """Environment-bound Omie client. One instance per resolved environment."""

    def __init__(self, env: OmieEnvironment, *, base_url: str = "", timeout: float = 0.0):
        s = get_settings()
        self.env = env
        self.base_url = (base_url or s.base_url).rstrip("/")
        self.timeout = timeout or s.timeout_seconds

    # -- core -------------------------------------------------------------
    async def call(
        self,
        path: str,
        call: str,
        param: Optional[dict | list] = None,
        *,
        confirm: bool = False,
        allow_empty_page: bool = False,
        max_retries: int = 2,
    ) -> Any:
        """Invoke one Omie method. Returns the parsed JSON result.

        Raises a typed `OmieApiError` subclass on any failure — never a
        partial or fabricated success.
        """
        endpoint = normalize_path(path)
        url = f"{self.base_url}{endpoint}"
        tag = f"omie {call} {endpoint}"

        if is_mutating(call):
            if self.env.readonly:
                raise OmieReadOnlyEnvironment(
                    f"Environment {self.env.name!r} is pinned readonly — refusing "
                    f"the mutating call {call!r}. NO side-effect was performed."
                )
            if not confirm:
                raise ConfirmationRequiredError(
                    f"{call} on {endpoint} (environment {self.env.name!r})",
                    "Omie has no undo and no sandbox",
                )

        params = param if isinstance(param, list) else [param or {}]
        body = {
            "call": call,
            "app_key": self.env.app_key,
            "app_secret": self.env.app_secret,
            "param": params,
        }

        key = limiter.key(self.env.app_key, endpoint, call)
        blocked = limiter.circuit_block(key)
        if blocked is not None:
            raise OmieRateLimited(
                f"{tag} — local circuit open after repeated failures; retry in "
                f"{blocked:.0f}s. (Guards against Omie's 30-min server-side block.)",
                status=429,
                retry_after=blocked,
            )

        attempt, last_exc = 0, None
        while attempt <= max_retries:
            sem = await limiter.acquire(key)
            try:
                raw = await asyncio.to_thread(
                    _http_request_json,
                    "POST",
                    url,
                    body=body,
                    timeout=self.timeout,
                    error_cls=OmieApiError,
                    empty_result={},
                    label=tag,
                    on_http_error=lambda st, bd, tg: fault_from_body(
                        bd, http_status=st, tag=tg
                    ),
                )
            except OmieApiError as e:
                last_exc = e
                limiter.record_failure(key)
                if isinstance(e, OmieEmptyPage):
                    limiter.record_success(key)  # end-of-data is not a failure
                    if allow_empty_page:
                        return {"_empty_page": True, "faultstring": e.faultstring}
                    raise
                if e.status in _RETRY_STATUSES and attempt < max_retries:
                    backoff = getattr(e, "retry_after", None) or (2.0 ** attempt)
                    if e.status == 425:
                        raise  # a 30-min block is never worth retrying into
                    await asyncio.sleep(min(backoff, 30.0))
                    attempt += 1
                    continue
                raise
            finally:
                sem.release()

            # Omie can report a fault with HTTP 200 — inspect the success body.
            if isinstance(raw, dict) and "faultstring" in raw:
                exc = classify_fault(
                    str(raw.get("faultstring") or ""),
                    http_status=200,
                    faultcode=raw.get("faultcode"),
                    tag=tag,
                )
                if isinstance(exc, OmieEmptyPage):
                    limiter.record_success(key)
                    if allow_empty_page:
                        return {"_empty_page": True, "faultstring": exc.faultstring}
                    raise exc
                limiter.record_failure(key)
                raise exc

            limiter.record_success(key)
            return raw

        raise last_exc or OmieApiError(f"{tag} — exhausted retries", status=502)

    # -- pagination -------------------------------------------------------
    async def paginate(
        self,
        path: str,
        call: str,
        param: Optional[dict] = None,
        *,
        page_size: int = 50,
        max_pages: int = 10,
        max_records: Optional[int] = None,
        records_key: Optional[str] = None,
    ) -> dict:
        """Walk a `Listar*` method across pages and concatenate its records.

        Omie caps `registros_por_pagina` at 100 and signals end-of-data with
        a fault, which `OmieEmptyPage` turns into a clean stop.

        `max_pages` is a REAL bound, and the result always reports
        `truncated` + `pages_fetched` — a silently-capped list that looks
        complete is the failure mode this guards against.
        """
        base = dict(param or {})
        size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        records: list = []
        page = int(base.get("pagina") or 1)
        last_fetched = page - 1
        pages_fetched = 0
        total_pages = total_records = None
        detected_key = records_key

        while pages_fetched < max_pages:
            payload = {**base, "pagina": page, "registros_por_pagina": size}
            last_fetched = page
            result = await self.call(path, call, payload, allow_empty_page=True)
            if isinstance(result, dict) and result.get("_empty_page"):
                break
            if not isinstance(result, dict):
                records.append(result)
                pages_fetched += 1
                break

            total_pages = result.get("total_de_paginas", total_pages)
            total_records = result.get("total_de_registros", total_records)

            if detected_key is None:
                detected_key = _detect_records_key(result)
            batch = result.get(detected_key) if detected_key else None
            if not isinstance(batch, list):
                # No recognisable record array — return the raw page rather
                # than pretending we understood the shape.
                return {
                    "records": records,
                    "pages_fetched": pages_fetched,
                    "raw_page": result,
                    "records_key": detected_key,
                    "truncated": False,
                    "note": "Unrecognised list shape — `raw_page` holds the "
                            "verbatim response for this method.",
                }

            records.extend(batch)
            pages_fetched += 1
            if max_records is not None and len(records) >= max_records:
                records = records[:max_records]
                break
            if not batch or (total_pages is not None and page >= int(total_pages)):
                break
            page += 1

        # `last_fetched` (not the loop's lookahead `page`) is what the caller
        # resumes from — the two differ depending on which break fired.
        more_pages = bool(total_pages is not None and last_fetched < int(total_pages))
        hit_record_cap = bool(max_records is not None and len(records) >= max_records)
        return {
            "records": records,
            "records_key": detected_key,
            "count": len(records),
            "pages_fetched": pages_fetched,
            "page_size": size,
            "total_de_paginas": total_pages,
            "total_de_registros": total_records,
            "truncated": (pages_fetched >= max_pages and more_pages) or hit_record_cap,
            "next_page": last_fetched + 1 if more_pages else None,
        }


def _detect_records_key(page: dict) -> Optional[str]:
    """Find the record array in a `Listar*` response.

    Omie names it per resource (`clientes_cadastro`, `produto_servico_cadastro`,
    `conta_pagar_cadastro`, `pedido_venda_produto`, …), so we detect the sole
    list-of-objects value rather than hard-coding ~115 key names — which would
    be a hand-maintained list that drifts (CLAUDE.md §1).
    """
    meta = {"pagina", "total_de_paginas", "registros", "total_de_registros"}
    candidates = [
        k for k, v in page.items()
        if k not in meta and isinstance(v, list) and (not v or isinstance(v[0], dict))
    ]
    if len(candidates) == 1:
        return candidates[0]
    for k in candidates:  # prefer the longest array when a page carries several
        return max(candidates, key=lambda c: len(page[c]))
    return None


def client_for(environment: Optional[str]) -> OmieClient:
    """Resolve an environment name → a bound client (raises OmieConfigError)."""
    return OmieClient(get_settings().get(environment))


__all__ = [
    "OmieClient",
    "client_for",
    "is_mutating",
    "normalize_path",
    "MAX_PAGE_SIZE",
    "MUTATING_PREFIXES",
]
