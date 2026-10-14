"""`quotes_migration(cfg, schema)` -- the quotes DDL for a product's schema.

Same conventions as `inventory_migration` / `parties_migration`: `org_id UUID NOT NULL` on every table, RLS enabled
with an `authenticated` own-org SELECT policy and the literal `service_role_bypass`; the backend writes through
the service-role client. Forward-only and idempotent (the chain replay applies a new file twice).

What the DATABASE (not the application) guarantees:

* a quote revision chain is `(org, root_id, version)`: exactly one `is_current` per root, at most ONE `accepted`
  per root -- two concurrent accepts of two versions cannot both win;
* a quote that left `draft` is FROZEN: its commercial columns and its lines are refused on UPDATE / DELETE
  (`QU003`), so what a customer accepted can never change under them (a revision is a NEW version);
* `quo_acceptances` (the customer-consent record: who, when, IP, the exact consent text, the sha256 of the terms)
  and `quo_events` (the audit trail) are APPEND-ONLY (`QU002`); one decision per quote version;
* composite FKs `(party_id, org_id)` / `(quote_id, org_id)` make a cross-tenant reference impossible even through
  the service role; money is integer cents (`BIGINT`), `total = subtotal - discount` is a CHECK.

The per-org human number comes from `quo_next_number(org)`: ONE `INSERT .. ON CONFLICT DO UPDATE .. RETURNING`
statement, atomic under concurrency without a read-then-write race.

Prerequisites (not created here): `public.current_org_id_for(text)` (core 070; the default `org_id_expr`), and, when
`cfg.with_parties` / `cfg.with_items`, those organs' tables (`parties` needs `UNIQUE (id, org_id)`, which it ships).
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import definer_search_path, org_rls

from .config import QuotesConfig
from .types import Channel, ConversionStatus, ConvertTo, Decision, EventKind, LineKind, QuoteStatus, values

#: Every organ table (unprefixed), in dependency order. The generator and isolation tests iterate this.
QUOTES_TABLES: tuple[str, ...] = ("counters", "quotes", "lines", "acceptances", "events")

#: History that is never updated, deleted or truncated (a trigger refuses).
APPEND_ONLY_TABLES: tuple[str, ...] = ("acceptances", "events")

#: SQLSTATEs carrying a refusal out of a trigger: append-only (`QU002`), frozen-after-draft (`QU003`).
APPEND_ONLY_SQLSTATE = "QU002"
FROZEN_SQLSTATE = "QU003"

#: Quote columns that define WHAT was offered -- frozen once the quote leaves `draft`.
FROZEN_QUOTE_COLUMNS: tuple[str, ...] = (
    "number", "root_id", "version", "party_id", "title", "currency", "valid_until", "notes", "terms",
    "convert_to", "subtotal_cents", "discount_cents", "total_cents", "created_by",
)


def _in(enum_cls) -> str:
    return ", ".join(f"'{v}'" for v in values(enum_cls))


def _append_only(s: str, table: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION {s}.{table}_append_only() RETURNS trigger
LANGUAGE plpgsql
{definer_search_path(s)}
AS $fn$
BEGIN
    RAISE EXCEPTION '{table} is append-only (% refused)', TG_OP USING ERRCODE = '{APPEND_ONLY_SQLSTATE}';
END;
$fn$;
DROP TRIGGER IF EXISTS {table}_no_update_delete ON {s}.{table};
CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {s}.{table}
    FOR EACH ROW EXECUTE FUNCTION {s}.{table}_append_only();
DROP TRIGGER IF EXISTS {table}_no_truncate ON {s}.{table};
CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {s}.{table}
    FOR EACH STATEMENT EXECUTE FUNCTION {s}.{table}_append_only();"""


