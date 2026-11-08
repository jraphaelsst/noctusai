"""`card_hub_migration(cfg, schema)` — the card-hub DDL for a NEW product.

Emits the equivalent of social-wiring migrations 056 (notes, tags, members,
entity "Datas" columns, reminders, checklists) + 057 (document catalogue,
documents, access log, private bucket + object RLS) + 083 (operator checklist
lines), parameterized by the config's table / FK / bucket names, composed from
`noctusai_lib.domain.sql_templates` so the RLS + search_path conventions cannot
drift. Pure string emission — no IO.

Social-wiring NEVER runs this (its tables exist; migration files are replay
logs and stay verbatim). The parity test pins that, for social-wiring's config,
the emitted COLUMNS equal what 056 + 057 + 083 created — so a product
generating its card hub from this template gets the same columns the lifted
code was written against.

Conventions every table follows:

- `org_id UUID NOT NULL`; RLS enabled; SERVICE-ONLY (the igig 044 shape): the
  literal-named `service_role_bypass` policy, `REVOKE ALL ... FROM PUBLIC, anon,
  authenticated`, `GRANT ALL ... TO service_role`, `COMMENT ... 'tier:org'`. The
  backend reaches the card hub through the service-role client, scoping every
  query by `org_id`; no browser role holds a policy or a privilege (the access
  log is append-only for everyone but `service_role` BY CONSTRUCTION).
- Soft-delete columns where the lifted code soft-deletes.
- Forward-only and idempotent (`IF NOT EXISTS`, `DROP POLICY IF EXISTS`
  before `CREATE POLICY`, `ON CONFLICT DO NOTHING` catalogue seed).
"""
from __future__ import annotations

from typing import Optional, Sequence

from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    service_role_bypass,
    set_search_path,
)

from .config import CardHubConfig

#: `(tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo,
#: descricao)`. The conservative default: identity-class types ship
#: `ativo = false` — enabling them is a data change gated on the product's
#: LGPD data-category intake, never a deploy. `outro` is required: it is what
#: an operator-authored checklist line's upload is filed under. (No `--` inside
#: a description: line-comment stripping in SQL tooling that is not
#: string-literal-aware — the mock's migration parser among them — would eat
#: the closing quote and every statement after it.)
DEFAULT_DOCUMENTO_TIPOS: tuple[tuple, ...] = (
    ("contrato", "contratual", 1825, False, True, "Contratos e aditivos"),
    ("proposta", "contratual", 1095, False, True, "Propostas comerciais"),
    ("comprovante_pagamento", "financeiro", 1825, False, True, "Comprovantes de pagamento"),
    ("comprovante_endereco", "cadastral", 730, False, True, "Comprovante de endereço"),
    ("outro", "nao_classificado", 365, False, True, "Outro documento não classificado"),
    ("rg", "identidade", 1825, True, False, "RG (retenção pendente de intake LGPD)"),
    ("cpf", "identidade", 1825, True, False, "CPF (retenção pendente de intake LGPD)"),
)

