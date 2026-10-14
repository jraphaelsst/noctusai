"""`purchasing_migration(cfg, schema)` -- the purchasing DDL + row-locked RPCs for a product's schema.

Same conventions as `inventory_migration`: `org_id UUID NOT NULL` on every table, RLS enabled with an `authenticated`
own-org SELECT policy and the literal `service_role_bypass`; the backend writes through the service-role client.
Forward-only and idempotent (the chain replay applies it twice). Money is integer cents; quantities `numeric(18,3)`.

Why the writes are RPCs: PostgREST has no multi-statement transaction. Saving an order replaces its lines, and
receiving checks "received so far" before adding -- from Python two concurrent receipts of the last unit would both
pass. Each RPC takes `SELECT ... FOR UPDATE` on the ORDER row, so the second caller waits and sees the first one's rows.
RPCs return jsonb `{"status": "ok"|"replayed"|"refused", "code"?}`; a refusal rolls ALL of that call's work back
(a plpgsql exception block is a savepoint) and is reported as data.

Landed cost (the proration, computed here under the lock, authority for the stock cost AND the AP amount):
    A      = freight + other - discount                          (order-level adjustment, may be negative)
    G      = order goods total  (sum of round(qty*unit_cost))
    R      = round(A * G_after / G) - round(A * G_before / G)    (this receipt's share; G_before = goods already
                                                                   received at ORDER prices, G_after = G_before + this)
    line_i = round(R * cum_goods_i / receipt_goods) - round(R * cum_goods_{i-1} / receipt_goods)
    landed_unit_i = max(0, round((goods_i + line_i) / qty_i))
Every share telescopes, so the receipts of an order add up to EXACTLY A (no cent is lost or invented, however the
quantities are split across receipts); rounding is half-away-from-zero. The AP amount of a receipt is
goods + R; the stock cost per line is `landed_unit_i` (<= qty_i/2 cents of rounding noise per line, the unavoidable
price of an integer-cent unit cost).

Prerequisites (not created here): `public.current_org_id_for(text)` (core 070) and, per `cfg.with_*`, the parties /
items / inventory organs' tables in the same schema.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import rls_subquery_policy, service_role_bypass

from .config import PurchasingConfig
from .types import OrderStatus, values

#: Every organ table (unprefixed), in dependency order. The generator and isolation tests iterate this.
PURCHASING_TABLES: tuple[str, ...] = ("settings", "approvers", "settings_log", "counters", "orders", "order_lines", "receipts", "receipt_lines")

RPC_NAMES: tuple[str, ...] = ("save_order", "transition", "receive", "set_threshold", "set_approver")

#: After a threshold change, approvals of orders above the LOWEST threshold in force in the window are refused.
APPROVAL_COOLDOWN_MINUTES = 10

_BIGINT_MAX = "9223372036854775807"

#: SQLSTATE carrying a business refusal out of a nested block.
REFUSAL_SQLSTATE = "PU001"


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
            f"GRANT SELECT ON {schema}.{table} TO authenticated;",
            f"GRANT ALL ON {schema}.{table} TO service_role;",
        ]
    )


def _tables(cfg: PurchasingConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    t = {name: cfg.table(name) for name in PURCHASING_TABLES}
    party_fk = (
        f",\n    FOREIGN KEY (party_id, org_id) REFERENCES {s}.{cfg.parties_table}(id, org_id) ON DELETE RESTRICT"
        if cfg.with_parties else ""
    )
    wh_ref = f" REFERENCES {s}.{cfg.warehouses_table}(id) ON DELETE RESTRICT" if cfg.with_inventory else ""
    item_ref = f" REFERENCES {s}.{cfg.items_table}(id) ON DELETE RESTRICT" if cfg.with_items else ""
    sections = [
        (
            "Org settings: the approval threshold. NULL = no threshold (an approver may approve any value). "
            "`previous_threshold_cents` / `threshold_changed_at` drive the post-change approval cooldown "
            "(written ONLY by the set_threshold RPC).",
            "settings",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['settings']} (
    org_id                  UUID PRIMARY KEY,
    approval_threshold_cents BIGINT CHECK (approval_threshold_cents IS NULL OR approval_threshold_cents >= 0),
    previous_threshold_cents BIGINT CHECK (previous_threshold_cents IS NULL OR previous_threshold_cents >= 0),
    threshold_changed_at    TIMESTAMPTZ,
    updated_by              UUID,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE {s}.{t['settings']} ADD COLUMN IF NOT EXISTS previous_threshold_cents BIGINT;
ALTER TABLE {s}.{t['settings']} ADD COLUMN IF NOT EXISTS threshold_changed_at TIMESTAMPTZ;
""",
        ),
        (
            "Approvers of THIS org (org-scoped: a grant here never reaches another org). Managed by org admins through "
            "the set_approver RPC; `can_approve` is membership in this table for the selected org.",
            "approvers",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['approvers']} (
    org_id      UUID NOT NULL,
    user_id     UUID NOT NULL,
    granted_by  UUID,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);
