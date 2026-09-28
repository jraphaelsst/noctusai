"""Planos (paid tiers) service — contract §Planos.

Routers stay thin; this owns the IO + business rules. Constructed
per-request from the user-scoped Supabase client so RLS binds to the
JWT identity — writes still stamp ``org_id`` to satisfy the RLS
``WITH CHECK``.

Sort order (``ordem`` then ``nome``) and pagination are applied in
Python after fetch rather than via ``.order()``/``.range()`` — the
in-repo ``MockSupabaseClient`` treats ``.order()`` as a no-op and has no
real SQL planner behind it, so relying on the client to sort/paginate
would make this service's behavior untestable (and silently different
between the mock and a real Postgrest instance). At this product's
scale (one community's tiers — tens of rows, not millions) fetching the
full filtered set and slicing in Python is the correct trade-off.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

_TABLE = "planos"
_MEMBROS_TABLE = "membros"

_DEFAULT_ENTITLEMENTS = {
    "feed": False,
    "forum": False,
    "chat": False,
    "eventos": False,
    "conteudo_ids": [],
    "grupos_whatsapp": [],
    "conteudo_todos": False,
}


#: Ninho Vazio tiers — projects/ninho-vazio/CONTRACT.md §Tiers. Data, not
#: code: `POST /api/planos/padrao` creates whichever are missing (matched by
#: `nome`); prices stay editable in Planos afterwards.
PLANOS_PADRAO: tuple[dict, ...] = (
    {"nome": "Gratuito", "preco_centavos": 0, "ciclo": "mensal",
     "grupoterapia": "nenhum", "ordem": 0},
    {"nome": "Ouvinte", "preco_centavos": 700, "ciclo": "mensal",
     "grupoterapia": "ouvir", "ordem": 1},
    {"nome": "Premium", "preco_centavos": 2700, "ciclo": "mensal",
     "grupoterapia": "falar", "ordem": 2},
)


class PlanosServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class PlanosService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    async def list(self, *, ativo: bool | None = None, page: int = 1, page_size: int = 50) -> dict:
        query = self._client.table(_TABLE).select("*").eq("org_id", self._org_id)
        if ativo is not None:
            query = query.eq("ativo", ativo)
        rows = query.execute().data or []
        rows.sort(key=lambda r: (r.get("ordem") or 0, r.get("nome") or ""))
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        counts = self._membros_ativos_counts([r["id"] for r in page_rows])
        items = [self._to_out(r, counts.get(str(r["id"]), 0)) for r in page_rows]
        return {"items": items, "total": total}

    async def get(self, *, plano_id: str) -> dict | None:
        result = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(plano_id))
            .maybe_single()
            .execute()
        )
        row = result.data
        if not row:
            return None
        counts = self._membros_ativos_counts([row["id"]])
        return self._to_out(row, counts.get(str(row["id"]), 0))

    def _membros_ativos_counts(self, plano_ids: list) -> dict[str, int]:
        """Count active members per plano — derived, never stored."""
        ids = [str(i) for i in plano_ids if i]
        if not ids:
            return {}
        rows = (
            self._client.table(_MEMBROS_TABLE)
            .select("plano_id")
            .eq("org_id", self._org_id)
            .eq("status", "ativo")
            .in_("plano_id", ids)
            .execute()
            .data
            or []
        )
        counts: dict[str, int] = {}
        for row in rows:
            pid = row.get("plano_id")
            if pid is None:
                continue
            pid = str(pid)
            if pid not in ids:
                # The mock's `.in_()` predicate degrades to match-all in
                # some code paths; guard defensively so a broader mock
                # response never leaks a count onto the wrong plano.
                continue
            counts[pid] = counts.get(pid, 0) + 1
        return counts

    @staticmethod
    def _to_out(row: dict, membros_ativos: int) -> dict:
        entitlements = {**_DEFAULT_ENTITLEMENTS, **(row.get("entitlements") or {})}
        return {**row, "entitlements": entitlements, "membros_ativos": membros_ativos}

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict) -> dict:
        nome = payload["nome"]
        existing = (
            self._client.table(_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("nome", nome)
            .execute()
            .data
        )
        if existing:
            raise PlanosServiceError(
                "Já existe um plano com esse nome.", status_code=409,
            )
        # Client-supplied id (never a client-facing field on `PlanoCreate` —
        # this is OUR generation, not caller input): Postgres would assign
        # `gen_random_uuid()` equally validly if omitted; supplying it
        # ourselves keeps behavior identical whether the backing store is
        # real Postgres or the in-repo `MockSupabaseClient` (whose auto-id
        # fallback is a non-UUID `mock-<table>-<n>` label the `Plano.id:
        # UUID` response model would otherwise reject).
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()), **payload, "org_id": self._org_id,
            "created_at": now, "updated_at": now,
        }
        result = self._client.table(_TABLE).insert(row).execute()
        if not result.data:
            raise PlanosServiceError("Falha ao criar plano.")
        created = result.data[0]
        return self._to_out(created, 0)

    async def criar_padrao(self) -> dict:
        """Create every missing tier of `PLANOS_PADRAO` (idempotent by
        `nome`, active or not). Returns `{"criados": [...], "existentes": [...]}`
        in the contract's table order."""
        existentes_nomes = {
            r.get("nome")
            for r in (
                self._client.table(_TABLE)
                .select("id,nome")
                .eq("org_id", self._org_id)
                .execute()
                .data
                or []
            )
        }
        criados: list[str] = []
        existentes: list[str] = []
        for tier in PLANOS_PADRAO:
            if tier["nome"] in existentes_nomes:
                existentes.append(tier["nome"])
                continue
            try:
                await self.create(payload={
                    "nome": tier["nome"],
                    "descricao": None,
                    "preco_centavos": tier["preco_centavos"],
                    "ciclo": tier["ciclo"],
                    "entitlements": {
                        **_DEFAULT_ENTITLEMENTS, "grupoterapia": tier["grupoterapia"],
                    },
                    "ordem": tier["ordem"],
                    "ativo": True,
                })
            except PlanosServiceError as exc:
                if exc.status_code != 409:
                    raise
                # A concurrent call created it between our read and write.
                existentes.append(tier["nome"])
                continue
            criados.append(tier["nome"])
        return {"criados": criados, "existentes": existentes}

    async def update(self, *, plano_id: str, payload: dict) -> dict | None:
        if "nome" in payload:
            existing = (
                self._client.table(_TABLE)
                .select("id")
                .eq("org_id", self._org_id)
                .eq("nome", payload["nome"])
                .execute()
                .data
                or []
            )
            if any(str(r["id"]) != str(plano_id) for r in existing):
                raise PlanosServiceError(
                    "Já existe um plano com esse nome.", status_code=409,
                )
        result = (
            self._client.table(_TABLE)
            .update(payload)
            .eq("org_id", self._org_id)
            .eq("id", str(plano_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        counts = self._membros_ativos_counts([row["id"]])
        return self._to_out(row, counts.get(str(row["id"]), 0))

    async def soft_delete(self, *, plano_id: str) -> bool:
        """Soft-delete: `ativo=false`. Members keep their historical `plano_id`.

        Contract: "If members still point at it, it still soft-deletes
        and the response is 204. Do not block." — no FK/ref check here
        by design.
        """
        result = (
            self._client.table(_TABLE)
            .update({"ativo": False})
            .eq("org_id", self._org_id)
            .eq("id", str(plano_id))
            .execute()
        )
        return bool(result.data)
