from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.photo_editing import (
    GuideNotActiveError,
    GuideVersionNotFoundError,
    activate_version,
    compose_effective_guide,
    create_draft,
    generate_draft_from_pool,
    resolve_effective_guide,
    restore_version,
)
from noctusai_lib.domain.photo_editing.types import (
    GuideStatus,
    OrgRule,
    ReferencePair,
    Room,
    RuleStatus,
    StyleGuide,
    sha256_text,
)

from .conftest import ORG, USER, activate_guide, run

G = StyleGuide(id="g1", versao=3, texto="- Luz natural  \r\n- Céu azul\n", sha256="x")


def rule(rid: str, texto: str, status=RuleStatus.APROVADA, minute=0) -> OrgRule:
    return OrgRule(id=rid, org_id=ORG, texto=texto, status=status,
                   decidido_em=datetime(2026, 9, 1, 12, minute, tzinfo=timezone.utc))


def test_compose_is_deterministic_and_order_independent() -> None:
    r1, r2 = rule("r1", "Não escurecer", minute=1), rule("r2", "Não remover plantas", minute=2)
    a = compose_effective_guide(G, [r2, r1])
    b = compose_effective_guide(G, [r1, r2])
    assert a == b
    assert a.sha256 == sha256_text(a.texto)
    assert a.regra_ids == ("r1", "r2")
    assert a.texto == (
        "# Guia de estilo da empresa (versão 3)\n\n- Luz natural\n- Céu azul\n\n"
        "# Regras desta imobiliária (não faça)\n1. Não escurecer\n2. Não remover plantas\n"
    )


def test_only_approved_rules_are_included() -> None:
    composed = compose_effective_guide(
        G, [rule("r1", "A", RuleStatus.PROPOSTA), rule("r2", "B", RuleStatus.REJEITADA)]
    )
    assert composed.regra_ids == ()
    assert "Regras" not in composed.texto


def test_resolve_requires_an_active_guide(ports) -> None:
    with pytest.raises(GuideNotActiveError):
        run(resolve_effective_guide(ports, ORG))


def test_resolve_versions_rule_sets_and_is_idempotent(ports) -> None:
    async def scenario() -> None:
        await activate_guide(ports)
        first = await resolve_effective_guide(ports, ORG)
        assert first.conjunto_regras_id is None
        again = await resolve_effective_guide(ports, ORG)
        assert again.id == first.id

        r = await ports.repo.add_rule(org_id=ORG, texto="Não escurecer", origem_comentarios=())
        await ports.repo.update_rule(r.id, status=RuleStatus.APROVADA, decidido_por=USER,
                                     decidido_em=ports.clock(), override_platform_admin=False)
        with_rule = await resolve_effective_guide(ports, ORG)
        assert with_rule.sha256 != first.sha256
        assert "1. Não escurecer" in with_rule.texto
        assert [s.versao for s in ports.repo.rule_sets] == [1]
        await resolve_effective_guide(ports, ORG)
        assert [s.versao for s in ports.repo.rule_sets] == [1]  # unchanged set ⇒ no new version
        # Other orgs never see this org's rules.
        other = await resolve_effective_guide(ports, "org-2")
        assert "Não escurecer" not in other.texto

    run(scenario())


def test_versions_are_immutable_restore_clones_activation_swaps(ports) -> None:
    async def scenario() -> None:
        v1 = await create_draft(ports, texto="um", gerado_de_versao=None, criado_por=USER)
        v2 = await create_draft(ports, texto="dois", gerado_de_versao=1, criado_por=USER)
        assert (v1.versao, v2.versao, v1.status) == (1, 2, GuideStatus.RASCUNHO)
        await activate_version(ports, 1, ativado_por=USER)
        await activate_version(ports, 2, ativado_por=USER)
        assert (await ports.repo.get_guide(1)).status is GuideStatus.SUBSTITUIDA
        assert (await ports.repo.get_active_guide()).versao == 2
        v3 = await restore_version(ports, 1, criado_por=USER)
        assert (v3.versao, v3.texto, v3.gerado_de_versao, v3.status) == (
            3, "um\n", 1, GuideStatus.RASCUNHO)
        with pytest.raises(GuideVersionNotFoundError):
            await restore_version(ports, 99, criado_por=USER)
        with pytest.raises(GuideVersionNotFoundError):
            await activate_version(ports, 99, ativado_por=USER)
        with pytest.raises(ValueError):
            await ports.repo.create_guide(versao=1, texto="x", sha256="x",
                                          gerado_de_versao=None, criado_por=None)

    run(scenario())


def test_generate_draft_from_pool(ports) -> None:
    async def scenario() -> None:
        assert await generate_draft_from_pool(ports) is None  # empty pool
        assert ports.llm.calls == []
        for i in range(3):
            ports.repo.seed_reference(ReferencePair(
                id=f"r{i}", antes_url=f"https://x/a{i}", depois_url=f"https://x/d{i}",
                comodo=Room.SALA, criado_por=USER))
        ports.repo.references["r0"] = ports.repo.references["r0"].__class__(
            **{**ports.repo.references["r0"].__dict__, "arquivado_em": ports.clock()})
        draft = await generate_draft_from_pool(ports.with_config(max_reference_pairs_per_guide=5))
        assert draft.versao == 1 and draft.status is GuideStatus.RASCUNHO
        assert draft.criado_por is None
        call = ports.llm.calls[-1]
        assert call["org_id"] is None and call["model"] == "gpt-5.6-sol"
        assert len(call["images"]) == 4  # 2 active pairs; archived excluded

    run(scenario())


def test_generate_draft_rejects_empty_answer(ports) -> None:
    ports.llm.responses["guia_estilo"] = {"guia": "   "}
    ports.repo.seed_reference(ReferencePair(id="r", antes_url="a", depois_url="d",
                                            comodo=Room.OUTRO, criado_por=USER))
    with pytest.raises(ValueError):
        run(generate_draft_from_pool(ports))