""",
        ),
        (
            "Append-only audit of approval-governing changes (threshold changes, approver grants / revocations). "
            "UPDATE / DELETE / TRUNCATE are refused by trigger.",
            "settings_log",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['settings_log']} (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('threshold', 'approver_added', 'approver_removed')),
    actor_id        UUID,
    subject_user_id UUID,
    old_cents       BIGINT,
    new_cents       BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{t['settings_log']}_org ON {s}.{t['settings_log']} (org_id, created_at);
CREATE OR REPLACE FUNCTION {s}.{t['settings_log']}_append_only() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION '{t['settings_log']} is append-only' USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS {t['settings_log']}_no_update ON {s}.{t['settings_log']};
CREATE TRIGGER {t['settings_log']}_no_update BEFORE UPDATE OR DELETE ON {s}.{t['settings_log']}
    FOR EACH ROW EXECUTE FUNCTION {s}.{t['settings_log']}_append_only();
DROP TRIGGER IF EXISTS {t['settings_log']}_no_truncate ON {s}.{t['settings_log']};
CREATE TRIGGER {t['settings_log']}_no_truncate BEFORE TRUNCATE ON {s}.{t['settings_log']}
    FOR EACH STATEMENT EXECUTE FUNCTION {s}.{t['settings_log']}_append_only();
""",
        ),
        (
            "Per-org sequential order numbers (the counter row is updated inside the save RPC, so a refused save burns no number).",
            "counters",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['counters']} (
    org_id       UUID PRIMARY KEY,
    last_number  INTEGER NOT NULL DEFAULT 0 CHECK (last_number >= 0)
);
""",
        ),
        (
            "Purchase orders. `supplier_name` is the snapshot shown/booked; `party_id` links the parties organ. "
            "Totals are computed by the save RPC: total = goods + freight + other - discount.",
            "orders",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['orders']} (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    number            INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ({_in(OrderStatus)})),
    party_id          UUID,
    supplier_name     TEXT NOT NULL CHECK (btrim(supplier_name) <> ''),
    warehouse_id      UUID{wh_ref},
    expected_date     DATE,
    installments_count INTEGER NOT NULL DEFAULT 1 CHECK (installments_count BETWEEN 1 AND 120),
    first_due_days    INTEGER NOT NULL DEFAULT 30 CHECK (first_due_days >= 0),
    interval_days     INTEGER NOT NULL DEFAULT 30 CHECK (interval_days >= 0),
    freight_cents     BIGINT NOT NULL DEFAULT 0 CHECK (freight_cents >= 0),
    discount_cents    BIGINT NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    other_cents       BIGINT NOT NULL DEFAULT 0 CHECK (other_cents >= 0),
    goods_cents       BIGINT NOT NULL DEFAULT 0 CHECK (goods_cents >= 0),
    total_cents       BIGINT NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    notes             TEXT,
    approved_by       UUID,
    approved_at       TIMESTAMPTZ,
    sent_at           TIMESTAMPTZ,
    cancelled_at      TIMESTAMPTZ,
    cancelled_by      UUID,
    cancel_reason     TEXT,
    created_by        UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, org_id),
    UNIQUE (org_id, number),
    CHECK (status <> 'approved' OR approved_at IS NOT NULL){party_fk}
);
CREATE INDEX IF NOT EXISTS idx_{t['orders']}_org_status ON {s}.{t['orders']} (org_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_{t['orders']}_party ON {s}.{t['orders']} (org_id, party_id) WHERE party_id IS NOT NULL;
""",
        ),
        (
            "Order lines. `received_qty` is maintained by the receive RPC (never above `qty`).",
            "order_lines",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['order_lines']} (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    order_id         UUID NOT NULL,
    line_no          INTEGER NOT NULL CHECK (line_no >= 1),
    item_id          UUID{item_ref},
    description      TEXT NOT NULL CHECK (btrim(description) <> ''),
    unit             TEXT,
    qty              NUMERIC(18,3) NOT NULL CHECK (qty > 0),
    unit_cost_cents  BIGINT NOT NULL CHECK (unit_cost_cents >= 0),
    line_total_cents BIGINT NOT NULL CHECK (line_total_cents >= 0),
    received_qty     NUMERIC(18,3) NOT NULL DEFAULT 0,
    UNIQUE (id, org_id),
    UNIQUE (order_id, line_no),
    CONSTRAINT {t['order_lines']}_received_bounds CHECK (received_qty >= 0 AND received_qty <= qty),
    FOREIGN KEY (order_id, org_id) REFERENCES {s}.{t['orders']}(id, org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_{t['order_lines']}_item ON {s}.{t['order_lines']} (org_id, item_id) WHERE item_id IS NOT NULL;
""",
        ),
        (
            "Receipts (partial receipts allowed). Amounts are the landed cost computed by the receive RPC (see module "
            "docstring); `stock_posted_at` / `finance_posted_at` mark the two idempotent posting legs. "
            "`idempotency_key` makes a retried POST a replay.",
            "receipts",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['receipts']} (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    order_id               UUID NOT NULL,
    receipt_no             INTEGER NOT NULL CHECK (receipt_no >= 1),
    received_on            DATE NOT NULL,
    note                   TEXT,
    goods_cents            BIGINT NOT NULL CHECK (goods_cents >= 0),
    adjustment_cents       BIGINT NOT NULL,
    total_cents            BIGINT NOT NULL CHECK (total_cents >= 0),
    order_goods_before_cents BIGINT NOT NULL CHECK (order_goods_before_cents >= 0),
    idempotency_key        TEXT CHECK (idempotency_key IS NULL OR btrim(idempotency_key) <> ''),
    stock_posted_at        TIMESTAMPTZ,
    finance_posted_at      TIMESTAMPTZ,
    posting_error          TEXT,
    created_by             UUID,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, org_id),
    UNIQUE (order_id, receipt_no),
    FOREIGN KEY (order_id, org_id) REFERENCES {s}.{t['orders']}(id, org_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['receipts']}_idem ON {s}.{t['receipts']} (org_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['receipts']}_org_date ON {s}.{t['receipts']} (org_id, received_on);
""",
        ),
        (
            "Receipt lines: the quantity received against an order line, its goods value and its prorated share of "
            "freight/other/discount; `landed_unit_cost_cents` is what the stock move is booked at.",
            "receipt_lines",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['receipt_lines']} (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    receipt_id              UUID NOT NULL,
    order_line_id           UUID NOT NULL,
    qty                     NUMERIC(18,3) NOT NULL CHECK (qty > 0),
    unit_cost_cents         BIGINT NOT NULL CHECK (unit_cost_cents >= 0),
    goods_cents             BIGINT NOT NULL CHECK (goods_cents >= 0),
    adjustment_cents        BIGINT NOT NULL,
    landed_unit_cost_cents  BIGINT NOT NULL CHECK (landed_unit_cost_cents >= 0),
    UNIQUE (receipt_id, order_line_id),
    FOREIGN KEY (receipt_id, org_id) REFERENCES {s}.{t['receipts']}(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (order_line_id, org_id) REFERENCES {s}.{t['order_lines']}(id, org_id) ON DELETE RESTRICT
);
""",
        ),
    ]
    out: list[str] = []
    for title, name, body in sections:
        out.append(f"-- {title}\n{body.strip()}\n{_org_rls(s, t[name], o)}")
    return out


def _refuse(code: str, detail: str = "NULL") -> str:
    extra = f", DETAIL = {detail}::text" if detail != "NULL" else ""
    return f"RAISE EXCEPTION USING ERRCODE = '{REFUSAL_SQLSTATE}', MESSAGE = '{code}'{extra};"


def _handler() -> str:
    return f"""EXCEPTION WHEN SQLSTATE '{REFUSAL_SQLSTATE}' THEN
    GET STACKED DIAGNOSTICS v_code = MESSAGE_TEXT, v_detail = PG_EXCEPTION_DETAIL;
    RETURN jsonb_build_object('status', 'refused', 'code', v_code, 'order_line_id', NULLIF(v_detail, ''));"""


def _secdef(s: str, name: str, args: str, sig: str, declare: str, body: str) -> str:
    return f"""CREATE OR REPLACE FUNCTION {s}.{name}({args}) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, {s}, pg_temp
AS $fn$
{declare.strip()}
{body.strip()}
$fn$;
REVOKE ALL ON FUNCTION {s}.{name}({sig}) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {s}.{name}({sig}) TO service_role;"""


def _rpcs(cfg: PurchasingConfig, s: str) -> str:
    t = {name: cfg.table(name) for name in PURCHASING_TABLES}
    orders, lines, receipts, rlines, counters = (f"{s}.{t[k]}" for k in ("orders", "order_lines", "receipts", "receipt_lines", "counters"))
    settings_t, approvers_t, log_t = (f"{s}.{t[k]}" for k in ("settings", "approvers", "settings_log"))
    n = {name: cfg.rpc(name) for name in RPC_NAMES}

    party_check = (
        f"""    IF v_party IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {s}.{cfg.parties_table} WHERE id = v_party AND org_id = p_org) THEN
        {_refuse('fornecedor_invalido')}
    END IF;
"""
        if cfg.with_parties
        else "    v_party := NULL;\n"
    )
    wh_check = (
        f"""    IF v_wh IS NULL THEN
        {_refuse('deposito_invalido')}
    END IF;
    IF NOT EXISTS (SELECT 1 FROM {s}.{cfg.warehouses_table} WHERE id = v_wh AND org_id = p_org) THEN
        {_refuse('deposito_invalido')}
    END IF;
"""
        if cfg.with_inventory
        else "    v_wh := NULL;\n"
    )
    item_required = (
        f"""        IF v_item IS NULL THEN
            {_refuse('item_obrigatorio')}
        END IF;
"""
        if cfg.with_inventory
        else ""
    )
    item_exists = (
        f"""        IF v_item IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {s}.{cfg.items_table} WHERE id = v_item AND org_id = p_org) THEN
            {_refuse('item_invalido')}
        END IF;
