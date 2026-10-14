"""`StockPort` -- the seam other organs (commerce checkout / fulfillment, purchasing, igig) use to hold stock.

Protocol + Fake + Real + factory (CLAUDE.md §1 seed IO rule):

- `SupabaseStockPort(db, cfg)` -- the real one: the row-locked RPCs over a schema-scoped PostgREST client;
- `FakeStockPort` -- in-memory with the SAME semantics (available = on_hand - reserved, all-or-none lines,
  idempotency by order_ref, commit at average cost); tests of consumers run against it;
- `NoopStockPort` -- for products that do not track stock: every call succeeds and reserves nothing;
- `make_stock_port(kind=...)` -- the factory.

Order lifecycle (roadmap E6): created -> `reserve`; paid -> `commit`; expired / revoked -> `release`.
All three are idempotent on `order_ref`, so a retried webhook / re-run job never double-holds or double-ships.
A refusal raises `InventoryError` (`estoque_insuficiente`, `sem_reserva`, ...) in BOTH the real and the fake.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from . import stock as stock_svc
from ._common import Scope, dec, new_id
from .config import InventoryConfig
from .errors import (
    ESTOQUE_INSUFICIENTE,
    QUANTIDADE_DIVERGENTE,
    QUANTIDADE_INVALIDA,
    RESERVA_CONSUMIDA,
    RESERVA_LIBERADA,
    SEM_DEPOSITO_PADRAO,
    SEM_RESERVA,
    from_refusal,
    invalid,
)

Line = Mapping[str, Any]


@runtime_checkable
class StockPort(Protocol):
    """What another organ may ask of inventory. Sync, like the services behind it."""

    def reserve(self, org_id: str, order_ref: str, lines: Sequence[Line]) -> dict:
        """Hold `qty` of every `{item_id, qty, warehouse_id?}` line (default warehouse when omitted), all or none."""
        ...

    def commit(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        """Turn the order's reservation into a stock-out at the average cost."""
        ...

    def release(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        """Free the order's reservation. Nothing reserved is a no-op."""
        ...

    def receive_stock(
        self,
        org_id: str,
        *,
        item_id: str,
        warehouse_id: str,
        qty: Any,
        unit_cost_cents: int,
        source: str,
        source_ref: str,
        user_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        """Stock IN at `unit_cost_cents` (purchase receipt). Idempotent on `(source, source_ref, item, warehouse)`:
        a retried delivery answers `status="replayed"` and moves nothing."""
        ...


class NoopStockPort:
    """For products without stock tracking: nothing is held, nothing fails."""

    def reserve(self, org_id: str, order_ref: str, lines: Sequence[Line]) -> dict:
        return {"status": "ok", "moves": []}

    def commit(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        return {"status": "ok", "moves": []}

    def release(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        return {"status": "ok", "moves": []}

    def receive_stock(self, org_id: str, **_: Any) -> dict:
        return {"status": "ok", "moves": []}


class SupabaseStockPort:
    """The real seam: the row-locked RPCs, scoped to the caller's org."""

    def __init__(self, db: Any, cfg: InventoryConfig) -> None:
        self._db = db
        self._cfg = cfg

    def _scope(self, org_id: str) -> Scope:
        return Scope(self._db, self._cfg, str(org_id))

    def reserve(self, org_id: str, order_ref: str, lines: Sequence[Line]) -> dict:
        return stock_svc.reserve(self._scope(org_id), order_ref, lines)

    def commit(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        return stock_svc.commit(self._scope(org_id), order_ref, lines)

    def release(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        return stock_svc.release(self._scope(org_id), order_ref, lines)

    def receive_stock(
        self,
        org_id: str,
        *,
        item_id: str,
        warehouse_id: str,
        qty: Any,
        unit_cost_cents: int,
        source: str,
        source_ref: str,
        user_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        data = {
            "item_id": item_id, "warehouse_id": warehouse_id, "qty": qty, "unit_cost_cents": unit_cost_cents,
            "source": source, "source_ref": source_ref, "note": note,
        }
        return stock_svc.receive(self._scope(org_id), data, user_id=user_id)


@dataclass
class _Bal:
    on_hand: Decimal = Decimal(0)
    reserved: Decimal = Decimal(0)
    avg_cost_cents: int = 0


@dataclass
class FakeStockPort:
    """In-memory port with the real rules. Seed stock with `receive()`; inspect with `available()` / `balance()`."""

    default_warehouse: Optional[str] = "default"
    balances: dict[tuple[str, str, str], _Bal] = field(default_factory=dict)
    #: (org, order_ref) -> {(item, wh): {"qty", "state"}} with state in reserved / committed / released.
    orders: dict[tuple[str, str], dict[tuple[str, str], dict]] = field(default_factory=dict)
    moves: list[dict] = field(default_factory=list)
    _received: dict[tuple[str, str, str, str, str], dict] = field(default_factory=dict)

    # -- test helpers -----------------------------------------------------------------------
    def receive(self, org_id: str, item_id: str, qty: Any, unit_cost_cents: int = 0, warehouse_id: Optional[str] = None) -> None:
        wh = warehouse_id or self.default_warehouse or "default"
        bal = self.balances.setdefault((str(org_id), str(item_id), wh), _Bal())
        q = dec(qty)
        total = bal.on_hand + q
        bal.avg_cost_cents = int(((bal.on_hand * bal.avg_cost_cents + q * unit_cost_cents) / total).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        bal.on_hand = total
        self.moves.append({"id": new_id(), "kind": "in", "item_id": str(item_id), "warehouse_id": wh, "qty": float(q)})

    def balance(self, org_id: str, item_id: str, warehouse_id: Optional[str] = None) -> _Bal:
        return self.balances.get((str(org_id), str(item_id), warehouse_id or self.default_warehouse or "default"), _Bal())

    def available(self, org_id: str, item_id: str, warehouse_id: Optional[str] = None) -> Decimal:
        b = self.balance(org_id, item_id, warehouse_id)
        return b.on_hand - b.reserved

    # -- the port ---------------------------------------------------------------------------
    def receive_stock(
        self,
        org_id: str,
        *,
        item_id: str,
        warehouse_id: str,
        qty: Any,
        unit_cost_cents: int,
        source: str,
        source_ref: str,
        user_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        q = dec(qty)
        if q <= 0:
            raise invalid("qty", "A quantidade deve ser maior que zero.", code=QUANTIDADE_INVALIDA)
        key = (str(org_id), source, source_ref, str(item_id), str(warehouse_id))
        if key in self._received:
            return {"status": "replayed", "moves": [self._received[key]]}
        self.receive(org_id, item_id, q, unit_cost_cents, warehouse_id)
        move = {**self.moves[-1], "unit_cost_cents": unit_cost_cents, "source": source, "source_ref": source_ref}
        self.moves[-1] = move
        self._received[key] = move
        return {"status": "ok", "moves": [move]}

    def _wh(self, line: Line) -> str:
        wh = line.get("warehouse_id") or self.default_warehouse
        if not wh:
            raise from_refusal({"status": "refused", "code": SEM_DEPOSITO_PADRAO, "item_id": str(line.get("item_id"))})
        return str(wh)

    def reserve(self, org_id: str, order_ref: str, lines: Sequence[Line]) -> dict:
        if not lines or not order_ref:
            raise invalid("lines", "Informe ao menos uma linha.", code=QUANTIDADE_INVALIDA)
        want: dict[tuple[str, str], Decimal] = {}
        for line in lines:
            q = dec(line.get("qty"))
            if q <= 0:
                raise invalid("qty", "A quantidade deve ser maior que zero.", code=QUANTIDADE_INVALIDA)
            key = (str(line["item_id"]), self._wh(line))
            want[key] = want.get(key, Decimal(0)) + q
        held = self.orders.setdefault((str(org_id), order_ref), {})
        fresh = {k: q for k, q in want.items() if k not in held}
        for (item, wh), q in sorted(fresh.items()):  # all or none: check everything before touching anything
            b = self.balances.get((str(org_id), item, wh), _Bal())
            if b.on_hand - b.reserved < q:
                raise from_refusal({"status": "refused", "code": ESTOQUE_INSUFICIENTE, "item_id": item})
        moves = []
        for (item, wh), q in sorted(fresh.items()):
            self.balances.setdefault((str(org_id), item, wh), _Bal()).reserved += q
            held[(item, wh)] = {"qty": q, "state": "reserved"}
            moves.append({"id": new_id(), "kind": "reserve", "item_id": item, "warehouse_id": wh, "qty": float(q)})
        self.moves.extend(moves)
        return {"status": "ok" if fresh else "replayed", "moves": moves}

    def _targets(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]], *, strict: bool) -> list[tuple[tuple[str, str], dict]]:
        held = self.orders.get((str(org_id), order_ref), {})
        wanted = {str(line["item_id"]): line for line in (lines or [])}
        for item, line in wanted.items():
            total = sum((v["qty"] for (i, _), v in held.items() if i == item), Decimal(0))
            if total == 0:
                if strict:
                    raise from_refusal({"status": "refused", "code": SEM_RESERVA, "item_id": item})
            elif line.get("qty") is not None and dec(line["qty"]) != total:
                raise from_refusal({"status": "refused", "code": QUANTIDADE_DIVERGENTE, "item_id": item})
        picked = [(k, v) for k, v in sorted(held.items()) if not wanted or k[0] in wanted]
        if not picked and strict:
            raise from_refusal({"status": "refused", "code": SEM_RESERVA})
        return picked

    def commit(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        targets = self._targets(org_id, order_ref, lines, strict=True)
        for (item, _), v in targets:
            if v["state"] == "released":
                raise from_refusal({"status": "refused", "code": RESERVA_LIBERADA, "item_id": item})
        moves = []
        for (item, wh), v in targets:
            if v["state"] == "committed":
                continue
            b = self.balances[(str(org_id), item, wh)]
            b.reserved -= v["qty"]
            b.on_hand -= v["qty"]
            v["state"] = "committed"
            moves.append({"id": new_id(), "kind": "commit", "item_id": item, "warehouse_id": wh, "qty": float(v["qty"]), "unit_cost_cents": b.avg_cost_cents})
        self.moves.extend(moves)
        return {"status": "ok" if moves else "replayed", "moves": moves}

    def release(self, org_id: str, order_ref: str, lines: Optional[Sequence[Line]] = None) -> dict:
        targets = self._targets(org_id, order_ref, lines, strict=False)
        for (item, _), v in targets:
            if v["state"] == "committed":
                raise from_refusal({"status": "refused", "code": RESERVA_CONSUMIDA, "item_id": item})
        moves = []
        for (item, wh), v in targets:
            if v["state"] == "released":
                continue
            self.balances[(str(org_id), item, wh)].reserved -= v["qty"]
            v["state"] = "released"
            moves.append({"id": new_id(), "kind": "release", "item_id": item, "warehouse_id": wh, "qty": float(v["qty"])})
        self.moves.extend(moves)
        return {"status": "ok" if (moves or not targets) else "replayed", "moves": moves}


def make_stock_port(
    kind: Literal["noop", "fake", "supabase"] = "noop",
    *,
    db: Any = None,
    cfg: Optional[InventoryConfig] = None,
) -> StockPort:
    """Build a `StockPort`. `supabase` needs `db` (schema-scoped PostgREST client) and `cfg`."""
    if kind == "noop":
        return NoopStockPort()
    if kind == "fake":
        return FakeStockPort()
    if kind == "supabase":
        if db is None or cfg is None:
            raise ValueError("make_stock_port(kind='supabase') requires db= and cfg=")
        return SupabaseStockPort(db, cfg)
    raise ValueError(f"unknown stock port kind {kind!r}")


__all__ = ["FakeStockPort", "NoopStockPort", "StockPort", "SupabaseStockPort", "make_stock_port"]