#: The home-org helper the seed has always emitted; a consumer whose migrations must use a
#: different resolver (social-wiring: the org-picker-aware `current_org_id_for`) passes
#: `org_id_expr=` to `card_hub_migration` instead of rewriting the generated text.
DEFAULT_ORG_ID_EXPR = "public.current_org_id()"


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _org_rls(schema: str, table: str, org_id_expr: Optional[str] = None) -> str:
    """The table's access shape.

    `org_id_expr=None` (the default, and what `card_hub_migration` emits): SERVICE-ONLY, the
    igig 044 shape -- RLS on, `service_role_bypass`, `REVOKE ALL ... FROM PUBLIC, anon,
    authenticated`, `GRANT ALL ... TO service_role`, `COMMENT ... 'tier:org'`. The card hub is
    reached only through the backend's service-role client, which scopes every query by
    `org_id`; no browser role holds a privilege or a policy on it.

    `org_id_expr="..."` (only via `card_hub_migration(legacy_browser_read=True)`): the old
    own-org SELECT policy for `authenticated`, kept solely to reproduce already-applied
    replay logs byte-for-byte.
    """
    lines = [f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;"]
    if org_id_expr is not None:
        select_name = f"{table}_select_own_org"
        lines += [
            f'DROP POLICY IF EXISTS "{select_name}" ON {schema}.{table};',
            rls_subquery_policy(schema, table, select_name, "SELECT", using=f"org_id = (SELECT {org_id_expr})"),
        ]
    lines += [
        f'DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{table};',
        service_role_bypass(table, schema=schema),
    ]
    if org_id_expr is None:
        lines += _service_only_lines(schema, table)
    return "\n".join(lines)


def _service_only_lines(schema: str, table: str) -> list[str]:
    return [
        f"REVOKE ALL ON TABLE {schema}.{table} FROM PUBLIC, anon, authenticated;",
        f"GRANT ALL ON TABLE {schema}.{table} TO service_role;",
        f"COMMENT ON TABLE {schema}.{table} IS 'tier:org';",
    ]


def _entity_fk(cfg: CardHubConfig, schema: str) -> str:
    return f"{cfg.entity_fk} UUID NOT NULL REFERENCES {schema}.{cfg.entity_table}(id) ON DELETE CASCADE"


def _notas(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t = cfg.tables.notas
    return f"""-- Notes: one `descricao` per card (partial unique index) + many `comentario`.
-- Soft-delete only: a deleted note leaves a tombstone.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    {_entity_fk(cfg, schema)},
    autor_id    UUID,
    tipo        TEXT NOT NULL DEFAULT 'comentario' CHECK (tipo IN ('descricao', 'comentario')),
    corpo       TEXT NOT NULL,
    editado_em  TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{t}_entity ON {schema}.{t} ({cfg.entity_fk}, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_{t}_org ON {schema}.{t} (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t}_one_descricao
    ON {schema}.{t} ({cfg.entity_fk})
    WHERE tipo = 'descricao' AND deleted_at IS NULL;
{_org_rls(schema, t, org_id_expr)}"""


def _tags(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t, links = cfg.tables.tags, cfg.tables.tag_links
    return f"""-- ONE org tag catalogue (case-insensitive unique name) + per-card links.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    nome        TEXT NOT NULL,
    cor         TEXT NOT NULL CHECK (cor ~ '^#[0-9a-fA-F]{{6}}$'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t}_org_nome ON {schema}.{t} (org_id, lower(nome));
{_org_rls(schema, t, org_id_expr)}

CREATE TABLE IF NOT EXISTS {schema}.{links} (
    {_entity_fk(cfg, schema)},
    tag_id      UUID NOT NULL REFERENCES {schema}.{t}(id) ON DELETE CASCADE,
    org_id      UUID NOT NULL,
    criado_por  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ({cfg.entity_fk}, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_{links}_tag ON {schema}.{links} (tag_id);
CREATE INDEX IF NOT EXISTS idx_{links}_org ON {schema}.{links} (org_id);
{_org_rls(schema, links, org_id_expr)}"""


def _membros(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t, src = cfg.tables.membros, cfg.member_source
    return f"""-- Assignment: points at the member source's id, NEVER at a name.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    {_entity_fk(cfg, schema)},
    {src.fk} UUID NOT NULL REFERENCES {schema}.{src.table}(id) ON DELETE CASCADE,
    org_id      UUID NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ({cfg.entity_fk}, {src.fk})
);
CREATE INDEX IF NOT EXISTS idx_{t}_member ON {schema}.{t} ({src.fk});
CREATE INDEX IF NOT EXISTS idx_{t}_org ON {schema}.{t} (org_id);
{_org_rls(schema, t, org_id_expr)}"""


def _datas(cfg: CardHubConfig, schema: str) -> str:
    e = cfg.entity_table
    constraint = f"{e}_recorrencia_valid"
    return f"""-- Trello "Datas" on the entity row.
ALTER TABLE {schema}.{e}
    ADD COLUMN IF NOT EXISTS data_inicio             TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_entrega            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS entrega_concluida       BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS lembrete_minutos_antes  INTEGER,
    ADD COLUMN IF NOT EXISTS recorrencia             TEXT;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{constraint}') THEN
        ALTER TABLE {schema}.{e}
            ADD CONSTRAINT {constraint}
            CHECK (recorrencia IS NULL OR recorrencia IN ('diaria', 'semanal', 'mensal', 'anual'));
    END IF;
END $$;"""


def _lembretes(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t = cfg.tables.lembretes
    # `lembretes_crud` opt-in (default False — social-wiring's real 056 table
    # has neither column; `test_template_columns_equal_sw_056_057_083` pins
    # that). igig's card hubs turn it on for the ad-hoc reminder CRUD.
    extra_cols = ""
    if cfg.lembretes_crud:
        extra_cols = f"""
    titulo         TEXT NOT NULL DEFAULT '',
    responsavel_id UUID REFERENCES {schema}.{cfg.member_source.table}(id) ON DELETE SET NULL,"""
    return f"""-- One row per scheduled reminder fire; the partial index is the drain path.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    {_entity_fk(cfg, schema)},{extra_cols}
    dispara_em    TIMESTAMPTZ NOT NULL,
    enviado_em    TIMESTAMPTZ,
    cancelado_em  TIMESTAMPTZ,
    destinatarios JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{t}_pending ON {schema}.{t} (dispara_em)
    WHERE enviado_em IS NULL AND cancelado_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_{t}_entity ON {schema}.{t} ({cfg.entity_fk}, created_at DESC);
{_org_rls(schema, t, org_id_expr)}"""


def _checklists(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t, itens = cfg.tables.checklists, cfg.tables.checklist_itens
    etapa_ref = (
        f" REFERENCES {schema}.{cfg.stage_table}(id) ON DELETE SET NULL" if cfg.stage_table else ""
    )
    return f"""-- Checklists (ad-hoc or stage-instantiated; many per card) + items.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    {_entity_fk(cfg, schema)},
    titulo      TEXT NOT NULL,
    posicao     INTEGER NOT NULL DEFAULT 0,
    origem      TEXT NOT NULL CHECK (origem IN ('ad_hoc', 'etapa')),
    etapa_id    UUID{etapa_ref},
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{t}_entity ON {schema}.{t} ({cfg.entity_fk}, posicao);
{_org_rls(schema, t, org_id_expr)}

CREATE TABLE IF NOT EXISTS {schema}.{itens} (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    checklist_id   UUID NOT NULL REFERENCES {schema}.{t}(id) ON DELETE CASCADE,
    texto          TEXT NOT NULL,
    concluido      BOOLEAN NOT NULL DEFAULT false,
    concluido_em   TIMESTAMPTZ,
    concluido_por  UUID,
    posicao        INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{itens}_checklist ON {schema}.{itens} (checklist_id, posicao);
{_org_rls(schema, itens, org_id_expr)}"""


def _documento_tipos(
    cfg: CardHubConfig, schema: str, tipos: Sequence[tuple], *, legacy_browser_read: bool = False
) -> str:
    t = cfg.tables.documento_tipos
    select_name = f"{t}_select_authenticated"
    values = ",\n    ".join(
        "(" + ", ".join(_sql_literal(v) for v in row) + ")" for row in tipos
    )
    seed = (
        f"""
INSERT INTO {schema}.{t}
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    {values}
ON CONFLICT (tipo_documento) DO NOTHING;"""
        if tipos
        else ""
    )
    if legacy_browser_read:
        access = f"""ALTER TABLE {schema}.{t} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "{select_name}" ON {schema}.{t};
{rls_subquery_policy(schema, t, select_name, "SELECT", using="true")}
DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{t};
{service_role_bypass(t, schema=schema)}"""
    else:
        access = _org_rls(schema, t)
    return f"""-- The table-driven retention + upload allow-list (platform-wide, no org_id).
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    tipo_documento  TEXT PRIMARY KEY,
    categoria_lgpd  TEXT NOT NULL,
    retencao_dias   INTEGER,
    identidade      BOOLEAN NOT NULL DEFAULT false,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    descricao       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
{access}{seed}"""


def _documentos(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t, tipos, acessos = cfg.tables.documentos, cfg.tables.documento_tipos, cfg.tables.documento_acessos
    return f"""-- Documents (soft delete with reason) + the append-only access log.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    {_entity_fk(cfg, schema)},
    storage_path           TEXT NOT NULL,
    nome_original          TEXT NOT NULL,
    mime_type              TEXT NOT NULL,
    tamanho_bytes          BIGINT NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_documento         TEXT NOT NULL REFERENCES {schema}.{tipos}(tipo_documento),
    categoria_lgpd         TEXT NOT NULL,
    retencao_ate           DATE,
    enviado_por            UUID,
    deleted_at             TIMESTAMPTZ,
    delete_motivo          TEXT,
    delete_solicitado_por  UUID,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{t}_entity ON {schema}.{t} ({cfg.entity_fk}, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_{t}_org ON {schema}.{t} (org_id);
CREATE INDEX IF NOT EXISTS idx_{t}_retencao ON {schema}.{t} (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;
{_org_rls(schema, t, org_id_expr)}

CREATE TABLE IF NOT EXISTS {schema}.{acessos} (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    documento_id  UUID NOT NULL REFERENCES {schema}.{t}(id) ON DELETE CASCADE,
    usuario_id    UUID,
    acao          TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{acessos}_documento ON {schema}.{acessos} (documento_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_{acessos}_org ON {schema}.{acessos} (org_id);
{_org_rls(schema, acessos, org_id_expr)}"""


def _bucket(cfg: CardHubConfig, *, legacy_browser_read: bool = False) -> str:
    """Private bucket + object RLS on the FIRST key segment (`org_id`).

    Policy names on `storage.objects` are global to that table, so each is
    bucket-qualified — two products' card hubs must not replace each other's.
    """
    b = cfg.bucket
    predicate = (
        f"bucket_id = '{b}' AND (storage.foldername(name))[1] = (SELECT public.current_org_id())::text"
    )
    parts = [
        f"INSERT INTO storage.buckets (id, name, public)\nVALUES ('{b}', '{b}', false)\nON CONFLICT (id) DO NOTHING;"
    ]
    browser_cmds = (
        ("SELECT", predicate, None),
        ("INSERT", None, predicate),
        ("UPDATE", predicate, None),
        ("DELETE", predicate, None),
    )
    for cmd, using, with_check in browser_cmds if legacy_browser_read else ():
        name = f"{b}_storage_{cmd.lower()}"
        parts.append(f'DROP POLICY IF EXISTS "{name}" ON storage.objects;')
        parts.append(rls_subquery_policy("storage", "objects", name, cmd, using=using, with_check=with_check))
    service_name = f"{b}_storage_service"
    parts.append(f'DROP POLICY IF EXISTS "{service_name}" ON storage.objects;')
    parts.append(
        rls_subquery_policy(
            "storage",
            "objects",
            service_name,
            "ALL",
            using=f"bucket_id = '{b}'",
            with_check=f"bucket_id = '{b}'",
            to_role="service_role",
        )
    )
    head = (
        "-- Private document bucket; object RLS keys on the org_id first path segment."
        if legacy_browser_read
        else "-- Private document bucket; service-role only (every file op goes through the backend)."
    )
    return head + "\n" + "\n".join(parts)


def _checklist_extras(cfg: CardHubConfig, schema: str, org_id_expr: Optional[str] = None) -> str:
    t, docs = cfg.tables.checklist_extras, cfg.tables.documentos
    return f"""-- Operator-authored checklist lines. NO `concluido` column: completion is
-- DERIVED (valor_texto / a live documento_id). Deleting the file keeps the line.
CREATE TABLE IF NOT EXISTS {schema}.{t} (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    {_entity_fk(cfg, schema)},
    label         TEXT NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('texto', 'arquivo')),
    valor_texto   TEXT,
    documento_id  UUID REFERENCES {schema}.{docs}(id) ON DELETE SET NULL,
    ordem         INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_{t}_entity ON {schema}.{t} ({cfg.entity_fk}, ordem, created_at)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_{t}_org ON {schema}.{t} (org_id);
CREATE INDEX IF NOT EXISTS idx_{t}_documento ON {schema}.{t} (documento_id)
    WHERE documento_id IS NOT NULL;
{_org_rls(schema, t, org_id_expr)}"""


def card_hub_migration(
    cfg: CardHubConfig,
    schema: str,
    *,
    documento_tipos: Optional[Sequence[tuple]] = None,
    org_id_expr: str = DEFAULT_ORG_ID_EXPR,
    legacy_browser_read: bool = False,
) -> str:
    """The whole card-hub DDL for `schema`, as one migration body.

    Prerequisites (not created here): `{schema}.{cfg.entity_table}`,
    `{schema}.{cfg.member_source.table}`, `{schema}.{cfg.stage_table}` (when
    set) and `public.current_org_id()`.

    `documento_tipos` overrides the seeded catalogue rows
    (`DEFAULT_DOCUMENTO_TIPOS`); pass `()` to seed none.

    SERVICE-ONLY BY CONSTRUCTION (the igig 044 shape): every table gets RLS + the literal
    `service_role_bypass` policy, `REVOKE ALL ... FROM PUBLIC, anon, authenticated`,
    `GRANT ALL ... TO service_role` and `COMMENT ... 'tier:org'`; the bucket keeps only its
    service-role policy. No browser role can read or write the card hub (security triage
    2026-11-07; `KB § PATTERNS/security/access-tiers.md`).

    `legacy_browser_read=True` reproduces the pre-2026-11-07 shape (own-org SELECT policies for
    `authenticated` + the org-folder bucket policies) and exists ONLY so already-applied,
    frozen replay logs (igig 019, social-wiring 241) stay byte-pinned to their generator;
    `check_card_hub_service_only` fails any NEW migration that carries it. In that mode
    `org_id_expr` is the expression the own-org SELECT policies compare `org_id` against;
    in the default mode it is unused.
    """
    if not schema or not schema.strip():
        raise ValueError("card_hub_migration requires a non-empty schema")
    tipos = DEFAULT_DOCUMENTO_TIPOS if documento_tipos is None else tuple(documento_tipos)
    rls_expr = org_id_expr if legacy_browser_read else None
    sections = [
        f"-- Card hub ({cfg.entity_kind}) -- generated by noctusai_lib.domain.card_hub.sql",
        f"{set_search_path(schema)};",
        _notas(cfg, schema, rls_expr),
        _tags(cfg, schema, rls_expr),
        _membros(cfg, schema, rls_expr),
    ]
    if cfg.entity_datas:
        sections.append(_datas(cfg, schema))
    sections += [
        _lembretes(cfg, schema, rls_expr),
        _checklists(cfg, schema, rls_expr),
        _documento_tipos(cfg, schema, tipos, legacy_browser_read=legacy_browser_read),
        _documentos(cfg, schema, rls_expr),
        _bucket(cfg, legacy_browser_read=legacy_browser_read),
        _checklist_extras(cfg, schema, rls_expr),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["DEFAULT_DOCUMENTO_TIPOS", "card_hub_migration"]