"""
        if cfg.with_items
        else "        v_item := NULL;\n"
    )

    save_order = _secdef(
        s, n["save_order"], "p_org UUID, p_order_id UUID, p_row JSONB", "UUID, UUID, JSONB",
        f"""
DECLARE
    v_code TEXT; v_detail TEXT;
    v_order {orders}%ROWTYPE; v_id UUID; v_num INTEGER;
    v_party UUID := NULLIF(p_row->>'party_id', '')::uuid; v_wh UUID := NULLIF(p_row->>'warehouse_id', '')::uuid;
    v_name TEXT := btrim(COALESCE(p_row->>'supplier_name', ''));
    v_freight BIGINT := COALESCE((p_row->>'freight_cents')::bigint, 0);
    v_discount BIGINT := COALESCE((p_row->>'discount_cents')::bigint, 0);
    v_other BIGINT := COALESCE((p_row->>'other_cents')::bigint, 0);
    v_inst INTEGER := COALESCE((p_row->>'installments_count')::integer, 1);
    v_first INTEGER := COALESCE((p_row->>'first_due_days')::integer, 30);
    v_interval INTEGER := COALESCE((p_row->>'interval_days')::integer, 30);
    l JSONB; v_item UUID; v_qty NUMERIC; v_cost BIGINT; v_desc TEXT; v_total BIGINT; v_goods BIGINT := 0; v_no INTEGER := 0;
