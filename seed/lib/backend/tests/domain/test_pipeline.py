"""Tests for `noctusai_lib.domain.pipeline` — user-editable stages + the one
card-move mechanic.

What these are actually protecting:

* **The rename guarantee.** The product requirement is "rename a stage and all
  past records follow". That holds only while cards reference the stage by ID.
  `test_rename_touches_no_card_row` fails the moment someone "optimises" by
  denormalising a label onto the card.
* **Role indirection.** The accept-proposal seam must resolve the stage by
  `papel`, never by name, or renaming a column breaks a feature elsewhere.
* **The history write.** This is the defect that motivated the extraction: two
  forked `mover-etapa` handlers, only one of which recorded transitions. The
  test asserts the row is written for a real move and NOT for a reorder.
* **Destructive guards.** Deleting a stage must not silently take the user's
  cards with it, and must not orphan a role.

Status-code-assertion-rule: these drive the domain layer directly, not HTTP.
The router's status codes are covered by the product's router tests.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.pipeline import (
    PipelineConfig,
    create_stage,
    delete_stage,
    group_into_colunas,
    list_stages,
    move_card,
    orphan_cards,
    reorder_stages,
    resolve_initial_stage,
    slugify,
    stage_by_role,
    update_stage,
)
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.testing.mocks import MockSupabaseClient

FUNIL = PipelineConfig(
    pipeline="funil",
    card_table="negociacoes_venda",
    value_field="valor_estimado",
    entity_label="negociação",
    entity_kind="negociacao_venda",
)

ORG = "org-1"


def _stage(sid, slug, label, posicao, papel=None, cor="secondary"):
    return {
        "id": sid,
        "org_id": ORG,
        "pipeline": "funil",
        "slug": slug,
        "label": label,
        "cor": cor,
        "posicao": posicao,
        "papel": papel,
        "ativo": True,
    }


DEFAULT_STAGES = [
    _stage("s1", "qualificacao", "Qualificação", 0),
    _stage("s2", "visitas", "Visitas", 1),
    _stage("s3", "proposta", "Proposta", 2, papel="proposta_aceite"),
    _stage("s4", "fechado", "Fechado", 3, papel="final"),
]


@pytest.fixture
def db():
    client = MockSupabaseClient(validate_schema=False, schema="erp")
    client.set_table_data("pipeline_stages", [dict(s) for s in DEFAULT_STAGES])
    client.set_table_data("pipeline_movimentos", [])
    client.set_table_data(
        "negociacoes_venda",
        [
            {"id": "n1", "cliente_id": "c1", "etapa_id": "s1", "kanban_pos": 0,
             "valor_estimado": 100},
            {"id": "n2", "cliente_id": "c2", "etapa_id": "s3", "kanban_pos": 0,
             "valor_estimado": 250},
            {"id": "n3", "cliente_id": "c3", "etapa_id": "s3", "kanban_pos": 1,
             "valor_estimado": 50},
        ],
    )
    return client


# ---------------------------------------------------------------------------
# slugify — the stable machine key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,expected",
    [
        ("Qualificação", "qualificacao"),
        ("Análise das Partes", "analise_das_partes"),
        ("Financiamento & Escritura", "financiamento_escritura"),
        ("  Em   Proposta  ", "em_proposta"),
        ("🔥", "etapa"),  # never empty — an empty slug breaks the UNIQUE key
    ],
)
def test_slugify_folds_accents_and_never_returns_empty(label, expected):
    assert slugify(label) == expected


# ---------------------------------------------------------------------------
# The rename guarantee
# ---------------------------------------------------------------------------

def test_rename_touches_no_card_row(db):
    """Renaming must write ONLY the stage row.

    If this ever fails because cards were updated too, the design has drifted
    to denormalising labels onto cards — at which point "all past records get
    edited" becomes a backfill that can miss rows.
    """
    update_stage(db, FUNIL, "s3", {"label": "Em Proposta"})

    assert db.table("negociacoes_venda").updated_payloads == []
    stage_updates = db.table("pipeline_stages").updated_payloads
    assert stage_updates == [{"label": "Em Proposta"}]


def test_role_survives_a_rename(db):
    """The accept seam resolves by role, so a rename cannot break it."""
    update_stage(db, FUNIL, "s3", {"label": "Qualquer Outro Nome"})
    db.set_table_data(
        "pipeline_stages",
        [{**s, "label": "Qualquer Outro Nome"} if s["id"] == "s3" else s
         for s in DEFAULT_STAGES],
    )

    found = stage_by_role(db, FUNIL, "proposta_aceite")
    assert found is not None
    assert found["id"] == "s3"
    assert found["slug"] == "proposta"  # slug is immutable


def test_slug_is_not_updatable(db):
    """`slug` is absent from the updatable whitelist — editing it is ignored."""
    update_stage(db, FUNIL, "s3", {"label": "Novo", "slug": "hackeado"})
    payload = db.table("pipeline_stages").updated_payloads[0]
    assert "slug" not in payload


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,fragment",
    [
        ({"label": "   "}, "vazio"),
        ({"label": "x" * 61}, "60 caracteres"),
        ({"label": "ok", "cor": "bg-[url(evil)]"}, "Cor inválida"),
        ({"label": "ok", "papel": "superstage"}, "Papel inválido"),
    ],
)
def test_create_rejects_bad_input(db, payload, fragment):
    with pytest.raises(AppException) as exc:
        create_stage(db, FUNIL, payload, org_id=ORG)
    assert fragment in exc.value.message


def test_create_rejects_duplicate_slug(db):
    with pytest.raises(AppException) as exc:
        create_stage(db, FUNIL, {"label": "Qualificação"}, org_id=ORG)
    assert "qualificacao" in exc.value.message


def test_create_rejects_second_stage_claiming_a_role(db):
    with pytest.raises(AppException) as exc:
        create_stage(db, FUNIL, {"label": "Outra", "papel": "final"}, org_id=ORG)
    assert "papel" in exc.value.message.lower()


def test_create_appends_to_the_end(db):
    create_stage(db, FUNIL, {"label": "Due Diligence"}, org_id=ORG)
    inserted = db.table("pipeline_stages").inserted_payloads[-1]
    assert inserted["posicao"] == 4          # max(0..3) + 1
    assert inserted["slug"] == "due_diligence"
    assert inserted["pipeline"] == "funil"
    assert inserted["org_id"] == ORG


# ---------------------------------------------------------------------------
# Deletion guards
# ---------------------------------------------------------------------------

def test_delete_refuses_a_stage_carrying_a_role(db):
    with pytest.raises(AppException) as exc:
        delete_stage(db, FUNIL, "s3")
    assert "papel" in exc.value.message


def test_delete_refuses_when_cards_present_and_no_target(db):
    """s1 holds n1. Deleting without a target must refuse, and say how many."""
    with pytest.raises(AppException) as exc:
        delete_stage(db, FUNIL, "s1")
    assert "1 negociação" in exc.value.message


def test_delete_reassigns_cards_before_removing(db):
    result = delete_stage(db, FUNIL, "s1", reassign_to="s2")
    assert result["cards_movidos"] == 1
    assert db.table("negociacoes_venda").updated_payloads == [{"etapa_id": "s2"}]


def test_delete_refuses_to_empty_the_funnel(db):
    db.set_table_data("pipeline_stages", [_stage("only", "unica", "Única", 0)])
    db.set_table_data("negociacoes_venda", [])
    with pytest.raises(AppException) as exc:
        delete_stage(db, FUNIL, "only")
    assert "pelo menos uma etapa" in exc.value.message


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

def test_reorder_rewrites_positions_in_the_given_order(db):
    reorder_stages(db, FUNIL, ["s3", "s1", "s2", "s4"])
    assert db.table("pipeline_stages").updated_payloads == [
        {"posicao": 0}, {"posicao": 1}, {"posicao": 2}, {"posicao": 3}
    ]


@pytest.mark.parametrize(
    "ordem,fragment",
    [
        ([], "ordem completa"),
        (["s1", "s1", "s2", "s3"], "repetidas"),
        (["s1", "s2"], "todas as etapas"),
        (["s1", "s2", "s3", "nope"], "desconhecidas"),
    ],
)
def test_reorder_rejects_incomplete_or_bogus_order(db, ordem, fragment):
    with pytest.raises(AppException) as exc:
        reorder_stages(db, FUNIL, ordem)
    assert fragment in exc.value.message


# ---------------------------------------------------------------------------
# move_card — the mechanic, and the history write that used to be missing
# ---------------------------------------------------------------------------

def test_move_writes_a_history_row(db):
    logged = []
    move_card(
        db, FUNIL,
        card_id="n1", to_stage_id="s3", user_id="u1", novo_indice=0,
        motivo="cliente aceitou visita",
        log_action=lambda *a, **k: logged.append(a),
    )

    history = db.table("pipeline_movimentos").inserted_payloads
    assert len(history) == 1
    assert history[0] == {
        "pipeline": "funil",
        "entidade_id": "n1",
        "de_etapa_id": "s1",
        "para_etapa_id": "s3",
        "responsavel_id": "u1",
        "motivo": "cliente aceitou visita",
        "cliente_id": "c1",
    }
    # entity kind is the pipeline's own, not a hardcoded "cliente"
    assert logged[0][2] == "negociacao_venda"


def test_move_within_the_same_stage_writes_no_history(db):
    """A reorder is not a transition; recording it would drown the real ones."""
    move_card(db, FUNIL, card_id="n2", to_stage_id="s3", user_id="u1", novo_indice=1)
    assert db.table("pipeline_movimentos").inserted_payloads == []
    # ...but the position change still persists
    assert {"etapa_id": "s3", "kanban_pos": 1} in db.table(
        "negociacoes_venda"
    ).updated_payloads


def test_move_to_unknown_stage_404s(db):
    with pytest.raises(AppException) as exc:
        move_card(db, FUNIL, card_id="n1", to_stage_id="ghost", user_id="u1")
    assert exc.value.status_code == 404


def test_move_accepts_extra_updates_for_legacy_columns(db):
    move_card(
        db, FUNIL, card_id="n1", to_stage_id="s3", user_id="u1",
        extra_updates={"etapa": "proposta"},
    )
    assert db.table("negociacoes_venda").updated_payloads[0]["etapa"] == "proposta"


# ---------------------------------------------------------------------------
# Board grouping
# ---------------------------------------------------------------------------

def test_group_emits_every_stage_including_empty_ones(db):
    rows = db.table("negociacoes_venda").select("*").execute().data
    colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows)

    assert [c["etapa"] for c in colunas] == ["s1", "s2", "s3", "s4"]
    assert [c["total"] for c in colunas] == [1, 0, 2, 0]
    assert colunas[2]["valorTotal"] == 300.0
    assert colunas[1]["cards"] == []
    # the column carries its stage definition so the UI needs no second lookup
    assert colunas[0]["stage"]["label"] == "Qualificação"


def test_group_orders_cards_by_kanban_pos(db):
    rows = db.table("negociacoes_venda").select("*").execute().data
    colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows)
    proposta = next(c for c in colunas if c["etapa"] == "s3")
    assert [c["id"] for c in proposta["cards"]] == ["n2", "n3"]


def test_recency_stage_sorts_newest_first_ignoring_kanban_pos():
    """The intake column answers "what just arrived" — `kanban_pos` is not it."""
    rows = [
        {"id": "old", "etapa_id": "s1", "kanban_pos": 0, "created_at": "2026-01-01T00:00:00Z"},
        {"id": "new", "etapa_id": "s1", "kanban_pos": 9, "created_at": "2026-09-02T00:00:00Z"},
        {"id": "mid", "etapa_id": "s1", "kanban_pos": 1, "created_at": "2026-05-01T00:00:00Z"},
    ]
    colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows, recency_first_stages={"s1"})
    # kanban_pos would have said old, mid, new — recency says the reverse.
    assert [c["id"] for c in colunas[0]["cards"]] == ["new", "mid", "old"]


def test_recency_leaves_every_other_column_hand_ordered():
    """Opting one stage in must not silently reorder the rest of the board."""
    rows = [
        {"id": "a", "etapa_id": "s3", "kanban_pos": 0, "created_at": "2026-01-01T00:00:00Z"},
        {"id": "b", "etapa_id": "s3", "kanban_pos": 1, "created_at": "2026-09-02T00:00:00Z"},
    ]
    colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows, recency_first_stages={"s1"})
    proposta = next(c for c in colunas if c["etapa"] == "s3")
    # Newest is `b`, but s3 is NOT a recency stage — kanban_pos still rules.
    assert [c["id"] for c in proposta["cards"]] == ["a", "b"]


def test_recency_is_opt_in_default_is_unchanged():
    """No `recency_first_stages` ⇒ byte-identical to the pre-seam behaviour,
    which is what keeps every other product consuming this organ untouched."""
    rows = [
        {"id": "old", "etapa_id": "s1", "kanban_pos": 0, "created_at": "2026-01-01T00:00:00Z"},
        {"id": "new", "etapa_id": "s1", "kanban_pos": 9, "created_at": "2026-09-02T00:00:00Z"},
    ]
    colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows)
    assert [c["id"] for c in colunas[0]["cards"]] == ["old", "new"]


def test_recency_truncation_keeps_the_newest_not_an_arbitrary_window():
    """🔴 The reason this lives server-side: `limite_cards` cuts AFTER the
    sort, so the first N of a recency column are the N NEWEST cards. A
    client-side sort could only reorder whatever window the server sent."""
    rows = [
        {"id": f"c{i}", "etapa_id": "s1", "kanban_pos": i, "created_at": f"2026-01-{i + 1:02d}T00:00:00Z"}
        for i in range(5)
    ]
    colunas = group_into_colunas(
        FUNIL, DEFAULT_STAGES, rows, recency_first_stages={"s1"}, limite_cards=2
    )
    assert [c["id"] for c in colunas[0]["cards"]] == ["c4", "c3"]
    # `total` still counts the whole column — the display limit is not a
    # silent under-report (the invariant the docstring calls out).
    assert colunas[0]["total"] == 5


def test_recency_card_without_created_at_sorts_last_not_crashes():
    rows = [
        {"id": "sem-data", "etapa_id": "s1", "kanban_pos": 0},
        {"id": "com-data", "etapa_id": "s1", "kanban_pos": 1, "created_at": "2026-01-01T00:00:00Z"},
    ]
    colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows, recency_first_stages={"s1"})
    assert [c["id"] for c in colunas[0]["cards"]] == ["com-data", "sem-data"]


def test_orphan_cards_are_reported_not_silently_dropped():
    rows = [{"id": "x", "etapa_id": "deleted-stage", "valor_estimado": 1}]
    assert group_into_colunas(FUNIL, DEFAULT_STAGES, rows)[0]["total"] == 0
    assert [r["id"] for r in orphan_cards(DEFAULT_STAGES, rows)] == ["x"]


# ---------------------------------------------------------------------------
# Initial stage — derived from order, not hardcoded
# ---------------------------------------------------------------------------

def test_initial_stage_follows_the_configured_order(db):
    assert resolve_initial_stage(db, FUNIL)["id"] == "s1"

    reordered = [
        {**_stage("s3", "proposta", "Proposta", 0, papel="proposta_aceite")},
        {**_stage("s1", "qualificacao", "Qualificação", 1)},
    ]
    db.set_table_data("pipeline_stages", reordered)
    assert resolve_initial_stage(db, FUNIL)["id"] == "s3"


def test_initial_stage_on_an_unconfigured_pipeline_fails_loudly(db):
    db.set_table_data("pipeline_stages", [])
    with pytest.raises(AppException) as exc:
        resolve_initial_stage(db, FUNIL)
    assert "nenhuma etapa configurada" in exc.value.message


def test_list_stages_is_ordered_and_hides_inactive_by_default(db):
    db.set_table_data(
        "pipeline_stages",
        [
            _stage("b", "b", "B", 5),
            _stage("a", "a", "A", 1),
            {**_stage("z", "z", "Z", 2), "ativo": False},
        ],
    )
    assert [s["id"] for s in list_stages(db, FUNIL)] == ["a", "b"]
    assert [s["id"] for s in list_stages(db, FUNIL, incluir_inativas=True)] == [
        "a", "z", "b"
    ]


# ---------------------------------------------------------------------------
# Deactivation is a SOFT DELETE — same invariants as the hard one
# ---------------------------------------------------------------------------
# The board lists only ACTIVE stages, so flipping `ativo` off is
# indistinguishable, from the user's seat, from deleting the column: the cards
# stop being on the board. `delete_stage` guards all three cases below;
# `update_stage` guarded none of them, so the careful path could be bypassed by
# editing a stage instead of deleting it.

def test_deactivating_a_stage_holding_cards_is_refused(db):
    # s2 is role-less, so the card guard is what must fire (the role guard is
    # exercised separately below). Before this, these two cards silently
    # vanished from the board.
    db.set_table_data(
        "negociacoes_venda",
        [
            {"id": "n1", "etapa_id": "s2", "kanban_pos": 0, "valor_estimado": 100},
            {"id": "n2", "etapa_id": "s2", "kanban_pos": 1, "valor_estimado": 250},
        ],
    )
    with pytest.raises(AppException) as exc:
        update_stage(db, FUNIL, "s2", {"ativo": False})
    assert "2 negociações" in str(exc.value)


def test_the_role_guard_reads_the_STORED_stage_not_the_payload(db):
    # Clearing the role in the same write must NOT unlock the deactivation:
    # the payload is a request, the stored row is the fact. Same posture as
    # `delete_stage`, which requires the role reassigned in a prior write.
    with pytest.raises(AppException) as exc:
        update_stage(db, FUNIL, "s3", {"ativo": False, "papel": None})
    assert "papel" in str(exc.value)


def test_the_refusal_names_the_stage_and_pluralises(db):
    db.set_table_data(
        "negociacoes_venda",
        [{"id": "n1", "etapa_id": "s2", "kanban_pos": 0, "valor_estimado": 1}],
    )
    with pytest.raises(AppException) as exc:
        update_stage(db, FUNIL, "s2", {"ativo": False})
    message = str(exc.value)
    assert "Visitas" in message and "1 negociação" in message


def test_deactivating_a_role_carrying_stage_is_refused(db):
    # Retiring "Proposta" would remove the accept seam exactly as deleting it
    # would — features key on the ROLE, and the role does not care how the
    # stage left the board.
    db.set_table_data("negociacoes_venda", [])
    with pytest.raises(AppException) as exc:
        update_stage(db, FUNIL, "s3", {"ativo": False})
    assert "papel" in str(exc.value)


def test_deactivating_the_last_active_stage_is_refused(db):
    db.set_table_data("negociacoes_venda", [])
    db.set_table_data("pipeline_stages", [dict(DEFAULT_STAGES[0])])
    with pytest.raises(AppException) as exc:
        update_stage(db, FUNIL, "s1", {"ativo": False})
    assert "pelo menos uma etapa ativa" in str(exc.value)


def test_an_empty_roleless_stage_can_still_be_retired(db):
    # The legitimate use: retire a stage that is already empty so its history
    # stays readable. This is what social-wiring migration 037 did to the
    # superseded "Qualificado" stage.
    db.set_table_data("negociacoes_venda", [])
    assert update_stage(db, FUNIL, "s2", {"ativo": False})["ativo"] is False


def test_reactivating_is_never_guarded(db):
    # Only the deactivation direction can strand a card.
    db.set_table_data("negociacoes_venda", [])
    update_stage(db, FUNIL, "s2", {"ativo": False})
    assert update_stage(db, FUNIL, "s2", {"ativo": True})["ativo"] is True


def test_orphan_cards_are_logged_by_the_board_not_just_computed(db, caplog):
    """The net has to be WIRED. It was exported and unit-tested but called by
    nothing, so the condition it exists to surface was in fact silent."""
    import logging

    rows = [{"id": "ghost", "etapa_id": "deleted-stage", "kanban_pos": 0}]
    with caplog.at_level(logging.WARNING):
        colunas = group_into_colunas(FUNIL, DEFAULT_STAGES, rows)

    assert "ghost" in caplog.text
    # ...and the board still renders. Failing it outright would turn one
    # misplaced card into a total outage.
    assert len(colunas) == len(DEFAULT_STAGES)


# ---------------------------------------------------------------------------
# pt-BR pluralisation in user-facing messages
# ---------------------------------------------------------------------------
# The organ appended a bare "s", so both boards told users they had
# "2 negociaçãos". Correct for "processo", broken for the other one.

@pytest.mark.parametrize(
    "label,total,expected",
    [
        ("negociação", 1, "1 negociação"),
        ("negociação", 2, "2 negociações"),
        ("processo", 1, "1 processo"),
        ("processo", 3, "3 processos"),
        ("cliente", 2, "2 clientes"),
        ("lead", 2, "2 leads"),
        ("contrato", 0, "0 contratos"),
    ],
)
def test_count_label_pluralises_pt_br(label, total, expected):
    cfg = PipelineConfig(
        pipeline="p", card_table="t", value_field="v",
        entity_label=label, entity_kind="k",
    )
    assert cfg.count_label(total) == expected


def test_an_explicit_plural_overrides_the_derivation():
    cfg = PipelineConfig(
        pipeline="p", card_table="t", value_field="v",
        entity_label="proposta", entity_kind="k", entity_label_plural="propostas enviadas",
    )
    assert cfg.count_label(2) == "2 propostas enviadas"


def test_the_delete_message_uses_it_too(db):
    # The pre-existing bug this fixes lived in `delete_stage`, not only in the
    # deactivation guard added alongside it.
    with pytest.raises(AppException) as exc:
        delete_stage(db, FUNIL, "s1")
    assert "1 negociação" in str(exc.value) and "negociaçãos" not in str(exc.value)
