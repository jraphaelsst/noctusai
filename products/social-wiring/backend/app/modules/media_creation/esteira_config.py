"""Esteira de reels -- the pipeline + card-hub declarations (esteira-contract.md 2.4 / 2.5).

Declarative only: the board is ONE more ``PipelineConfig`` on the shared
``social_wiring.pipeline_stages`` / ``pipeline_movimentos`` tables, and the post card
is the seed card hub (``noctusai_lib.domain.card_hub``) over ``cs_posts``. The
generated section of migration 241 is produced by :func:`gerar_migration_card_hub`
and a test pins that the file still carries exactly that text -- never hand-edit it.

Code keys only on stage ROLES (``gravacao``, ``postado``, ``cancelado``), never on
slugs or labels, so a renamed "Gravacao" keeps its gate.

The ``movimento`` timeline kind is :func:`esteira_timeline.gather_movimentos_esteira`
(bound at construction below).
"""
from __future__ import annotations

from noctusai_lib.domain.card_hub import (
    CardHubConfig,
    DocumentoPolicy,
    MemberSource,
    card_hub_migration,
)
from noctusai_lib.domain.card_hub.gatherers import SEED_GATHERERS
from noctusai_lib.domain.pipeline import PipelineConfig, StageDefault

from app.modules.media_creation.esteira_timeline import gather_movimentos_esteira
from app.services import table_reads

__all__ = [
    "BUCKET_ESTEIRA",
    "CS_POST_HUB",
    "ESTEIRA_DOC_TIPOS",
    "ESTEIRA_PADRAO",
    "PIPELINE_ESTEIRA",
    "ROLE_CANCELADO",
    "ROLE_GRAVACAO",
    "ROLE_POSTADO",
    "gerar_migration_card_hub",
]

ROLE_GRAVACAO = "gravacao"
ROLE_POSTADO = "postado"
ROLE_CANCELADO = "cancelado"

BUCKET_ESTEIRA = "sw-esteira"

#: By position; the entry stage is the first one.
ESTEIRA_PADRAO: tuple[StageDefault, ...] = (
    StageDefault("ideacao", "Ideação", "secondary"),
    StageDefault("headline_roteiro", "Headline + roteiro", "primary"),
    StageDefault("gravacao", "Gravação", "warning", ROLE_GRAVACAO),
    StageDefault("edicao", "Edição", "warning"),
    StageDefault("pronto", "Pronto", "success"),
    StageDefault("postado", "Postado", "success", ROLE_POSTADO),
    StageDefault("bloqueado_cancelado", "Bloqueado/cancelado", "destructive", ROLE_CANCELADO),
)

PIPELINE_ESTEIRA = PipelineConfig(
    pipeline="esteira",
    card_table="cs_posts",
    value_field="kanban_pos",
    entity_label="post",
    entity_label_plural="posts",
    entity_kind="cs_post",
    cliente_field=None,
    stage_roles=(ROLE_GRAVACAO, ROLE_POSTADO, ROLE_CANCELADO),
)

#: ``(tipo, categoria, retencao_dias, identidade, ativo, descricao)`` -- no identity
#: types: a post is not a person.
ESTEIRA_DOC_TIPOS: tuple[tuple, ...] = (
    ("referencia", "nao_classificado", 365, False, True, "Referências visuais e briefings"),
    ("outro", "nao_classificado", 365, False, True, "Outro documento"),
)

CS_POST_HUB = CardHubConfig(
    entity_kind="post",
    entity_label="Post",
    entity_table="cs_posts",
    entity_fk="post_id",
    id_param="post_id",
    table_prefix="cs_post",
    member_source=MemberSource(table="cs_equipe", fk="equipe_id", label="nome", cor="cor", body_field="membro_ids"),
    bucket=BUCKET_ESTEIRA,
    actor_resolver=table_reads.resolve_actors,
    timeline_gatherers={**SEED_GATHERERS, "movimento": gather_movimentos_esteira},
    entity_datas=True,
    lembretes_crud=True,
    stage_table="pipeline_stages",
    documentos=DocumentoPolicy(storage_segment="posts"),
)


def gerar_migration_card_hub() -> str:
    """The exact text between the ``GENERATED card_hub(post)`` markers of migration 241.

    Table policies use the org-picker-aware ``current_org_id_for`` (every SW migration after
    211 must; ``test_migration_211_org_picker_policies``)."""
    return card_hub_migration(
        CS_POST_HUB,
        "social_wiring",
        documento_tipos=ESTEIRA_DOC_TIPOS,
        org_id_expr="public.current_org_id_for('social_wiring')",
    )
