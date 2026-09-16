from __future__ import annotations

import pytest

from noctusai_lib.domain.photo_editing import (
    Actor,
    CommentRequiredError,
    Decision,
    InvalidModelOutputError,
    PhotoNotDecidableError,
    PhotoStatus,
    RuleDecisionForbiddenError,
    RuleNotFoundError,
    RuleStatus,
    Speed,
    decide_rule,
    propose_rules,
    record_decision,
)
from noctusai_lib.domain.photo_editing.types import JobType

from .conftest import ORG, USER, run

ADMIN = Actor(user_id="adm", org_id=ORG, org_role="manager")
CORRETOR = Actor(user_id="cor", org_id=ORG, org_role="corretor")
OTHER_ADMIN = Actor(user_id="x", org_id="org-2", org_role="owner")
PLATFORM = Actor(user_id="plat", org_id=None, org_role=None, is_platform_admin=True)


async def _review_ready_photo(ports, n: int = 1):
    batch = await ports.repo.create_batch(org_id=ORG, nome="L", criado_por=USER,
                                          origem="upload", velocidade=Speed.URGENTE)
    await ports.repo.update_batch(batch.id, guia_efetivo_sha256="sha-guia")
    photos = []
    for i in range(n):
        p = await ports.repo.add_photo(org_id=ORG, lote_id=batch.id, ordem=i + 1,
                                       storage_path_original=f"p{i}")
        for target in (PhotoStatus.NORMALIZANDO, PhotoStatus.PRONTA, PhotoStatus.EDITANDO,
                       PhotoStatus.EDITADA, PhotoStatus.AVALIANDO, PhotoStatus.AGUARDANDO_DECISAO):
            p = await ports.repo.transition_photo(p.id, target)
        photos.append(p)
    return batch, photos


def test_reject_requires_comment(ports) -> None:
    async def scenario() -> None:
        _, (p,) = await _review_ready_photo(ports)
        for blank in (None, "", "   "):
            with pytest.raises(CommentRequiredError):
                await record_decision(ports, foto_id=p.id, decisao=Decision.REJEITAR,
                                      comentario=blank, decidido_por=USER)
        assert ports.repo.decisions == []

    run(scenario())


def test_decision_appends_decision_and_dataset_and_feeds_learning(ports) -> None:
    async def scenario() -> None:
        _, (p,) = await _review_ready_photo(ports)
        out = await record_decision(ports, foto_id=p.id, decisao=Decision.REJEITAR,
                                    comentario="  céu falso ", decidido_por=USER)
        assert out.photo.status is PhotoStatus.REJEITADA
        assert out.decision.comentario == "céu falso"
        rec = ports.repo.dataset[0]
        assert (rec.decisao_final, rec.guia_efetivo_sha256, rec.comentario) == (
            Decision.REJEITAR, "sha-guia", "céu falso")
        assert rec.avaliacao_score is None  # no evaluation stored for this photo
        assert (await ports.repo.get_cursor(ORG)).rejeicoes_desde_ultima == 1
        jobs = [j for j in ports.jobs._jobs.values() if j.type == JobType.PROPOR_REGRAS]
        assert len(jobs) == 1 and jobs[0].scheduled_for > ports.clock()

        # Changeable: same photo approved later → second append, never an update.
        await record_decision(ports, foto_id=p.id, decisao=Decision.APROVAR,
                              comentario=None, decidido_por=USER)
        assert len(ports.repo.decisions) == 2 and len(ports.repo.dataset) == 2
        latest = await ports.repo.latest_decisions(p.lote_id)
        assert latest[p.id].decisao is Decision.APROVAR
        # Re-affirming the same decision is legal (no illegal self-transition).
        await record_decision(ports, foto_id=p.id, decisao=Decision.APROVAR,
                              comentario=None, decidido_por=USER)

    run(scenario())


def test_cannot_decide_before_review(ports) -> None:
    async def scenario() -> None:
        batch = await ports.repo.create_batch(org_id=ORG, nome="L", criado_por=USER,
                                              origem="upload", velocidade=Speed.URGENTE)
        p = await ports.repo.add_photo(org_id=ORG, lote_id=batch.id, ordem=1,
                                       storage_path_original="p")
        with pytest.raises(PhotoNotDecidableError):
            await record_decision(ports, foto_id=p.id, decisao=Decision.APROVAR,
                                  comentario=None, decidido_por=USER)

    run(scenario())


