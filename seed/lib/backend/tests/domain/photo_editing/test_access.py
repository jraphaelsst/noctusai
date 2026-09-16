from __future__ import annotations

from noctusai_lib.domain.permissions import FakePermissionGrantRepository
from noctusai_lib.domain.photo_editing import Actor, EditType, OrgSettings, compute_capabilities

from .conftest import EDIT_MODEL, ORG, run

SETTINGS = OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,), modelo_editor_id=EDIT_MODEL)


def caps(actor, settings=SETTINGS, curators=()):
    grants = FakePermissionGrantRepository()
    for u in curators:
        grants.grant(u, "photo_curator")
    return run(compute_capabilities(actor=actor, settings=settings, grants=grants))


def test_corretor_never_sees_the_verdict() -> None:
    c = caps(Actor(user_id="c", org_id=ORG, org_role="corretor"))
    assert c["pode_criar_lote"] is True
    assert c["pode_ver_veredito"] is False
    assert c["pode_aprovar_regras"] is False
    assert c["dashboard"] is None


def test_agency_admin_and_platform_admin() -> None:
    admin = caps(Actor(user_id="a", org_id=ORG, org_role="owner"))
    assert (admin["pode_ver_veredito"], admin["pode_aprovar_regras"], admin["dashboard"]) == (
        True, True, "org")
    assert admin["pode_gerir_pool"] is False
    plat = caps(Actor(user_id="p", org_id=None, org_role=None, is_platform_admin=True))
    assert (plat["pode_gerir_pool"], plat["pode_ativar_guia"], plat["dashboard"]) == (
        True, True, "plataforma")


def test_curator_grant_manages_pool_only() -> None:
    cur = caps(Actor(user_id="k", org_id=ORG, org_role="member"), curators=["k"])
    assert (cur["pode_gerir_pool"], cur["pode_ativar_guia"], cur["pode_ver_veredito"]) == (
        True, True, False)


def test_no_model_blocks_batches_and_economico_is_locked() -> None:
    no_model = caps(Actor(user_id="a", org_id=ORG, org_role="admin"),
                    settings=OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,)))
    assert (no_model["pode_criar_lote"], no_model["modelo_configurado"]) == (False, False)
    assert no_model["economico_bloqueado_motivo"] == "sem_modelo"
    with_model = caps(Actor(user_id="a", org_id=ORG, org_role="admin"))
    # C8: no catalog image model supports Batch today.
    assert (with_model["economico_disponivel"], with_model["economico_bloqueado_motivo"]) == (
        False, "modelo_sem_batch")
    assert with_model["limites"] == {"fotos_por_lote": 100, "bytes_por_foto": 26214400}
    assert with_model["tipos_edicao_ativos"] == ["ceu"]


def test_outsider_role_cannot_create() -> None:
    assert caps(Actor(user_id="v", org_id=ORG, org_role="viewer"))["pode_criar_lote"] is False
