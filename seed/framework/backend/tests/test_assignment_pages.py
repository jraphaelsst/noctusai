"""The assignment page-key contract: the BE `PageSpec`s equal the FE `assignment/pages.tsx` constants (parsed, not imported),
a module can carry them, and the organ is mountable with a custom strategy hook through the seed `mount_assignment`."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_seed.modules import ModuleSpec, module_manifest
from noctusai_seed.modules.assignment import (
    ASSIGNMENT_DEFAULT_LABELS,
    ASSIGNMENT_DEFAULT_PATHS,
    ASSIGNMENT_PAGE_KEYS,
    assignment_pages,
)
from noctusai_seed.organs import mount_assignment, mount_organs

FE = Path(__file__).resolve().parents[3] / "lib" / "frontend" / "src" / "assignment" / "pages.tsx"


def _fe_const(name: str) -> dict[str, str]:
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", FE.read_text(encoding="utf-8"), re.S)
    assert body, f"{name} not found in {FE}"
    return dict(re.findall(r"(\w+):\s*'([^']*)'", body.group(1)))


def test_the_be_page_specs_equal_the_fe_constants():
    assert dict(ASSIGNMENT_PAGE_KEYS) == _fe_const("ASSIGNMENT_PAGE_KEYS")
    assert dict(ASSIGNMENT_DEFAULT_PATHS) == _fe_const("ASSIGNMENT_DEFAULT_PATHS")
    assert dict(ASSIGNMENT_DEFAULT_LABELS) == _fe_const("ASSIGNMENT_DEFAULT_LABELS")


def test_a_module_carries_the_two_pages_and_the_manifest_lists_them():
    crm = ModuleSpec(key="crm", pages=assignment_pages())
    assert crm.page_keys == ("crm_distribuicao", "crm_equipes")
    pages = module_manifest([crm])["modules"][0]["pages"]
    assert [(p["key"], p["path"], p["label"], p["status"]) for p in pages] == [
        ("crm_distribuicao", "/crm/distribuicao", "Distribuição", "producao"),
        ("crm_equipes", "/crm/equipes", "Equipes", "producao"),
    ]


def test_a_market_may_move_or_relabel_a_page_but_not_name_one_that_does_not_exist():
    moved = assignment_pages(paths={"rules": "/crm/vendas/distribuicao"}, labels={"teams": "Times"}, status="desenvolvimento")
    assert [(p.path, p.label, p.status) for p in moved] == [("/crm/vendas/distribuicao", "Distribuição", "desenvolvimento"), ("/crm/equipes", "Times", "desenvolvimento")]
    with pytest.raises(ValueError, match="unknown pages"):
        assignment_pages(paths={"nope": "/x"})


def test_the_seed_mount_wires_the_router_with_org_auth_and_a_custom_strategy_hook_is_selectable():
    """`mount_assignment` builds the router over the host's clients; a hook name is accepted, a builtin name is refused at construction."""
    calls = {"admin": 0}

    async def auth(authorization: str | None = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="no auth")
        return (SimpleNamespace(id="u1"), "tok", "11111111-1111-4111-8111-111111111111")

    def admin_client():
        calls["admin"] += 1
        raise AssertionError("a 401 must stop before any client is built")

    organ = mount_assignment(
        schema="asgx", auth_dependency=auth, get_admin_client=admin_client, get_core_client=admin_client, strategy_hooks={"by_plantao": lambda s, c: None},
    )
    assert organ.name == "assignment"
    routers, _overrides = mount_organs([organ])
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    client = TestClient(app)
    assert client.get("/api/assignment/teams").status_code == 401
    assert client.post("/api/assignment/assign", json={"subject_kind": "card", "subject_id": "c" * 8}).status_code == 401
    assert calls["admin"] == 0
    assert mount_assignment.__name__ == "mount_assignment"


def test_mount_refuses_a_cfg_for_another_schema():
    from noctusai_lib.domain.assignment import AssignmentConfig

    with pytest.raises(ValueError, match="cfg.schema"):
        mount_assignment(schema="a", auth_dependency=lambda: None, get_admin_client=lambda: None, get_core_client=lambda: None, cfg=AssignmentConfig(schema="b"))
