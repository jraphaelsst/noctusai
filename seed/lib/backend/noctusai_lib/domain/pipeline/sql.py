"""`pipeline_migration(cfg, schema)` — the pipeline DDL for a NEW product.

Until now the canonical DDL for the pipeline organ lived in exactly one place,
ERP's `042_pipeline_stages.sql`, which is hand-written for two ERP boards (a
`CHECK (pipeline IN ('funil', 'processos_venda'))`, ERP-only FKs, an ERP org
trigger). A second product copying it copies those ERP assumptions. This module
emits the ORGAN's tables parameterised by `PipelineConfig`, the same way
`card_hub_migration` does for the card hub.

What it emits (all idempotent, forward-only):

* `{stages_table}` — user-editable stages (id, org_id, pipeline, slug, label,
  cor, posicao, papel, ativo, timestamps; `UNIQUE (org_id, pipeline, slug)`,
  one stage per `papel` per pipeline).
* `{history_table}` — the stage-transition history, APPEND-ONLY (a trigger
  refuses UPDATE and DELETE; a trail that can be edited is not a trail).
* the CARD columns on `{card_table}` (which must already exist): `etapa_id`,
  `kanban_pos numeric` (never integer — see `ordering`), the status column,
  `motivo_perda_codigo`, `motivo_perda`.

SERVICE-ROLE ONLY. The two tables it CREATES carry RLS with a
`service_role_bypass` policy and nothing for `authenticated`/`anon`, plus an
explicit `REVOKE ALL ... FROM anon, authenticated`. A table in an exposed
schema with an `authenticated` grant and an org-scoped policy is a read API for
the whole org straight from the browser (the finance organ's P1, 2026-11-05);
the pipeline backend always reaches these tables through the service-role
client, so no browser path is ever needed. The card table's own grants are the
consumer's, not this module's — it only ADDS columns.

Deliberately NOT emitted:

* a `CHECK (pipeline IN (...))` / `CHECK (papel IN (...))` — the stage table is
  shared by every pipeline in a schema and each declares its own roles
  (`PipelineConfig.stage_roles`); the API validates both. A per-pipeline CHECK
  breaks the second pipeline.
* a CHECK on the status column — the consumer may already hold its own
  vocabulary there (`FunnelConfig.status_values` maps the canonical four onto
  it); the API validates.
* default stages — `ensure_default_stages` seeds them from Python.

`tier` is the access tier written into `COMMENT ON TABLE` (`KB § PATTERNS/
security/access-tiers.md`): `"platform"` for a platform-tenancy funnel,
`"org"` otherwise.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import (
    service_role_bypass,
    updated_at_trigger,
)

from .config import PipelineConfig

_TIERS = ("platform", "org")
_UPDATED_AT_FN = "pipeline_set_updated_at"


def _touch_function(schema: str, name: str) -> str:
    """The `updated_at` touch trigger function: SECURITY INVOKER (a touch needs no
    elevated rights), empty search_path, schema-qualified `pg_catalog.now()`."""
    return (
        f"CREATE OR REPLACE FUNCTION {schema}.{name}()\n"
        f"RETURNS TRIGGER\n"
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''\n"
        f"AS $$ BEGIN NEW.updated_at = pg_catalog.now(); RETURN NEW; END; $$;"
    )


def _path_list(schema: str) -> str:
    """`<schema>, public` without repeating `public` when the schema IS public."""
    return "public" if schema == "public" else f"{schema}, public"


def _search_path(schema: str) -> str:
    return f"SET search_path = {_path_list(schema)};"


def _ident(value: str, what: str) -> str:
    if not value or not value.replace("_", "").isalnum() or value[0].isdigit():
        raise ValueError(f"pipeline_migration: {what} {value!r} is not a plain SQL identifier")
    return value


def _lockdown(schema: str, table: str, tier: str) -> str:
    return "\n".join(
        [
            f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;",
            f"REVOKE ALL ON {schema}.{table} FROM anon, authenticated;",
            f"GRANT ALL ON {schema}.{table} TO service_role;",
            f'DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{table};',
            service_role_bypass(table, schema=schema),
            f"COMMENT ON TABLE {schema}.{table} IS 'tier:{tier}';",
        ]
    )


def _stages(cfg: PipelineConfig, schema: str, tier: str) -> str:
    t = _ident(cfg.stages_table, "stages_table")
    return f"""-- Stages are ROWS (rename = one UPDATE). `papel` is the semantic role code keys on.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    pipeline    TEXT NOT NULL,
    slug        TEXT NOT NULL CHECK (slug ~ '^[a-z0-9_]+$'),
    label       TEXT NOT NULL CHECK (length(trim(label)) > 0),
    cor         TEXT NOT NULL DEFAULT 'secondary'
                CHECK (cor IN ('primary', 'secondary', 'success', 'warning', 'destructive', 'muted')),
    posicao     INTEGER NOT NULL DEFAULT 0,
    papel       TEXT,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, pipeline, slug)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t}_papel
    ON {schema}.{t} (org_id, pipeline, papel) WHERE papel IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t}_board ON {schema}.{t} (org_id, pipeline, posicao);
{updated_at_trigger(schema, t, function_name=_UPDATED_AT_FN)}
{_lockdown(schema, t, tier)}"""


def _history(cfg: PipelineConfig, schema: str, tier: str) -> str:
    t, st = _ident(cfg.history_table, "history_table"), cfg.stages_table
    cliente = "    cliente_id     UUID,\n" if cfg.cliente_field else ""
    return f"""-- Stage-transition history. APPEND-ONLY: the trigger refuses UPDATE/DELETE.