""",
        f"""
BEGIN
    IF v_freight < 0 OR v_discount < 0 OR v_other < 0 THEN
        {_refuse('valor_invalido')}
    END IF;
    IF v_inst < 1 OR v_inst > 120 THEN
        {_refuse('parcelas_invalidas')}
    END IF;
    IF v_first < 0 OR v_interval < 0 OR (v_inst > 1 AND v_interval < 1) THEN
        {_refuse('prazo_invalido')}
    END IF;
    IF v_name = '' THEN
        {_refuse('fornecedor_invalido')}
    END IF;
    IF p_row->'lines' IS NULL OR jsonb_typeof(p_row->'lines') <> 'array' OR jsonb_array_length(p_row->'lines') = 0 THEN
        {_refuse('sem_linhas')}
    END IF;
{party_check}{wh_check}    IF p_order_id IS NULL THEN
        INSERT INTO {counters} (org_id, last_number) VALUES (p_org, 1)
            ON CONFLICT (org_id) DO UPDATE SET last_number = {counters}.last_number + 1
            RETURNING last_number INTO v_num;
        INSERT INTO {orders} (org_id, number, status, supplier_name, created_by)
            VALUES (p_org, v_num, 'draft', v_name, NULLIF(p_row->>'created_by', '')::uuid) RETURNING id INTO v_id;
    ELSE
        SELECT * INTO v_order FROM {orders} WHERE id = p_order_id AND org_id = p_org FOR UPDATE;
        IF NOT FOUND THEN
            {_refuse('pedido_inexistente')}
        END IF;
        IF v_order.status <> 'draft' THEN
            {_refuse('pedido_nao_editavel')}
        END IF;
        v_id := v_order.id;
        DELETE FROM {lines} WHERE order_id = v_id AND org_id = p_org;
    END IF;
    FOR l IN SELECT * FROM jsonb_array_elements(p_row->'lines') LOOP
        v_no := v_no + 1;
        v_item := NULLIF(l->>'item_id', '')::uuid;
        v_qty := (l->>'qty')::numeric;
        v_cost := (l->>'unit_cost_cents')::bigint;
        v_desc := btrim(COALESCE(l->>'description', ''));
        IF v_qty IS NULL OR v_qty <= 0 THEN
            {_refuse('quantidade_invalida')}
        END IF;
        IF v_cost IS NULL OR v_cost < 0 OR v_desc = '' THEN
            {_refuse('linha_invalida')}
        END IF;
{item_required}{item_exists}        v_total := round(v_qty * v_cost)::bigint;
        v_goods := v_goods + v_total;
        INSERT INTO {lines} (org_id, order_id, line_no, item_id, description, unit, qty, unit_cost_cents, line_total_cents)
            VALUES (p_org, v_id, v_no, v_item, v_desc, NULLIF(l->>'unit', ''), v_qty, v_cost, v_total);
    END LOOP;
    IF v_goods <= 0 THEN
        {_refuse('pedido_sem_valor')}
    END IF;
    IF v_goods + v_freight + v_other - v_discount < 0 THEN
        {_refuse('desconto_excede')}
    END IF;
    UPDATE {orders} SET party_id = v_party, supplier_name = v_name, warehouse_id = v_wh,
        expected_date = NULLIF(p_row->>'expected_date', '')::date, installments_count = v_inst,
        first_due_days = v_first, interval_days = v_interval, freight_cents = v_freight, discount_cents = v_discount,
        other_cents = v_other, goods_cents = v_goods, total_cents = v_goods + v_freight + v_other - v_discount,
        notes = NULLIF(btrim(COALESCE(p_row->>'notes', '')), ''), updated_at = now()
        WHERE id = v_id AND org_id = p_org;
    RETURN jsonb_build_object('status', 'ok', 'order_id', v_id);
{_handler()}
END;""",
    )

    transition = _secdef(
        s, n["transition"],
        "p_org UUID, p_order_id UUID, p_action TEXT, p_user UUID, p_reason TEXT, p_actor_can_exceed BOOLEAN DEFAULT false",
        "UUID, UUID, TEXT, UUID, TEXT, BOOLEAN",
        f"""
