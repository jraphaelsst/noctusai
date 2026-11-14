"""Persistence port of the ImobShotAI cards (`imobshot_cards` / `imobshot_eventos`, migration 343).

Sync by design (PostgREST is blocking): the service calls it through `asyncio.to_thread`. Two implementations:
the Supabase one (the three atomic writes are RPCs, so a state change and its event are ONE transaction) and an
in-memory one for tests, reading the photo engine's in-memory repository the way the database joins tables."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from uuid import uuid4

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

CARDS = "imobshot_cards"
EVENTOS = "imobshot_eventos"
LOTES = "fotos_lotes"
FOTOS = "fotos_fotos"
_IN_BATCH = 100


@dataclass(frozen=True)
class Card:
    id: str
    org_id: str
    imovel_codigo: str
    etapa: str
    etapa_desde: datetime
    created_at: datetime
    updated_at: datetime
    fotos_concluidas_at: Optional[datetime] = None
    capa_foto_id: Optional[str] = None


@dataclass(frozen=True)
class LoteRef:
    id: str
    status: str
    criado_por: str
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class FotoRef:
    id: str
    lote_id: str
    storage_path_editada: Optional[str]
    storage_path_original: str = ""


@dataclass(frozen=True)
class Evento:
    tipo: str
    etapa_de: Optional[str]
    etapa_para: Optional[str]
    actor_id: Optional[str]
    at: datetime
    detalhe: dict = field(default_factory=dict)


class ImobshotRepository(Protocol):
    def obter_ou_criar_card(self, org_id: str, codigo: str, actor_id: str) -> tuple[Card, bool]: ...
    def vincular_lote(self, card_id: str, lote_id: str, actor_id: str) -> bool: ...
    def get_card(self, org_id: str, card_id: str) -> Optional[Card]: ...
    def list_cards(
        self, org_id: str, *, etapa: Optional[str], q: Optional[str], criado_por: Optional[str],
        limit: int, offset: int,
    ) -> tuple[list[Card], int]: ...
    def lotes_dos_cards(self, card_ids: list[str]) -> dict[str, list[LoteRef]]: ...
    def card_id_do_lote(self, lote_id: str) -> Optional[str]: ...
    def fotos_por_ids(self, foto_ids: list[str]) -> list[FotoRef]: ...
    def eventos(self, card_id: str, limit: int) -> list[Evento]: ...
    def aplicar_etapa(self, card_id: str, etapa: str, capa_foto_id: Optional[str], actor_id: Optional[str]) -> bool: ...


def _dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _card(row: dict) -> Card:
    return Card(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        imovel_codigo=row["imovel_codigo"],
        etapa=row["etapa"],
        etapa_desde=_dt(row["etapa_desde"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
        fotos_concluidas_at=_dt(row.get("fotos_concluidas_at")),
        capa_foto_id=str(row["capa_foto_id"]) if row.get("capa_foto_id") else None,
    )


def _prefix_pattern(q: str) -> Optional[str]:
    """`q` as an ilike prefix. Only code characters survive, so a wildcard or a PostgREST separator can't be injected."""
    clean = re.sub(r"[^A-Za-z0-9._-]", "", q or "")
    return f"{clean}%" if clean else None