def _tables(cfg: QuotesConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    t = {name: cfg.table(name) for name in QUOTES_TABLES}
    party_fk = (
        f",\n    FOREIGN KEY (party_id, org_id) REFERENCES {s}.{cfg.parties_table} (id, org_id) ON DELETE RESTRICT"
        if cfg.with_parties
        else ""
    )
    item_fk = f" REFERENCES {s}.{cfg.items_table}(id) ON DELETE RESTRICT" if cfg.with_items else ""
    frozen_diff = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in FROZEN_QUOTE_COLUMNS)
    sections = [
        (
            "Per-org quote number sequence (advanced ONLY by quo_next_number).",
            "counters",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['counters']} (
    org_id       UUID PRIMARY KEY,
    last_number  BIGINT NOT NULL DEFAULT 0 CHECK (last_number >= 0)
);
""",
        ),
        (
            "Quotes (orçamentos / propostas). One row per VERSION; `convert_to` NULL = derive from the lines at accept time; `root_id` ties the revisions of one quote together "
            "(`root_id = id` on version 1). Money is integer cents; a quote that left draft is frozen (trigger).",
            "quotes",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['quotes']} (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    number              TEXT NOT NULL CHECK (btrim(number) <> ''),
    root_id             UUID NOT NULL,
    version             INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    is_current          BOOLEAN NOT NULL DEFAULT true,
    party_id            UUID NOT NULL,
    title               TEXT,
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ({_in(QuoteStatus)})),
    currency            TEXT NOT NULL DEFAULT '{cfg.currency}' CHECK (currency ~ '^[A-Z]{{3}}$'),
    valid_until         DATE,
    notes               TEXT,
    terms               TEXT,
    convert_to          TEXT CHECK (convert_to IS NULL OR convert_to IN ({_in(ConvertTo)})),
    subtotal_cents      BIGINT NOT NULL DEFAULT 0 CHECK (subtotal_cents >= 0),
    discount_cents      BIGINT NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    total_cents         BIGINT NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    sent_at             TIMESTAMPTZ,
    last_sent_to        TEXT,
    viewed_at           TIMESTAMPTZ,
    accepted_at         TIMESTAMPTZ,
    rejected_at         TIMESTAMPTZ,
    expired_at          TIMESTAMPTZ,
    rejection_reason    TEXT,
    conversion_status   TEXT NOT NULL DEFAULT 'none' CHECK (conversion_status IN ({_in(ConversionStatus)})),
    conversion_kind     TEXT,
    conversion_ref      TEXT,
    conversion_error    TEXT,
    signature_ref       TEXT,
    signature_status    TEXT,
    created_by          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, org_id),
    CHECK (total_cents = subtotal_cents - discount_cents),
    CHECK ((status = 'accepted') = (accepted_at IS NOT NULL)){party_fk}
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['quotes']}_version ON {s}.{t['quotes']} (org_id, root_id, version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['quotes']}_number ON {s}.{t['quotes']} (org_id, number, version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['quotes']}_current ON {s}.{t['quotes']} (org_id, root_id) WHERE is_current;
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['quotes']}_accepted ON {s}.{t['quotes']} (org_id, root_id) WHERE status = 'accepted';
CREATE INDEX IF NOT EXISTS idx_{t['quotes']}_status ON {s}.{t['quotes']} (org_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_{t['quotes']}_party ON {s}.{t['quotes']} (org_id, party_id);
CREATE INDEX IF NOT EXISTS idx_{t['quotes']}_due ON {s}.{t['quotes']} (org_id, valid_until) WHERE status IN ('sent', 'viewed');

CREATE OR REPLACE FUNCTION {s}.{t['quotes']}_frozen() RETURNS trigger
LANGUAGE plpgsql
{definer_search_path(s)}
AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION '{t['quotes']}: only a draft can be deleted' USING ERRCODE = '{FROZEN_SQLSTATE}';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status <> 'draft' AND ({frozen_diff}) THEN
        RAISE EXCEPTION '{t['quotes']}: a quote that left draft is frozen -- revise it as a new version' USING ERRCODE = '{FROZEN_SQLSTATE}';
    END IF;
    RETURN NEW;
END;
$fn$;
DROP TRIGGER IF EXISTS {t['quotes']}_frozen ON {s}.{t['quotes']};
CREATE TRIGGER {t['quotes']}_frozen BEFORE UPDATE OR DELETE ON {s}.{t['quotes']}
    FOR EACH ROW EXECUTE FUNCTION {s}.{t['quotes']}_frozen();
""",
        ),
        (
            "Quote lines. `kind` (goods | service) drives convert-on-accept; `item_id` is optional (a free-text line is "
            "allowed); description / unit / price are SNAPSHOTS. Frozen with their quote (trigger).",
            "lines",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['lines']} (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    quote_id         UUID NOT NULL,
    position         INTEGER NOT NULL CHECK (position >= 0),
    item_id          UUID{item_fk},
    description      TEXT NOT NULL CHECK (btrim(description) <> ''),
    unit             TEXT NOT NULL DEFAULT 'UN',
    kind             TEXT NOT NULL DEFAULT 'goods' CHECK (kind IN ({_in(LineKind)})),
    qty              NUMERIC(18,3) NOT NULL CHECK (qty > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    discount_cents   BIGINT NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    total_cents      BIGINT NOT NULL CHECK (total_cents >= 0),
    UNIQUE (quote_id, position),
    FOREIGN KEY (quote_id, org_id) REFERENCES {s}.{t['quotes']} (id, org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_{t['lines']}_item ON {s}.{t['lines']} (org_id, item_id) WHERE item_id IS NOT NULL;

CREATE OR REPLACE FUNCTION {s}.{t['lines']}_frozen() RETURNS trigger
LANGUAGE plpgsql
{definer_search_path(s)}
AS $fn$
DECLARE v_status TEXT;
BEGIN
    SELECT status INTO v_status FROM {s}.{t['quotes']}
        WHERE id = COALESCE(NEW.quote_id, OLD.quote_id) AND org_id = COALESCE(NEW.org_id, OLD.org_id);
    IF v_status IS NOT NULL AND v_status <> 'draft' THEN
        RAISE EXCEPTION '{t['lines']}: the lines of a quote that left draft are frozen' USING ERRCODE = '{FROZEN_SQLSTATE}';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$fn$;
DROP TRIGGER IF EXISTS {t['lines']}_frozen ON {s}.{t['lines']};
CREATE TRIGGER {t['lines']}_frozen BEFORE INSERT OR UPDATE OR DELETE ON {s}.{t['lines']}
    FOR EACH ROW EXECUTE FUNCTION {s}.{t['lines']}_frozen();
""",
        ),
        (
            "Customer decisions (the consent record): who, when, from where, the EXACT consent text shown and the "
            "sha256 of the terms decided on. ONE decision per quote version. APPEND-ONLY.",
            "acceptances",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['acceptances']} (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    quote_id        UUID NOT NULL,
    decision        TEXT NOT NULL CHECK (decision IN ({_in(Decision)})),
    channel         TEXT NOT NULL CHECK (channel IN ({_in(Channel)})),
    signer_name     TEXT NOT NULL CHECK (btrim(signer_name) <> ''),
    reason          TEXT,
    consent_text    TEXT,
    content_sha256  TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{{64}}$'),
    ip              TEXT,
    user_agent      TEXT,
    decided_by      UUID,
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, quote_id),
    CHECK (decision <> 'accepted' OR consent_text IS NOT NULL OR channel = 'staff'),
    FOREIGN KEY (quote_id, org_id) REFERENCES {s}.{t['quotes']} (id, org_id) ON DELETE RESTRICT
);
{_append_only(s, t['acceptances'])}
""",
        ),
        (
            "Audit trail of a quote (APPEND-ONLY, no FK so deleting a draft leaves its history).",
            "events",
            f"""
CREATE TABLE IF NOT EXISTS {s}.{t['events']} (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq          BIGINT GENERATED ALWAYS AS IDENTITY,
    org_id       UUID NOT NULL,
    quote_id     UUID NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ({_in(EventKind)})),
    from_status  TEXT,
    to_status    TEXT,
    actor        UUID,
    detail       JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(detail) = 'object')
);
CREATE INDEX IF NOT EXISTS idx_{t['events']}_quote ON {s}.{t['events']} (org_id, quote_id, seq);
{_append_only(s, t['events'])}
""",
        ),
    ]
    out: list[str] = []
    for title, name, body in sections:
        out.append(f"-- {title}\n{body.strip()}\n{org_rls(s, t[name], o, grants=True)}")
    return out


def _rpcs(cfg: QuotesConfig, s: str) -> str:
    counters = f"{s}.{cfg.table('counters')}"
    name = f"{s}.{cfg.rpc('next_number')}"
    return f"""-- The per-org number: one atomic upsert-returning (no read-then-write race). service_role only.
CREATE OR REPLACE FUNCTION {name}(p_org UUID) RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
{definer_search_path(s)}
AS $fn$
DECLARE v_n BIGINT;
BEGIN
    INSERT INTO {counters} (org_id, last_number) VALUES (p_org, 1)
        ON CONFLICT (org_id) DO UPDATE SET last_number = {counters}.last_number + 1
        RETURNING last_number INTO v_n;
    RETURN v_n;
END;
$fn$;
REVOKE ALL ON FUNCTION {name}(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {name}(UUID) TO service_role;"""


def quotes_migration(cfg: QuotesConfig, schema: str) -> str:
    """The whole quotes DDL for `schema`, as one re-runnable migration body."""
    if not schema or not schema.strip():
        raise ValueError("quotes_migration requires a non-empty schema")
    if schema != cfg.schema:
        raise ValueError(f"quotes_migration schema {schema!r} must equal cfg.schema {cfg.schema!r}")
    sections = [
        "-- Quotes organ -- generated by noctusai_lib.domain.quotes.sql (do not hand-edit)",
        f"SET search_path = {schema}, public;",
        *_tables(cfg, schema),
        _rpcs(cfg, schema),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = [
    "APPEND_ONLY_SQLSTATE",
    "APPEND_ONLY_TABLES",
    "FROZEN_QUOTE_COLUMNS",
    "FROZEN_SQLSTATE",
    "QUOTES_TABLES",
    "quotes_migration",
]