DECLARE
    v_code TEXT; v_detail TEXT; v_order {orders}%ROWTYPE; v_target TEXT; v_from TEXT[];
    v_thr BIGINT; v_prev BIGINT; v_chg TIMESTAMPTZ; v_low BIGINT;
""",
        f"""
BEGIN
    SELECT * INTO v_order FROM {orders} WHERE id = p_order_id AND org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        {_refuse('pedido_inexistente')}
    END IF;
    IF p_action = 'approve' THEN v_target := 'approved'; v_from := ARRAY['draft'];
    ELSIF p_action = 'send' THEN v_target := 'sent'; v_from := ARRAY['approved'];
    ELSIF p_action = 'cancel' THEN v_target := 'cancelled'; v_from := ARRAY['draft', 'approved', 'sent'];
    ELSE
        {_refuse('transicao_invalida')}
    END IF;
    IF v_order.status = v_target THEN
        RETURN jsonb_build_object('status', 'replayed', 'order_id', v_order.id);
    END IF;
    IF p_action = 'cancel' AND EXISTS (SELECT 1 FROM {receipts} WHERE order_id = v_order.id AND org_id = p_org) THEN
        {_refuse('pedido_com_recebimento')}
    END IF;
    IF NOT (v_order.status = ANY (v_from)) THEN
        {_refuse('transicao_invalida')}
    END IF;
    IF p_action = 'approve' THEN
        -- The limit is judged HERE, under the order's row lock, against the order's CURRENT total (a concurrent PUT that
        -- raised it has either committed before this lock was taken or waits for it); the threshold row is share-locked
        -- so a concurrent threshold change cannot slip between the read and the write.
        SELECT approval_threshold_cents, previous_threshold_cents, threshold_changed_at INTO v_thr, v_prev, v_chg
            FROM {settings_t} WHERE org_id = p_org FOR SHARE;
        IF FOUND THEN
            IF v_thr IS NOT NULL AND v_order.total_cents > v_thr AND NOT COALESCE(p_actor_can_exceed, false) THEN
                {_refuse('aprovacao_acima_do_limite')}
            END IF;
            IF v_chg IS NOT NULL AND v_chg > now() - interval '{APPROVAL_COOLDOWN_MINUTES} minutes' THEN
                v_low := LEAST(COALESCE(v_thr, {_BIGINT_MAX}), COALESCE(v_prev, {_BIGINT_MAX}));
                IF v_order.total_cents > v_low THEN
                    {_refuse('limite_em_carencia')}
                END IF;
            END IF;
        END IF;
        UPDATE {orders} SET status = 'approved', approved_by = p_user, approved_at = now(), updated_at = now() WHERE id = v_order.id;
    ELSIF p_action = 'send' THEN
        UPDATE {orders} SET status = 'sent', sent_at = now(), updated_at = now() WHERE id = v_order.id;
    ELSE
        UPDATE {orders} SET status = 'cancelled', cancelled_at = now(), cancelled_by = p_user,
            cancel_reason = NULLIF(btrim(COALESCE(p_reason, '')), ''), updated_at = now() WHERE id = v_order.id;
    END IF;
    RETURN jsonb_build_object('status', 'ok', 'order_id', v_order.id);
{_handler()}
END;""",
    )

    receive = _secdef(
        s, n["receive"], "p_org UUID, p_order_id UUID, p_row JSONB", "UUID, UUID, JSONB",
        f"""
