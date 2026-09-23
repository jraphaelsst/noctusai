"""Social-wiring's card hub, as a seed `CardHubConfig`.

The card's generic mechanics (notas, tags, membros, checklists, checklist
extras, LGPD documents, the timeline pager, the badge row) live in the seed —
`noctusai_lib.domain.card_hub`, lifted out of THIS module as a MOVE (wave A,
`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`). This
file is everything that makes that generic card social-wiring's card, and
nothing else:

- the names — `table_prefix="cliente"` resolves every card-hub table to the
  migration-056/057/083 names this product already has (zero DDL);
- the members — `lead_corretores`, whose PUT body field is
  `lead_corretor_ids` (the HTTP contract);
- the entity read — `clientes_service.get_cliente` (its own rules, not a
  bare `select *`);
- who a user id is — `table_reads.resolve_actors`, through THIS product's
  core (`public`) client;
- the timeline kinds + badge/resumo keys only this product has
  (`timeline_service`);
- the document policy only this product has: retention from the editable
  policy table (migration 079, `documento_retencao`), and the identity-
  extraction state (migration 068) stamped at upload and served on reads.

Consumers reach it through `app.modules.card_hub.deps.card_hub_config()` —
see that accessor for why it is the one deferred import of this module.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from noctusai_lib.domain.card_hub import CardHubConfig, DocumentoPolicy, MemberSource

from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub import timeline_service
from app.modules.card_hub.checklist_extras_service import TIPO_DOCUMENTO
from app.modules.card_hub.deps import BUCKET
from app.modules.card_hub.documentos_service import ALLOWED_MIME_TYPES, MAX_UPLOAD_BYTES
from app.services import clientes_service as clientes_svc
from app.services import documento_retencao, table_reads

#: Signed-URL lifetime — short, minted per request, never stored (contract §2).
SIGNED_URL_TTL_SECONDS = 300


def _retencao_dias(client: Any, org_id: UUID, tipo_documento: str, _tipo_row: dict) -> Any:
    """🔴 The POLICY, not the catalogue. Migration 079 moved `retencao_dias`
    off `cliente_documento_tipos` (which only a migration could change) into
    `documento_retencao_politicas` (which the Settings screen can). The
    catalogue column still exists as a one-release rollback path and is
    marked superseded in the database itself — reading it here again would
    silently ignore whatever the controller set on the screen."""
    return documento_retencao.dias_para(client, org_id, "cliente", tipo_documento)


def _extracao_ao_enviar(tipo_documento: str) -> dict:
    """An identity document is queued for a field read the moment it lands
    (migration 068). `pendente` is set HERE, at insert, rather than by the
    background job — so a job that never starts (worker died, process
    recycled mid-request) is visibly waiting instead of invisibly lost."""
    return {
        "extracao_status": (
            "pendente" if identidade_svc.deve_extrair(tipo_documento) else None
        ),
    }


def _extracao_servida(row: dict) -> dict:
    """🔴 Extraction state, surfaced on every document read. Before this it
    was written by `identidade_extracao_service` and read only by the sweep
    and by `sugestoes_pendentes` — a document stuck in `erro` (an OpenAI 429,
    a corrupt PDF) showed nowhere on the card, indistinguishable from one that
    was never meant to be read at all. `None` for a non-identity type (never
    queued) is the honest value, not a gap."""
    return {
        "extracao_status": row.get("extracao_status"),
        "extracao_erro": row.get("extracao_erro"),
    }


CARD_HUB = CardHubConfig(
    entity_kind="cliente",
    entity_table="clientes",
    entity_fk="cliente_id",
    id_param="cliente_id",
    table_prefix="cliente",
    member_source=MemberSource(
        table="lead_corretores", fk="lead_corretor_id", label="nome", cor="cor"
    ),
    bucket=BUCKET,
    actor_resolver=table_reads.resolve_actors,
    ensure_entity=clientes_svc.get_cliente,
    timeline_gatherers=timeline_service.TIMELINE_GATHERERS,
    badge_extensions=(timeline_service.badges_sw,),
    resumo_extensions=(timeline_service.resumo_sw,),
    entity_datas=True,
    stage_table="pipeline_stages",
    documentos=DocumentoPolicy(
        # The module constant, not a second literal: `documentos_service
        # .MAX_UPLOAD_BYTES` stays the one place the policy is written. The
        # `/documentos` upload route passes the constant's LIVE value per call
        # (`documentos_service.upload_documento`); this is the value the
        # seed's own paths (a checklist-extra upload) enforce.
        max_upload_bytes=MAX_UPLOAD_BYTES,
        allowed_mime_types=ALLOWED_MIME_TYPES,
        signed_url_ttl_seconds=SIGNED_URL_TTL_SECONDS,
        # Object keys stay `{org_id}/clientes/{cliente_id}/{document_id}` —
        # the entity table name, the seed default — so every existing object
        # (and migration 057's object-RLS policies) stays valid.
        storage_segment=None,
        retention_days=_retencao_dias,
        extra_insert_fields=_extracao_ao_enviar,
        extra_out_fields=_extracao_servida,
    ),
    checklist_extra_tipo_documento=TIPO_DOCUMENTO,
)


__all__ = ["CARD_HUB", "SIGNED_URL_TTL_SECONDS"]