-- `entidade_id` is deliberately not an FK (one column cannot reference every
-- pipeline's card table); `responsavel_id` is nullable (system moves) and not
-- an FK (the user table differs per product). `kind` = mover | entrada | perdido |
-- reaberto | arquivado; status events repeat the card's current stage in both
-- columns (`para_etapa_id` is NULL only for a card that sits in no stage).
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    pipeline       TEXT NOT NULL,
    entidade_id    UUID NOT NULL,
{cliente}    de_etapa_id    UUID REFERENCES {schema}.{st}(id),
    para_etapa_id  UUID REFERENCES {schema}.{st}(id),
    kind           TEXT NOT NULL DEFAULT 'mover',
    responsavel_id UUID,
    motivo         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE {schema}.{t} ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'mover';
CREATE INDEX IF NOT EXISTS idx_{t}_entidade ON {schema}.{t} (org_id, pipeline, entidade_id, created_at DESC);
CREATE OR REPLACE FUNCTION {schema}.{t}_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = {_path_list(schema)}
AS $$ BEGIN RAISE EXCEPTION '{t} is append-only'; END; $$;
DROP TRIGGER IF EXISTS {t}_no_update_delete ON {schema}.{t};
CREATE TRIGGER {t}_no_update_delete
    BEFORE UPDATE OR DELETE ON {schema}.{t}
    FOR EACH ROW EXECUTE FUNCTION {schema}.{t}_append_only();
{_lockdown(schema, t, tier)}"""


def _card_columns(cfg: PipelineConfig, schema: str) -> str:
    c, st = _ident(cfg.card_table, "card_table"), cfg.stages_table
    status = _ident(cfg.status_field or "status", "status_field")
    return f"""-- Card columns the funnel organ reads/writes. `kanban_pos` is NUMERIC, never
-- integer: a drop between two cards stores their midpoint (see `ordering`).
ALTER TABLE {schema}.{c}
    ADD COLUMN IF NOT EXISTS etapa_id UUID REFERENCES {schema}.{st}(id),
    ADD COLUMN IF NOT EXISTS kanban_pos NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS {status} TEXT NOT NULL DEFAULT 'aberto',
    ADD COLUMN IF NOT EXISTS motivo_perda_codigo TEXT,
    ADD COLUMN IF NOT EXISTS motivo_perda TEXT;
CREATE INDEX IF NOT EXISTS idx_{c}_etapa_pos ON {schema}.{c} (etapa_id, kanban_pos);"""


def pipeline_migration(cfg: PipelineConfig, schema: str, *, tier: str = "org") -> str:
    """The whole pipeline DDL for `schema`, as one migration body.

    Prerequisites (not created here): `{schema}.{cfg.card_table}`.
    """
    if not schema or not schema.strip():
        raise ValueError("pipeline_migration requires a non-empty schema")
    _ident(schema, "schema")
    if tier not in _TIERS:
        raise ValueError(f"pipeline_migration: tier must be one of {_TIERS}, got {tier!r}")
    sections = [
        f"-- Pipeline ({cfg.pipeline}) -- generated by noctusai_lib.domain.pipeline.sql",
        _search_path(schema),
        _touch_function(schema, _UPDATED_AT_FN),
        _stages(cfg, schema, tier),
        _history(cfg, schema, tier),
        _card_columns(cfg, schema),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["pipeline_migration"]