DECLARE
    v_code TEXT; v_detail TEXT;
    v_order {orders}%ROWTYPE; v_prev {receipts}%ROWTYPE; v_ol {lines}%ROWTYPE; v_rid UUID := gen_random_uuid();
    v_key TEXT := NULLIF(btrim(COALESCE(p_row->>'idempotency_key', '')), '');
    l RECORD;
    v_before BIGINT; v_a BIGINT; v_g BIGINT; v_rgoods BIGINT := 0; v_radj BIGINT; v_no INTEGER;
    v_cum BIGINT := 0; v_prev_share BIGINT := 0; v_share BIGINT; v_adj BIGINT; v_goods BIGINT; v_landed BIGINT;
    v_open INTEGER; v_status TEXT;
""",
        f"""
BEGIN
    SELECT * INTO v_order FROM {orders} WHERE id = p_order_id AND org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        {_refuse('pedido_inexistente')}
    END IF;
    IF v_key IS NOT NULL THEN
        SELECT * INTO v_prev FROM {receipts} WHERE org_id = p_org AND idempotency_key = v_key;
        IF FOUND THEN
            IF v_prev.order_id <> v_order.id THEN
                {_refuse('chave_reutilizada')}
            END IF;
            RETURN jsonb_build_object('status', 'replayed', 'receipt_id', v_prev.id, 'order_status', v_order.status);
        END IF;
    END IF;
    IF v_order.status = 'received' THEN {_refuse('pedido_ja_recebido')}
    ELSIF v_order.status = 'cancelled' THEN {_refuse('pedido_cancelado')}
    ELSIF v_order.status = 'draft' THEN {_refuse('pedido_nao_aprovado')}
    ELSIF v_order.status NOT IN ('approved', 'sent', 'partially_received') THEN {_refuse('pedido_nao_recebivel')}
    END IF;
    IF p_row->'lines' IS NULL OR jsonb_typeof(p_row->'lines') <> 'array' OR jsonb_array_length(p_row->'lines') = 0 THEN
        {_refuse('sem_linhas')}
    END IF;
    SELECT COALESCE(SUM(rl.goods_cents), 0) INTO v_before FROM {rlines} rl
        JOIN {receipts} r ON r.id = rl.receipt_id AND r.org_id = rl.org_id WHERE r.order_id = v_order.id AND r.org_id = p_org;
    SELECT COALESCE(MAX(receipt_no), 0) + 1 INTO v_no FROM {receipts} WHERE order_id = v_order.id;
    v_a := v_order.freight_cents + v_order.other_cents - v_order.discount_cents;
    v_g := v_order.goods_cents;
    -- First pass: validate + total this receipt's goods (grouped by order line) under the lock.
    FOR l IN
        SELECT (x->>'order_line_id')::uuid AS order_line_id, sum((x->>'qty')::numeric) AS qty
        FROM jsonb_array_elements(p_row->'lines') x GROUP BY 1
    LOOP
        SELECT * INTO v_ol FROM {lines} WHERE id = l.order_line_id AND order_id = v_order.id AND org_id = p_org FOR UPDATE;
        IF NOT FOUND THEN
            {_refuse('linha_invalida', 'l.order_line_id')}
        END IF;
        IF l.qty IS NULL OR l.qty <= 0 THEN
            {_refuse('quantidade_invalida', 'l.order_line_id')}
        END IF;
        IF v_ol.received_qty + l.qty > v_ol.qty THEN
            {_refuse('recebimento_excede_pedido', 'l.order_line_id')}
        END IF;
        v_rgoods := v_rgoods + round(l.qty * v_ol.unit_cost_cents)::bigint;
    END LOOP;
    v_radj := round((v_a * (v_before + v_rgoods))::numeric / v_g)::bigint - round((v_a * v_before)::numeric / v_g)::bigint;
    INSERT INTO {receipts} (id, org_id, order_id, receipt_no, received_on, note, goods_cents, adjustment_cents, total_cents,
                            order_goods_before_cents, idempotency_key, created_by)
        VALUES (v_rid, p_org, v_order.id, v_no, COALESCE(NULLIF(p_row->>'received_on', '')::date, CURRENT_DATE),
                NULLIF(btrim(COALESCE(p_row->>'note', '')), ''), v_rgoods, v_radj, v_rgoods + v_radj, v_before, v_key,
                NULLIF(p_row->>'created_by', '')::uuid);
    -- Second pass: per-line landed cost by cumulative proration (telescopes to exactly v_radj).
    FOR l IN
        SELECT (x->>'order_line_id')::uuid AS order_line_id, sum((x->>'qty')::numeric) AS qty, ol.line_no
        FROM jsonb_array_elements(p_row->'lines') x JOIN {lines} ol ON ol.id = (x->>'order_line_id')::uuid
        GROUP BY 1, ol.line_no ORDER BY ol.line_no
    LOOP
        SELECT * INTO v_ol FROM {lines} WHERE id = l.order_line_id;
        v_goods := round(l.qty * v_ol.unit_cost_cents)::bigint;
        v_cum := v_cum + v_goods;
        v_share := CASE WHEN v_rgoods = 0 THEN 0 ELSE round((v_radj * v_cum)::numeric / v_rgoods)::bigint END;
        v_adj := v_share - v_prev_share;
        v_prev_share := v_share;
        v_landed := GREATEST(0, round((v_goods + v_adj)::numeric / l.qty)::bigint);
        INSERT INTO {rlines} (org_id, receipt_id, order_line_id, qty, unit_cost_cents, goods_cents, adjustment_cents, landed_unit_cost_cents)
            VALUES (p_org, v_rid, l.order_line_id, l.qty, v_ol.unit_cost_cents, v_goods, v_adj, v_landed);
        UPDATE {lines} SET received_qty = received_qty + l.qty WHERE id = l.order_line_id;
    END LOOP;
    SELECT count(*) INTO v_open FROM {lines} WHERE order_id = v_order.id AND received_qty < qty;
    v_status := CASE WHEN v_open = 0 THEN 'received' ELSE 'partially_received' END;
    UPDATE {orders} SET status = v_status, updated_at = now() WHERE id = v_order.id;
    RETURN jsonb_build_object('status', 'ok', 'receipt_id', v_rid, 'order_status', v_status);
{_handler()}
END;""",
    )
    max_ = _BIGINT_MAX
    set_threshold = _secdef(
        s, n["set_threshold"], "p_org UUID, p_user UUID, p_cents BIGINT", "UUID, UUID, BIGINT",
        f"""