class SupabaseImobshotRepository:
    """Over the `social_wiring`-scoped service-role client (bare table names)."""

    def __init__(self, client: Any) -> None:
        self._c = client

    def _rpc(self, name: str, params: dict) -> Any:
        return self._c.rpc(name, params).execute().data

    def obter_ou_criar_card(self, org_id: str, codigo: str, actor_id: str) -> tuple[Card, bool]:
        out = self._rpc(
            "imobshot_obter_ou_criar_card", {"p_org": org_id, "p_codigo": codigo, "p_ator": actor_id}
        )
        card = self.get_card(org_id, str(out["id"]))
        if card is None:
            raise RuntimeError(f"imobshot card {out['id']} vanished right after creation")
        return card, bool(out["criado"])

    def vincular_lote(self, card_id: str, lote_id: str, actor_id: str) -> bool:
        return bool(
            self._rpc("imobshot_vincular_lote", {"p_card": card_id, "p_lote": lote_id, "p_ator": actor_id})
        )

    def get_card(self, org_id: str, card_id: str) -> Optional[Card]:
        rows = (
            self._c.table(CARDS).select("*").eq("org_id", org_id).eq("id", card_id).limit(1).execute().data
        )
        return _card(rows[0]) if rows else None

    def list_cards(
        self, org_id: str, *, etapa: Optional[str], q: Optional[str], criado_por: Optional[str],
        limit: int, offset: int,
    ) -> tuple[list[Card], int]:
        # A corretor sees the cards holding a lote they created: an INNER embed on the FK, so a card appears once.
        select = "*, fotos_lotes!inner(criado_por)" if criado_por else "*"
        query = self._c.table(CARDS).select(select, count="exact").eq("org_id", org_id)
        if criado_por:
            query = query.eq("fotos_lotes.criado_por", criado_por)
        if etapa:
            query = query.eq("etapa", etapa)
        pattern = _prefix_pattern(q or "")
        if pattern:
            query = query.ilike("imovel_codigo", pattern)
        res = query.order("updated_at", desc=True).order("id").range(offset, offset + limit - 1).execute()
        return [_card(r) for r in (res.data or [])], int(res.count or 0)

    def lotes_dos_cards(self, card_ids: list[str]) -> dict[str, list[LoteRef]]:
        out: dict[str, list[LoteRef]] = {cid: [] for cid in card_ids}
        for i in range(0, len(card_ids), _IN_BATCH):
            chunk = card_ids[i : i + _IN_BATCH]
            for row in iter_paged_rows(
                lambda start, end, _c=chunk: self._c.table(LOTES)
                .select("id, card_id, status, criado_por, created_at")
                .in_("card_id", _c)
                .order("created_at", desc=True)
                .order("id")
                .range(start, end)
                .execute()
                .data
            ):
                out[str(row["card_id"])].append(
                    LoteRef(str(row["id"]), row["status"], str(row["criado_por"]), _dt(row.get("created_at")))
                )
        return out

    def card_id_do_lote(self, lote_id: str) -> Optional[str]:
        rows = self._c.table(LOTES).select("card_id").eq("id", lote_id).limit(1).execute().data
        return str(rows[0]["card_id"]) if rows and rows[0].get("card_id") else None

    def fotos_por_ids(self, foto_ids: list[str]) -> list[FotoRef]:
        out: list[FotoRef] = []
        for i in range(0, len(foto_ids), _IN_BATCH):
            chunk = foto_ids[i : i + _IN_BATCH]
            rows = (
                self._c.table(FOTOS)
                .select("id, lote_id, storage_path_original, storage_path_editada")
                .in_("id", chunk)
                .execute()
                .data
            )
            out += [
                FotoRef(str(r["id"]), str(r["lote_id"]), r.get("storage_path_editada"), r["storage_path_original"])
                for r in rows or []
            ]
        return out

    def eventos(self, card_id: str, limit: int) -> list[Evento]:
        rows = (
            self._c.table(EVENTOS)
            .select("tipo, etapa_de, etapa_para, actor_id, at, detalhe")
            .eq("card_id", card_id)
            .order("at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return [
            Evento(
                r["tipo"], r.get("etapa_de"), r.get("etapa_para"),
                str(r["actor_id"]) if r.get("actor_id") else None, _dt(r["at"]), r.get("detalhe") or {},
            )
            for r in rows or []
        ]

    def aplicar_etapa(self, card_id: str, etapa: str, capa_foto_id: Optional[str], actor_id: Optional[str]) -> bool:
        return bool(
            self._rpc(
                "imobshot_aplicar_etapa",
                {"p_card": card_id, "p_etapa": etapa, "p_capa": capa_foto_id, "p_ator": actor_id},
            )
        )


class InMemoryImobshotRepository:
    """Test double of the tables + the three functions, joined to the photo engine's in-memory repository."""

    def __init__(self, photo_repo: Any) -> None:
        self._photos = photo_repo
        self.cards: dict[str, Card] = {}
        self.events: list[tuple[str, Evento]] = []  # (card_id, evento)
        self.lote_card: dict[str, str] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _emit(self, card_id: str, tipo: str, actor_id: Optional[str], **kw: Any) -> None:
        self.events.append((card_id, Evento(tipo, kw.get("etapa_de"), kw.get("etapa_para"), actor_id, self._now(),
                                            kw.get("detalhe") or {})))

    def obter_ou_criar_card(self, org_id: str, codigo: str, actor_id: str) -> tuple[Card, bool]:
        for card in self.cards.values():
            if card.org_id == org_id and card.imovel_codigo == codigo:
                return card, False
        now = self._now()
        card = Card(str(uuid4()), org_id, codigo, "fotos_enviadas", now, now, now)
        self.cards[card.id] = card
        self._emit(card.id, "card_criado", actor_id, etapa_para="fotos_enviadas")
        return card, True

    def vincular_lote(self, card_id: str, lote_id: str, actor_id: str) -> bool:
        card = self.cards.get(card_id)
        batch = self._photos.batches.get(lote_id)
        if card is None or batch is None or batch.org_id != card.org_id or self.lote_card.get(lote_id) == card_id:
            return False
        self.lote_card[lote_id] = card_id
        self._emit(card_id, "lote_vinculado", actor_id, detalhe={"lote_id": lote_id})
        return True

    def get_card(self, org_id: str, card_id: str) -> Optional[Card]:
        card = self.cards.get(card_id)
        return card if card is not None and card.org_id == org_id else None

    def list_cards(
        self, org_id: str, *, etapa: Optional[str], q: Optional[str], criado_por: Optional[str],
        limit: int, offset: int,
    ) -> tuple[list[Card], int]:
        rows = [c for c in self.cards.values() if c.org_id == org_id]
        if etapa:
            rows = [c for c in rows if c.etapa == etapa]
        if q:
            rows = [c for c in rows if c.imovel_codigo.upper().startswith(q.strip().upper())]
        if criado_por:
            rows = [
                c for c in rows
                if any(
                    self._photos.batches[lid].criado_por == criado_por
                    for lid, cid in self.lote_card.items() if cid == c.id
                )
            ]
        rows.sort(key=lambda c: c.updated_at, reverse=True)
        return rows[offset : offset + limit], len(rows)

    def lotes_dos_cards(self, card_ids: list[str]) -> dict[str, list[LoteRef]]:
        out: dict[str, list[LoteRef]] = {cid: [] for cid in card_ids}
        for lote_id, card_id in self.lote_card.items():
            if card_id in out:
                b = self._photos.batches[lote_id]
                out[card_id].append(LoteRef(b.id, getattr(b.status, "value", b.status), b.criado_por, b.created_at))
        for refs in out.values():
            refs.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return out

    def card_id_do_lote(self, lote_id: str) -> Optional[str]:
        return self.lote_card.get(lote_id)

    def fotos_por_ids(self, foto_ids: list[str]) -> list[FotoRef]:
        return [
            FotoRef(p.id, p.lote_id, p.storage_path_editada, p.storage_path_original)
            for p in self._photos.photos.values() if p.id in set(foto_ids)
        ]

    def eventos(self, card_id: str, limit: int) -> list[Evento]:
        return [e for cid, e in reversed(self.events) if cid == card_id][:limit]

    def aplicar_etapa(self, card_id: str, etapa: str, capa_foto_id: Optional[str], actor_id: Optional[str]) -> bool:
        card = self.cards[card_id]
        now = self._now()
        if card.capa_foto_id != capa_foto_id:
            card = replace(card, capa_foto_id=capa_foto_id)
        if card.etapa == etapa:
            self.cards[card_id] = card
            return False
        self._emit(card_id, "etapa_mudou", actor_id, etapa_de=card.etapa, etapa_para=etapa)
        self.cards[card_id] = replace(
            card, etapa=etapa, etapa_desde=now, updated_at=now,
            fotos_concluidas_at=now if etapa == "fotos_aprovadas" else card.fotos_concluidas_at,
        )
        return True


__all__ = [
    "Card", "Evento", "FotoRef", "ImobshotRepository", "InMemoryImobshotRepository", "LoteRef",
    "SupabaseImobshotRepository",
]
