"""Business logic for the `card_hub` module — social-wiring's half of it.

The card's generic state (notas, tags, membros, checklists) is the seed's
`noctusai_lib.domain.card_hub.services`, lifted out of THIS file as a MOVE
(wave A, 2026-09-22 — the "lifting later must be a MOVE, not a rewrite" debt
recorded by `lead-card-hub-p2-PROJECT.md` D13/S3). The functions below keep
their historical `(client, org_id, cliente_id, ...)` signatures as thin
shims over it, bound to social-wiring's `CardHubConfig`
(`app.modules.card_hub.config.CARD_HUB`), so every caller in this product
reads unchanged. What genuinely stays here is social-wiring's own: which
atendimento a card-level write belongs to (`resolve_atendimento_id`), and the
shared read helpers the product's other card_hub services import.

`client` is always the `social_wiring`-scoped admin client from
`app.modules.card_hub.deps.get_card_hub_client` — every function here
accepts it as a parameter rather than resolving its own, so a single
request (and a single test) sees one consistent view of the mock/real
backend (see that dependency's docstring for why a second independently-
derived `.schema()` call would NOT see the same data).

Pagination: every unbounded read composes the canonical read helpers in
`app.services.table_reads` (PostgREST's 1 000-row cap + the `in_()`
URL-length limit). The `_t` / `_batched` / `_paged_rows` / `_resolve_actors`
/ `_actor` names below are aliases over those canonical definitions, so every
importer of them reads unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.card_hub import services as seed_svc
from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub.deps import card_hub_config
from app.services import table_reads

_PAGE_SIZE = table_reads.PAGE_SIZE
_IN_FILTER_BATCH = table_reads.IN_FILTER_BATCH


# ─── shared helpers ─────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── PostgREST read helpers — canonical definitions in `table_reads` ────
#
# The private names survive as aliases so every existing importer (the
# agendamentos / compradores / roteiros / documento-checklist services, ...)
# reads exactly as it did.

_t = table_reads.table
_batched = table_reads.batched
_paged_rows = table_reads.paged_rows
_in_batched_rows = table_reads.in_batched_rows
_resolve_actors = table_reads.resolve_actors
_actor = table_reads.actor


def ensure_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """The `clientes` row, or `NotFoundError("clientes", id)` — the seed's
    `ensure_entity` over `CARD_HUB.ensure_entity` (`clientes_service
    .get_cliente`)."""
    return seed_svc.ensure_entity(card_hub_config(), client, org_id, cliente_id)


# ─── Which atendimento does this belong to? ─────────────────────────────────
#
# Lives HERE rather than in the module that first needed it. It arrived with
# agendamentos, and compradores (migration 073) is the second caller asking the
# identical question — "this card is a person, but the thing I am attaching
# belongs to a DEAL; which one?". Two copies of that answer would disagree
# about archived and collapsed rows, which is the subtle half.
#
# `AmbiguousAtendimento` moves with it: the resolver's refusal is part of the
# resolver, and a caller that imports one without the other cannot handle what
# it raises. `agendamentos_service` re-exports both, so its existing importers
# and tests are untouched.


class AmbiguousAtendimento(AppException):
    """The person has more than one open atendimento, so "the" one is a guess.

    Raised rather than picking the newest: an appointment filed against the
    wrong deal renders identically on the card and is wrong in the one place
    D17 says matters — the history.

    An `AppException`, NOT a bare exception the router converts: the seed's
    handler renders `details` into the error envelope, so the candidate ids
    survive to the client. A `raise HTTPException(detail={...})` does NOT —
    the seed's HTTPException handler stringifies the detail into `message`,
    which is how the first version of this shipped a 409 the UI could not read.
    """

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        super().__init__(
            code="AMBIGUOUS_ATENDIMENTO",
            message=(
                "Este cliente tem mais de um atendimento aberto — escolha a qual "
                "o agendamento pertence."
                if candidates
                else "Este cliente não tem atendimento aberto — informe atendimento_id."
            ),
            status_code=409,
            details={"atendimentos": candidates},
        )


def _atendimentos_do_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    return _paged_rows(client, "atendimentos", org_id, eq_filters={"cliente_id": str(cliente_id)})


def resolve_atendimento_id(
    client: Any, org_id: UUID, cliente_id: UUID, explicit: Optional[UUID] = None
) -> str:
    """Which atendimento a new appointment belongs to.

    `explicit` wins and is validated against this cliente — accepting an
    unvalidated id would let a caller file an appointment onto someone else's
    deal. Otherwise: the single open atendimento, or `AmbiguousAtendimento`.
    """
    rows = _atendimentos_do_cliente(client, org_id, cliente_id)
    if explicit is not None:
        if not any(str(r["id"]) == str(explicit) for r in rows):
            raise NotFoundError("atendimentos", str(explicit))
        return str(explicit)

    abertos = [
        r for r in rows
        if r.get("substituida_por") is None and not r.get("arquivado", False)
    ]
    if len(abertos) == 1:
        return str(abertos[0]["id"])
    if not abertos:
        # Every atendimento is closed/archived. Refuse rather than resurrect
        # one — "which closed deal is this visit for?" is the user's call.
        raise AmbiguousAtendimento([])
    raise AmbiguousAtendimento([str(r["id"]) for r in abertos])


def tem_permuta_ativa(client: Any, org_id: UUID, atendimento_id: str) -> bool:
    """Does this atendimento have a `permuta`-type parcela? (P0c contract
    §E1/§H11 — a permuta comprador stands in a seller-like position for
    THAT parcela, so their side counts as `certificando` too.)

    A direct, lightweight read of `atendimento_negociacao_parcelas`
    (`card_hub.negociacao_estruturada_service`'s own table) rather than
    `contrato_gerador.dados.parcela_permuta`, which needs the WHOLE
    `DadosContrato` graph loaded — too heavy for a card-listing/checklist
    read. Single source for what used to be `empresas_service._tem_permuta`
    and `documento_checklist_service._tem_permuta`, an N=2 recurrence the
    recurrence rule flags at first sight — both call sites now import this
    one."""
    rows = (
        _t(client, "atendimento_negociacao_parcelas")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("tipo", "permuta")
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


# ─── Notas / tags / membros / checklists — shims over the seed ──────────
#
# Bodies: `noctusai_lib.domain.card_hub.services`. Two names differ there
# because the seed is not about a `cliente`: `set_cliente_tags` /
# `get_cliente_tags` are `set_entity_tags` / `get_entity_tags`, and
# `set_membros`' `lead_corretor_ids` is the generic `member_ids`.


def create_nota(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    corpo: str,
    autor_id: Optional[UUID],
    tipo: str = "comentario",
) -> dict:
    return seed_svc.create_nota(
        card_hub_config(), client, org_id, cliente_id, corpo=corpo, autor_id=autor_id, tipo=tipo
    )


def update_nota(client: Any, org_id: UUID, cliente_id: UUID, nota_id: UUID, *, corpo: str) -> dict:
    return seed_svc.update_nota(card_hub_config(), client, org_id, cliente_id, nota_id, corpo=corpo)


def get_descricao(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[dict]:
    return seed_svc.get_descricao(card_hub_config(), client, org_id, cliente_id)


def delete_nota(client: Any, org_id: UUID, cliente_id: UUID, nota_id: UUID) -> None:
    seed_svc.delete_nota(card_hub_config(), client, org_id, cliente_id, nota_id)


def list_tags(client: Any, org_id: UUID) -> dict:
    return seed_svc.list_tags(card_hub_config(), client, org_id)


def create_tag(client: Any, org_id: UUID, *, nome: str, cor: str) -> dict:
    return seed_svc.create_tag(card_hub_config(), client, org_id, nome=nome, cor=cor)


def update_tag(client: Any, org_id: UUID, tag_id: UUID, *, nome: Optional[str], cor: Optional[str]) -> dict:
    return seed_svc.update_tag(card_hub_config(), client, org_id, tag_id, nome=nome, cor=cor)


def delete_tag(client: Any, org_id: UUID, tag_id: UUID) -> None:
    seed_svc.delete_tag(card_hub_config(), client, org_id, tag_id)


def set_cliente_tags(
    client: Any, org_id: UUID, cliente_id: UUID, *, tag_ids: list[UUID], criado_por: Optional[UUID]
) -> dict:
    return seed_svc.set_entity_tags(
        card_hub_config(), client, org_id, cliente_id, tag_ids=tag_ids, criado_por=criado_por
    )


def get_cliente_tags(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    return seed_svc.get_entity_tags(card_hub_config(), client, org_id, cliente_id)


def get_membros(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    return seed_svc.get_membros(card_hub_config(), client, org_id, cliente_id)


def set_membros(client: Any, org_id: UUID, cliente_id: UUID, *, lead_corretor_ids: list[UUID]) -> dict:
    return seed_svc.set_membros(
        card_hub_config(), client, org_id, cliente_id, member_ids=lead_corretor_ids
    )


def list_checklists(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    return seed_svc.list_checklists(card_hub_config(), client, org_id, cliente_id)


def create_checklist(client: Any, org_id: UUID, cliente_id: UUID, *, titulo: str) -> dict:
    return seed_svc.create_checklist(card_hub_config(), client, org_id, cliente_id, titulo=titulo)


def update_checklist(
    client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID, *, titulo: Optional[str], posicao: Optional[int]
) -> dict:
    return seed_svc.update_checklist(
        card_hub_config(), client, org_id, cliente_id, checklist_id, titulo=titulo, posicao=posicao
    )


def delete_checklist(client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID) -> None:
    seed_svc.delete_checklist(card_hub_config(), client, org_id, cliente_id, checklist_id)


def create_checklist_item(
    client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID, *, texto: str
) -> dict:
    return seed_svc.create_checklist_item(
        card_hub_config(), client, org_id, cliente_id, checklist_id, texto=texto
    )


def update_checklist_item(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    checklist_id: UUID,
    item_id: UUID,
    *,
    texto: Optional[str],
    concluido: Optional[bool],
    posicao: Optional[int],
    concluido_por: Optional[UUID],
) -> dict:
    return seed_svc.update_checklist_item(
        card_hub_config(),
        client,
        org_id,
        cliente_id,
        checklist_id,
        item_id,
        texto=texto,
        concluido=concluido,
        posicao=posicao,
        concluido_por=concluido_por,
    )


def delete_checklist_item(
    client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID, item_id: UUID
) -> None:
    seed_svc.delete_checklist_item(card_hub_config(), client, org_id, cliente_id, checklist_id, item_id)


__all__ = [
    "AmbiguousAtendimento",
    "create_checklist",
    "create_checklist_item",
    "create_nota",
    "create_tag",
    "delete_checklist",
    "delete_checklist_item",
    "delete_nota",
    "delete_tag",
    "ensure_cliente",
    "get_cliente_tags",
    "get_descricao",
    "get_membros",
    "list_checklists",
    "list_tags",
    "resolve_atendimento_id",
    "set_cliente_tags",
    "set_membros",
    "tem_permuta_ativa",
    "update_checklist",
    "update_checklist_item",
    "update_nota",
    "update_tag",
]