DECLARE
    v_code TEXT; v_detail TEXT; v_row {settings_t}%ROWTYPE; v_prev BIGINT;
""",
        f"""
BEGIN
    IF p_cents IS NOT NULL AND p_cents < 0 THEN
        {_refuse('valor_invalido')}
    END IF;
    INSERT INTO {settings_t} (org_id) VALUES (p_org) ON CONFLICT (org_id) DO NOTHING;
    SELECT * INTO v_row FROM {settings_t} WHERE org_id = p_org FOR UPDATE;
    IF v_row.approval_threshold_cents IS NOT DISTINCT FROM p_cents THEN
        RETURN jsonb_build_object('status', 'replayed');
    END IF;
    IF v_row.threshold_changed_at IS NOT NULL AND v_row.threshold_changed_at > now() - interval '{APPROVAL_COOLDOWN_MINUTES} minutes' THEN
        v_prev := NULLIF(LEAST(COALESCE(v_row.previous_threshold_cents, {max_}), COALESCE(v_row.approval_threshold_cents, {max_})), {max_});
    ELSE
        v_prev := v_row.approval_threshold_cents;
    END IF;
    UPDATE {settings_t} SET approval_threshold_cents = p_cents, previous_threshold_cents = v_prev,
        threshold_changed_at = now(), updated_by = p_user, updated_at = now() WHERE org_id = p_org;
    INSERT INTO {log_t} (org_id, kind, actor_id, old_cents, new_cents)
        VALUES (p_org, 'threshold', p_user, v_row.approval_threshold_cents, p_cents);
    RETURN jsonb_build_object('status', 'ok');
{_handler()}
END;""",
    )

    set_approver = _secdef(
        s, n["set_approver"], "p_org UUID, p_actor UUID, p_user UUID, p_grant BOOLEAN", "UUID, UUID, UUID, BOOLEAN",
        """
