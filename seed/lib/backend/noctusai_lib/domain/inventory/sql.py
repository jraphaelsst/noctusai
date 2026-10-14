"""`inventory_migration(cfg, schema)` -- the inventory DDL for a product's schema.

Same conventions as `finance_migration`: `org_id UUID NOT NULL` on every table, RLS enabled with an
`authenticated` own-org SELECT policy and the literal `service_role_bypass`; the backend writes through
the service-role client. Forward-only and idempotent (applied twice by the chain replay).

Why every mutation is an RPC (the overselling guard, roadmap E6/E12): PostgREST has no multi-statement
transaction, so "read on_hand, check, update" from Python lets two concurrent reserves of the last unit
both pass. Each RPC takes `SELECT ... FOR UPDATE` on the balance row, writes the kardex move AND updates
the balance in ONE transaction, and `CHECK (on_hand - reserved >= 0)` on the balance is the unconditional
backstop -- the DB, not the application, makes overselling impossible.

Valuation is MOVING AVERAGE COST (LIFO is not permitted in Brazil; brief §B): every receipt recomputes
`avg_cost_cents = round((on_hand*avg + qty*cost) / (on_hand + qty))`; every outflow leaves at the current
average. Quantities are `numeric(18,3)` (fractional KG); money is integer cents (`BIGINT`).

RPC contract: each returns jsonb `{"status": "ok"|"replayed"|"refused", "code"?, "item_id"?, "moves": [...]}`.
A refusal inside the (sub)transaction rolls ALL of that call's lines back (a plpgsql exception block is a
savepoint), then is reported as data, not raised. Idempotency key (a unique index):
`(org_id, source, source_ref, kind, item_id, warehouse_id)`.

Prerequisites (not created here): `public.current_org_id_for(text)` (core 070; the default `org_id_expr`)
and, when `cfg.with_items`, the `items` organ's `<items_prefix>items` table with an `org_id` column.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import rls_subquery_policy, service_role_bypass

from .config import InventoryConfig
from .types import MoveKind, values

#: Every organ table (unprefixed), in dependency order. The generator and isolation tests iterate this.
INVENTORY_TABLES: tuple[str, ...] = ("warehouses", "item_settings", "stock_balances", "stock_moves")

#: Append-only history: the kardex is never updated, deleted or truncated (a trigger refuses).
APPEND_ONLY_TABLES: tuple[str, ...] = ("stock_moves",)

#: SQLSTATE used to carry a business refusal out of a nested block (`IN001`) / an append-only violation (`IN002`).
REFUSAL_SQLSTATE = "IN001"
APPEND_ONLY_SQLSTATE = "IN002"

RPC_NAMES: tuple[str, ...] = ("receive", "issue", "adjust", "transfer", "reserve", "commit", "release")


def _in(enum_cls) -> str:
    return ", ".join(f"'{v}'" for v in values(enum_cls))


def _org_rls(schema: str, table: str, org_id_expr: str) -> str:
    select_name = f"{table}_select_own_org"
    return "\n".join(
        [
            f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;",
            f'DROP POLICY IF EXISTS "{select_name}" ON {schema}.{table};',
            rls_subquery_policy(schema, table, select_name, "SELECT", using=f"org_id = (SELECT {org_id_expr})"),
            f'DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{table};',
            service_role_bypass(table, schema=schema),
        ]
    )


def _tables(cfg: InventoryConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    t = {name: cfg.table(name) for name in INVENTORY_TABLES}
    item_fk = f" REFERENCES {s}.{cfg.items_table}(id) ON DELETE RESTRICT" if cfg.with_items else ""
    sections = [
        (
            "Warehouses. One default per org (partial unique index); never deleted, only deactivated.",
            "warehouses",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['warehouses']} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    name        TEXT NOT NULL,
    code        TEXT NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT false,
    address     JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (btrim(name) <> '' AND btrim(code) <> ''),
    CHECK (NOT (is_default AND NOT active))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['warehouses']}_code ON {s}.{t['warehouses']} (org_id, lower(code));
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['warehouses']}_default ON {s}.{t['warehouses']} (org_id) WHERE is_default;
""",
        ),
        (
            "Per item x warehouse settings (the low-stock threshold).",
            "item_settings",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['item_settings']} (
    org_id        UUID NOT NULL,
    item_id       UUID NOT NULL{item_fk},
    warehouse_id  UUID NOT NULL REFERENCES {s}.{t['warehouses']}(id) ON DELETE RESTRICT,
    min_qty       NUMERIC(18,3) NOT NULL DEFAULT 0 CHECK (min_qty >= 0),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, item_id, warehouse_id)
);
""",
        ),
        (
            "Balances: the cache the kardex explains. The CHECKs are the overselling backstop (stock=1 pieces).",
            "stock_balances",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['stock_balances']} (
    org_id         UUID NOT NULL,
    item_id        UUID NOT NULL{item_fk},
    warehouse_id   UUID NOT NULL REFERENCES {s}.{t['warehouses']}(id) ON DELETE RESTRICT,
    on_hand        NUMERIC(18,3) NOT NULL DEFAULT 0,
    reserved       NUMERIC(18,3) NOT NULL DEFAULT 0,
    avg_cost_cents BIGINT NOT NULL DEFAULT 0 CHECK (avg_cost_cents >= 0),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, item_id, warehouse_id),
    CONSTRAINT {t['stock_balances']}_reserved_nonneg CHECK (reserved >= 0),
    CONSTRAINT {t['stock_balances']}_available_nonneg CHECK (on_hand - reserved >= 0)
);
CREATE INDEX IF NOT EXISTS idx_{t['stock_balances']}_wh ON {s}.{t['stock_balances']} (org_id, warehouse_id);
""",
        ),
        (
            "Stock moves (APPEND-ONLY kardex). `seq` orders the history; *_after columns make the running "
            "balance a read. adjust.qty is the signed delta; every other kind is > 0.",
            "stock_moves",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['stock_moves']} (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq                   BIGINT GENERATED ALWAYS AS IDENTITY,
    org_id                UUID NOT NULL,
    item_id               UUID NOT NULL{item_fk},
    warehouse_id          UUID NOT NULL REFERENCES {s}.{t['warehouses']}(id) ON DELETE RESTRICT,
    kind                  TEXT NOT NULL CHECK (kind IN ({_in(MoveKind)})),
    qty                   NUMERIC(18,3) NOT NULL,
    unit_cost_cents       BIGINT NOT NULL DEFAULT 0 CHECK (unit_cost_cents >= 0),
    source                TEXT NOT NULL DEFAULT 'manual',
    source_ref            TEXT,
    transfer_group        UUID,
    note                  TEXT,
    on_hand_after         NUMERIC(18,3) NOT NULL,
    reserved_after        NUMERIC(18,3) NOT NULL,
    avg_cost_after_cents  BIGINT NOT NULL,
    occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by            UUID,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (qty <> 0),
    CHECK (kind = 'adjust' OR qty > 0),
    CHECK (source_ref IS NULL OR btrim(source_ref) <> ''),
    CHECK ((kind IN ('transfer_in', 'transfer_out')) = (transfer_group IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['stock_moves']}_idem
    ON {s}.{t['stock_moves']} (org_id, source, source_ref, kind, item_id, warehouse_id) WHERE source_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['stock_moves']}_item ON {s}.{t['stock_moves']} (org_id, item_id, warehouse_id, seq);
CREATE INDEX IF NOT EXISTS idx_{t['stock_moves']}_ref ON {s}.{t['stock_moves']} (org_id, source, source_ref) WHERE source_ref IS NOT NULL;

CREATE OR REPLACE FUNCTION {s}.{t['stock_moves']}_append_only() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, {s}, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION '{t['stock_moves']} is append-only (% refused)', TG_OP USING ERRCODE = '{APPEND_ONLY_SQLSTATE}';
END;
$fn$;
DROP TRIGGER IF EXISTS {t['stock_moves']}_no_update_delete ON {s}.{t['stock_moves']};
CREATE TRIGGER {t['stock_moves']}_no_update_delete BEFORE UPDATE OR DELETE ON {s}.{t['stock_moves']}
    FOR EACH ROW EXECUTE FUNCTION {s}.{t['stock_moves']}_append_only();
DROP TRIGGER IF EXISTS {t['stock_moves']}_no_truncate ON {s}.{t['stock_moves']};
CREATE TRIGGER {t['stock_moves']}_no_truncate BEFORE TRUNCATE ON {s}.{t['stock_moves']}
    FOR EACH STATEMENT EXECUTE FUNCTION {s}.{t['stock_moves']}_append_only();
""",
        ),
    ]
    out: list[str] = []
    for title, name, body in sections:
        out.append(f"-- {title}\n{body.strip()}\n{_org_rls(s, t[name], o)}")
    return out


def _refuse(code: str, item: str = "NULL") -> str:
    detail = f", DETAIL = {item}::text" if item != "NULL" else ""
    return f"RAISE EXCEPTION USING ERRCODE = '{REFUSAL_SQLSTATE}', MESSAGE = '{code}'{detail};"


def _handler() -> str:
    return f"""EXCEPTION WHEN SQLSTATE '{REFUSAL_SQLSTATE}' THEN
    GET STACKED DIAGNOSTICS v_code = MESSAGE_TEXT, v_item = PG_EXCEPTION_DETAIL;
    RETURN jsonb_build_object('status', 'refused', 'code', v_code, 'item_id', NULLIF(v_item, ''));"""


def _secdef(s: str, name: str, args: str, sig: str, returns: str, declare: str, body: str) -> str:
    return f"""CREATE OR REPLACE FUNCTION {s}.{name}({args}) RETURNS {returns}
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, {s}, pg_temp
AS $fn$
{declare.strip()}
{body.strip()}
$fn$;
REVOKE ALL ON FUNCTION {s}.{name}({sig}) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {s}.{name}({sig}) TO service_role;"""


def _rpcs(cfg: InventoryConfig, s: str) -> str:
    t = {name: cfg.table(name) for name in INVENTORY_TABLES}
    wh, bal, mv = f"{s}.{t['warehouses']}", f"{s}.{t['stock_balances']}", f"{s}.{t['stock_moves']}"
    n = {name: cfg.rpc(name) for name in (*RPC_NAMES, "lock_balance", "apply_move")}
    item_check = (
        f"""    IF NOT EXISTS (SELECT 1 FROM {s}.{cfg.items_table} WHERE id = p_item AND org_id = p_org) THEN
        {_refuse('item_invalido', 'p_item')}
    END IF;
"""
        if cfg.with_items
        else ""
    )
    lock_balance = _secdef(
        s, n["lock_balance"], "p_org UUID, p_item UUID, p_wh UUID", "UUID, UUID, UUID", bal,
        "DECLARE v_bal %s%%ROWTYPE;" % bal,
        f"""
BEGIN
    IF NOT EXISTS (SELECT 1 FROM {wh} WHERE id = p_wh AND org_id = p_org) THEN
        {_refuse('deposito_invalido')}
    END IF;
{item_check}    INSERT INTO {bal} (org_id, item_id, warehouse_id) VALUES (p_org, p_item, p_wh) ON CONFLICT DO NOTHING;
    SELECT * INTO v_bal FROM {bal} WHERE org_id = p_org AND item_id = p_item AND warehouse_id = p_wh FOR UPDATE;
    RETURN v_bal;
END;""",
    )
    apply_move = _secdef(
        s, n["apply_move"],
        "p_org UUID, p_item UUID, p_wh UUID, p_kind TEXT, p_qty NUMERIC, p_cost BIGINT, p_source TEXT, p_ref TEXT, "
        "p_user UUID, p_note TEXT, p_group UUID, p_occurred TIMESTAMPTZ",
        "UUID, UUID, UUID, TEXT, NUMERIC, BIGINT, TEXT, TEXT, UUID, TEXT, UUID, TIMESTAMPTZ", "JSONB",
        f"""
DECLARE
    v_bal  {bal}%ROWTYPE;
    v_prev {mv}%ROWTYPE;
    v_move {mv}%ROWTYPE;
    v_on   NUMERIC; v_res NUMERIC; v_avg BIGINT; v_cost BIGINT;
""",
        f"""
BEGIN
    IF p_qty IS NULL OR p_qty = 0 OR (p_kind <> 'adjust' AND p_qty < 0) THEN
        {_refuse('quantidade_invalida', 'p_item')}
    END IF;
    IF p_cost IS NOT NULL AND p_cost < 0 THEN
        {_refuse('custo_invalido', 'p_item')}
    END IF;
    v_bal := {s}.{n['lock_balance']}(p_org, p_item, p_wh);
    IF p_ref IS NOT NULL THEN
        SELECT * INTO v_prev FROM {mv}
            WHERE org_id = p_org AND source = p_source AND source_ref = p_ref AND kind = p_kind
              AND item_id = p_item AND warehouse_id = p_wh;
        IF FOUND THEN
            RETURN jsonb_build_object('replayed', true, 'move', to_jsonb(v_prev));
        END IF;
    END IF;
    v_on := v_bal.on_hand; v_res := v_bal.reserved; v_avg := v_bal.avg_cost_cents; v_cost := v_avg;
    IF p_kind IN ('in', 'transfer_in') OR (p_kind = 'adjust' AND p_qty > 0) THEN
        IF p_kind <> 'adjust' AND p_cost IS NULL THEN
            {_refuse('custo_invalido', 'p_item')}
        END IF;
        v_cost := COALESCE(p_cost, v_avg);
        v_avg := round((v_on * v_avg + p_qty * v_cost) / (v_on + p_qty))::bigint;
        v_on := v_on + p_qty;
    ELSIF p_kind IN ('out', 'transfer_out') THEN
        IF v_on - v_res < p_qty THEN
            {_refuse('estoque_insuficiente', 'p_item')}
        END IF;
        v_on := v_on - p_qty;
    ELSIF p_kind = 'adjust' THEN
        IF v_on + p_qty < v_res THEN
            {_refuse('abaixo_reservado', 'p_item')}
        END IF;
        v_on := v_on + p_qty;
    ELSIF p_kind = 'reserve' THEN
        IF v_on - v_res < p_qty THEN
            {_refuse('estoque_insuficiente', 'p_item')}
        END IF;
        v_res := v_res + p_qty;
    ELSIF p_kind = 'release' THEN
        IF v_res < p_qty THEN
            {_refuse('quantidade_divergente', 'p_item')}
        END IF;
        v_res := v_res - p_qty;
    ELSIF p_kind = 'commit' THEN
        IF v_res < p_qty THEN
            {_refuse('quantidade_divergente', 'p_item')}
        END IF;
        v_res := v_res - p_qty;
        v_on := v_on - p_qty;
    ELSE
        {_refuse('quantidade_invalida', 'p_item')}
    END IF;
    UPDATE {bal} SET on_hand = v_on, reserved = v_res, avg_cost_cents = v_avg, updated_at = now()
        WHERE org_id = p_org AND item_id = p_item AND warehouse_id = p_wh;
    INSERT INTO {mv} (org_id, item_id, warehouse_id, kind, qty, unit_cost_cents, source, source_ref, transfer_group, note,
                      on_hand_after, reserved_after, avg_cost_after_cents, occurred_at, created_by)
        VALUES (p_org, p_item, p_wh, p_kind, p_qty, v_cost, p_source, p_ref, p_group, p_note,
                v_on, v_res, v_avg, COALESCE(p_occurred, now()), p_user)
        RETURNING * INTO v_move;
    RETURN jsonb_build_object('replayed', false, 'move', to_jsonb(v_move));
END;""",
    )

    def single(name: str, kind: str, cost: str) -> str:
        return _secdef(
            s, n[name], "p_org UUID, p_row JSONB", "UUID, JSONB", "JSONB",
            "DECLARE v_res JSONB; v_code TEXT; v_item TEXT;",
            f"""
BEGIN
    v_res := {s}.{n['apply_move']}(
        p_org, (p_row->>'item_id')::uuid, (p_row->>'warehouse_id')::uuid, '{kind}', (p_row->>'qty')::numeric, {cost},
        COALESCE(p_row->>'source', 'manual'), NULLIF(p_row->>'source_ref', ''), (p_row->>'created_by')::uuid,
        p_row->>'note', NULL, (p_row->>'occurred_at')::timestamptz);
    RETURN jsonb_build_object('status', CASE WHEN (v_res->>'replayed')::boolean THEN 'replayed' ELSE 'ok' END,
                              'moves', jsonb_build_array(v_res->'move'));
{_handler()}
END;""",
        )

    receive = single("receive", "in", "(p_row->>'unit_cost_cents')::bigint")
    issue = single("issue", "out", "NULL")
    adjust = _secdef(
        s, n["adjust"], "p_org UUID, p_row JSONB", "UUID, JSONB", "JSONB",
        f"""
DECLARE
    v_res JSONB; v_code TEXT; v_item TEXT;
    v_item_id UUID := (p_row->>'item_id')::uuid; v_wh UUID := (p_row->>'warehouse_id')::uuid;
    v_bal {bal}%ROWTYPE; v_counted NUMERIC := (p_row->>'counted_qty')::numeric; v_delta NUMERIC;
    v_src TEXT := COALESCE(p_row->>'source', 'manual'); v_ref TEXT := NULLIF(p_row->>'source_ref', '');
    v_prev {mv}%ROWTYPE;
""",
        f"""
BEGIN
    IF v_counted IS NULL OR v_counted < 0 THEN
        {_refuse('quantidade_invalida', 'v_item_id')}
    END IF;
    v_bal := {s}.{n['lock_balance']}(p_org, v_item_id, v_wh);
    IF v_ref IS NOT NULL THEN
        SELECT * INTO v_prev FROM {mv}
            WHERE org_id = p_org AND source = v_src AND source_ref = v_ref AND kind = 'adjust'
              AND item_id = v_item_id AND warehouse_id = v_wh;
        IF FOUND THEN
            RETURN jsonb_build_object('status', 'replayed', 'moves', jsonb_build_array(to_jsonb(v_prev)));
        END IF;
    END IF;
    v_delta := v_counted - v_bal.on_hand;
    IF v_delta = 0 THEN
        RETURN jsonb_build_object('status', 'ok', 'moves', '[]'::jsonb);
    END IF;
    v_res := {s}.{n['apply_move']}(
        p_org, v_item_id, v_wh, 'adjust', v_delta, (p_row->>'unit_cost_cents')::bigint, v_src, v_ref,
        (p_row->>'created_by')::uuid, p_row->>'note', NULL, (p_row->>'occurred_at')::timestamptz);
    RETURN jsonb_build_object('status', 'ok', 'moves', jsonb_build_array(v_res->'move'));
{_handler()}
END;""",
    )
    transfer = _secdef(
        s, n["transfer"], "p_org UUID, p_row JSONB", "UUID, JSONB", "JSONB",
        """
DECLARE
    v_out JSONB; v_in JSONB; v_code TEXT; v_item TEXT;
    v_item_id UUID := (p_row->>'item_id')::uuid;
    v_from UUID := (p_row->>'from_warehouse_id')::uuid; v_to UUID := (p_row->>'to_warehouse_id')::uuid;
    v_src TEXT := COALESCE(p_row->>'source', 'manual'); v_ref TEXT := NULLIF(p_row->>'source_ref', '');
    v_qty NUMERIC := (p_row->>'qty')::numeric; v_when TIMESTAMPTZ := (p_row->>'occurred_at')::timestamptz;
    v_user UUID := (p_row->>'created_by')::uuid; v_note TEXT := p_row->>'note';
""",
        f"""
BEGIN
    IF v_from = v_to THEN
        {_refuse('transferencia_mesmo_deposito', 'v_item_id')}
    END IF;
    PERFORM {s}.{n['lock_balance']}(p_org, v_item_id, LEAST(v_from, v_to));
    PERFORM {s}.{n['lock_balance']}(p_org, v_item_id, GREATEST(v_from, v_to));
    v_out := {s}.{n['apply_move']}(p_org, v_item_id, v_from, 'transfer_out', v_qty, NULL, v_src, v_ref, v_user, v_note,
                                   gen_random_uuid(), v_when);
    v_in := {s}.{n['apply_move']}(p_org, v_item_id, v_to, 'transfer_in', v_qty, (v_out->'move'->>'unit_cost_cents')::bigint,
                                  v_src, v_ref, v_user, v_note, (v_out->'move'->>'transfer_group')::uuid, v_when);
    RETURN jsonb_build_object('status', CASE WHEN (v_out->>'replayed')::boolean THEN 'replayed' ELSE 'ok' END,
                              'moves', jsonb_build_array(v_out->'move', v_in->'move'));
{_handler()}
END;""",
    )
    reserve = _secdef(
        s, n["reserve"], "p_org UUID, p_order_ref TEXT, p_lines JSONB, p_user UUID, p_source TEXT",
        "UUID, TEXT, JSONB, UUID, TEXT", "JSONB",
        f"""
DECLARE
    r RECORD; v_res JSONB; v_code TEXT; v_item TEXT; v_moves JSONB := '[]'::jsonb; v_all_replayed BOOLEAN := true;
    v_default UUID;
""",
        f"""
BEGIN
    IF p_order_ref IS NULL OR btrim(p_order_ref) = '' OR p_lines IS NULL OR jsonb_array_length(p_lines) = 0 THEN
        {_refuse('quantidade_invalida')}
    END IF;
    SELECT id INTO v_default FROM {wh} WHERE org_id = p_org AND is_default AND active;
    FOR r IN
        SELECT (l->>'item_id')::uuid AS item_id, COALESCE((l->>'warehouse_id')::uuid, v_default) AS warehouse_id,
               sum((l->>'qty')::numeric) AS qty
        FROM jsonb_array_elements(p_lines) l GROUP BY 1, 2 ORDER BY 1, 2
    LOOP
        IF r.warehouse_id IS NULL THEN
            {_refuse('sem_deposito_padrao', 'r.item_id')}
        END IF;
        v_res := {s}.{n['apply_move']}(p_org, r.item_id, r.warehouse_id, 'reserve', r.qty, NULL, COALESCE(p_source, 'order'),
                                       p_order_ref, p_user, NULL, NULL, NULL);
        v_all_replayed := v_all_replayed AND (v_res->>'replayed')::boolean;
        v_moves := v_moves || jsonb_build_array(v_res->'move');
    END LOOP;
    RETURN jsonb_build_object('status', CASE WHEN v_all_replayed THEN 'replayed' ELSE 'ok' END, 'moves', v_moves);
{_handler()}
END;""",
    )

    def settle(name: str, kind: str, other: str, other_code: str, none_refuses: bool) -> str:
        none_branch = _refuse("sem_reserva", "v_line_item") if none_refuses else "CONTINUE;"
        return _secdef(
            s, n[name], "p_org UUID, p_order_ref TEXT, p_lines JSONB, p_user UUID, p_source TEXT",
            "UUID, TEXT, JSONB, UUID, TEXT", "JSONB",
            """
DECLARE
    r RECORD; l JSONB; v_res JSONB; v_code TEXT; v_item TEXT; v_moves JSONB := '[]'::jsonb; v_all_replayed BOOLEAN := true;
    v_any BOOLEAN := false; v_src TEXT := COALESCE(p_source, 'order'); v_reserved NUMERIC; v_line_item UUID;
    v_filter BOOLEAN := p_lines IS NOT NULL AND jsonb_array_length(p_lines) > 0;
""",
            f"""
BEGIN
    IF p_order_ref IS NULL OR btrim(p_order_ref) = '' THEN
        {_refuse('quantidade_invalida')}
    END IF;
    IF v_filter THEN
        FOR l IN SELECT * FROM jsonb_array_elements(p_lines) LOOP
            v_line_item := (l->>'item_id')::uuid;
            SELECT sum(qty) INTO v_reserved FROM {mv}
                WHERE org_id = p_org AND source = v_src AND source_ref = p_order_ref AND kind = 'reserve' AND item_id = v_line_item;
            IF v_reserved IS NULL THEN
                {none_branch}
            ELSIF l->>'qty' IS NOT NULL AND (l->>'qty')::numeric <> v_reserved THEN
                {_refuse('quantidade_divergente', 'v_line_item')}
            END IF;
        END LOOP;
    END IF;
    FOR r IN
        SELECT m.item_id, m.warehouse_id, m.qty FROM {mv} m
        WHERE m.org_id = p_org AND m.source = v_src AND m.source_ref = p_order_ref AND m.kind = 'reserve'
          AND (NOT v_filter OR m.item_id IN (SELECT (x->>'item_id')::uuid FROM jsonb_array_elements(p_lines) x))
        ORDER BY m.item_id, m.warehouse_id
    LOOP
        v_any := true;
        IF NOT EXISTS (SELECT 1 FROM {mv} WHERE org_id = p_org AND source = v_src AND source_ref = p_order_ref
                       AND kind = '{kind}' AND item_id = r.item_id AND warehouse_id = r.warehouse_id)
           AND EXISTS (SELECT 1 FROM {mv} WHERE org_id = p_org AND source = v_src AND source_ref = p_order_ref
                       AND kind = '{other}' AND item_id = r.item_id AND warehouse_id = r.warehouse_id) THEN
            {_refuse(other_code, 'r.item_id')}
        END IF;
        v_res := {s}.{n['apply_move']}(p_org, r.item_id, r.warehouse_id, '{kind}', r.qty, NULL, v_src, p_order_ref, p_user,
                                       NULL, NULL, NULL);
        v_all_replayed := v_all_replayed AND (v_res->>'replayed')::boolean;
        v_moves := v_moves || jsonb_build_array(v_res->'move');
    END LOOP;
    IF NOT v_any THEN
        {_refuse('sem_reserva') if none_refuses else "RETURN jsonb_build_object('status', 'ok', 'moves', '[]'::jsonb);"}
    END IF;
    RETURN jsonb_build_object('status', CASE WHEN v_all_replayed THEN 'replayed' ELSE 'ok' END, 'moves', v_moves);
{_handler()}
END;""",
        )

    commit = settle("commit", "commit", "release", "reserva_liberada", True)
    release = settle("release", "release", "commit", "reserva_consumida", False)
    parts = [
        "-- Row-locked stock mutations: lock the balance, write the kardex move AND the balance in ONE transaction.",
        lock_balance, apply_move, receive, issue, adjust, transfer, reserve, commit, release,
    ]
    return "\n\n".join(parts)


def inventory_migration(cfg: InventoryConfig, schema: str) -> str:
    """The whole inventory DDL for `schema`, as one re-runnable migration body."""
    if not schema or not schema.strip():
        raise ValueError("inventory_migration requires a non-empty schema")
    if schema != cfg.schema:
        raise ValueError(f"inventory_migration schema {schema!r} must equal cfg.schema {cfg.schema!r}")
    sections = [
        "-- Inventory organ -- generated by noctusai_lib.domain.inventory.sql (do not hand-edit)",
        f"SET search_path = {schema}, public;",
        *_tables(cfg, schema),
        _rpcs(cfg, schema),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = [
    "APPEND_ONLY_SQLSTATE",
    "APPEND_ONLY_TABLES",
    "INVENTORY_TABLES",
    "REFUSAL_SQLSTATE",
    "RPC_NAMES",
    "inventory_migration",
]