def _script_rules(ports, regras):
    ports.llm.responses["propor_regras"] = {"regras": regras}


def test_propose_rules_from_rejections_with_cursor(ports, clock) -> None:
    async def scenario() -> None:
        _, photos = await _review_ready_photo(ports, n=3)
        for p, c in zip(photos, ["céu roxo", "sumiu o sofá", "ok"]):
            clock.advance(seconds=1)
            await record_decision(ports, foto_id=p.id, decisao=Decision.REJEITAR,
                                  comentario=c, decidido_por=USER)
        _script_rules(ports, [
            {"texto": "Não usar céu roxo", "comentarios": [1]},
            {"texto": "Não remover móveis", "comentarios": [2]},
        ])
        created = await propose_rules(ports, ORG)
        assert [r.texto for r in created] == ["Não usar céu roxo", "Não remover móveis"]
        assert all(r.status is RuleStatus.PROPOSTA for r in created)
        assert created[1].origem_comentarios[0]["comentario"] == "sumiu o sofá"
        call = ports.llm.calls[-1]
        assert call["images"] == [] and "3. ok" in call["prompt"]
        cursor = await ports.repo.get_cursor(ORG)
        assert cursor.rejeicoes_desde_ultima == 0
        assert cursor.ultima_decisao_id == ports.repo.decisions[-1].id
        # Rule-proposer cost lands on the org's ledger.
        assert [c.category for c in ports.repo.costs.values()] == ["openai_text"]

        # Nothing new ⇒ no call.
        n_calls = len(ports.llm.calls)
        assert await propose_rules(ports, ORG) == []
        assert len(ports.llm.calls) == n_calls

        # New rejection; a duplicate proposal of an existing rule is skipped.
        clock.advance(seconds=1)
        await record_decision(ports, foto_id=photos[2].id, decisao=Decision.REJEITAR,
                              comentario="céu roxo de novo", decidido_por=USER)
        _script_rules(ports, [{"texto": "não usar céu roxo ", "comentarios": [1]}])
        assert await propose_rules(ports, ORG) == []
        assert "- Não usar céu roxo" in ports.llm.calls[-1]["prompt"]

    run(scenario())


@pytest.mark.parametrize(
    "bad",
    [
        {"regras": "x"},
        {"regras": [{"texto": "", "comentarios": [1]}]},
        {"regras": [{"texto": "Não", "comentarios": [9]}]},
        {"regras": [{"texto": "Não", "comentarios": ["1"]}]},
    ],
)
def test_malformed_proposals_are_retryable_errors(ports, bad) -> None:
    async def scenario() -> None:
        _, (p,) = await _review_ready_photo(ports)
        await record_decision(ports, foto_id=p.id, decisao=Decision.REJEITAR,
                              comentario="c", decidido_por=USER)
        ports.llm.responses["propor_regras"] = bad
        with pytest.raises(InvalidModelOutputError):
            await propose_rules(ports, ORG)
        assert ports.repo.rules == {}

    run(scenario())


def test_rule_decision_authority(ports) -> None:
    async def scenario() -> None:
        r = await ports.repo.add_rule(org_id=ORG, texto="Não X", origem_comentarios=())
        with pytest.raises(RuleDecisionForbiddenError):
            await decide_rule(ports, r.id, approve=True, actor=CORRETOR)
        with pytest.raises(RuleDecisionForbiddenError):
            await decide_rule(ports, r.id, approve=True, actor=OTHER_ADMIN)
        approved = await decide_rule(ports, r.id, approve=True, actor=ADMIN)
        assert (approved.status, approved.override_platform_admin) == (RuleStatus.APROVADA, False)
        assert (await decide_rule(ports, r.id, approve=True, actor=ADMIN)) == approved
        # Only the platform admin can flip an agency admin's decision.
        with pytest.raises(RuleDecisionForbiddenError):
            await decide_rule(ports, r.id, approve=False, actor=ADMIN)
        flipped = await decide_rule(ports, r.id, approve=False, actor=PLATFORM)
        assert (flipped.status, flipped.override_platform_admin, flipped.decidido_por) == (
            RuleStatus.REJEITADA, True, "plat")
        with pytest.raises(RuleNotFoundError):
            await decide_rule(ports, "nope", approve=True, actor=PLATFORM)

    run(scenario())