DECLARE
    v_code TEXT; v_detail TEXT; v_n INTEGER;
""",
        f"""
BEGIN
    IF p_user IS NULL THEN
        {_refuse('usuario_invalido')}
    END IF;
    IF COALESCE(p_grant, false) THEN
        INSERT INTO {approvers_t} (org_id, user_id, granted_by) VALUES (p_org, p_user, p_actor) ON CONFLICT (org_id, user_id) DO NOTHING;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        IF v_n = 0 THEN
            RETURN jsonb_build_object('status', 'replayed');
        END IF;
        INSERT INTO {log_t} (org_id, kind, actor_id, subject_user_id) VALUES (p_org, 'approver_added', p_actor, p_user);
    ELSE
        DELETE FROM {approvers_t} WHERE org_id = p_org AND user_id = p_user;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        IF v_n = 0 THEN
            RETURN jsonb_build_object('status', 'replayed');
        END IF;
        INSERT INTO {log_t} (org_id, kind, actor_id, subject_user_id) VALUES (p_org, 'approver_removed', p_actor, p_user);
    END IF;
    RETURN jsonb_build_object('status', 'ok');
{_handler()}
END;""",
    )
    # The pre-cooldown 5-argument `transition` would stay callable beside the new one (CREATE OR REPLACE with another
    # signature adds an OVERLOAD) and approve with no limit check: drop it so only the guarded function exists.
    drop_legacy = f"DROP FUNCTION IF EXISTS {s}.{n['transition']}(UUID, UUID, TEXT, UUID, TEXT);"
    return "\n\n".join(
        ["-- Row-locked purchasing writes: lock the ORDER, then write everything in ONE transaction.", drop_legacy, save_order, transition, receive, set_threshold, set_approver]
    )


def purchasing_migration(cfg: PurchasingConfig, schema: str) -> str:
    """The whole purchasing DDL for `schema`, as one re-runnable migration body."""
    if not schema or not schema.strip():
        raise ValueError("purchasing_migration requires a non-empty schema")
    if schema != cfg.schema:
        raise ValueError(f"purchasing_migration schema {schema!r} must equal cfg.schema {cfg.schema!r}")
    sections = [
        "-- Purchasing organ -- generated by noctusai_lib.domain.purchasing.sql (do not hand-edit)",
        f"SET search_path = {schema}, public;",
        *_tables(cfg, schema),
        _rpcs(cfg, schema),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["APPROVAL_COOLDOWN_MINUTES", "PURCHASING_TABLES", "REFUSAL_SQLSTATE", "RPC_NAMES", "purchasing_migration"]
