"""``GET /api/agent-packages/{key}/versions`` and ``/{key}/{versao}`` — serve a
published dev-advisor package (Agent Packages §I).

Scope ``packages:read`` for a ``pk_*`` token, any org member for a user. The
tree served is the one the build produced (``dist/claude/``), stored on the
version at import time (017 ``agent_package_trees``) — it carries the
package's ``LEARNINGS.md`` / ``PACKAGE.json``, which cannot be re-derived from
the Studio rows. Only ``dev-advisor`` agents are packages: a runtime agent
(IsaIA, Julia) is a 404 here, so a ``packages:read`` token can never read a
runtime agent's prompt. Unknown agent, runtime agent, unknown semver and a
version without a tree are all 404 with distinct codes only where that does
not reveal a runtime agent's existence.

``{versao}`` is a semver, or ``latest`` for the currently ``ativa`` version.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import require_packages_read
from app.routers.studio_agents_router import get_studio_definition_store_dep, http_error
from app.schemas.packages import SEMVER_PATTERN, PackageFileOut, PackageOut, PackageVersionOut, PackageVersionsOut
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/agent-packages", tags=["agent-packages"])

_SEMVER = re.compile(SEMVER_PATTERN)


def resolve_dev_advisor(store, org_id, key: str):
    """The org's dev-advisor agent ``key`` — a runtime agent is reported as
    not found (never confirm it exists to a token that cannot read it)."""
    try:
        agent = store.get_agent(org_id, key)
    except NotFound as exc:
        raise http_error(404, "agent_not_found", "Agente não encontrado.") from exc
    if agent.definition_mode != "studio" or agent.kind != "dev-advisor":
        raise http_error(404, "agent_not_found", "Agente não encontrado.")
    return agent


def _published(store, org_id, agent) -> list:
    rows = [
        v for v in store.list_versions(org_id, agent.id)
        if v.status in ("ativa", "substituida") and v.versao_semver is not None
    ]
    return sorted(rows, key=lambda v: (v.published_at is not None, v.published_at, v.versao), reverse=True)


@router.get("/{key}/versions", response_model=PackageVersionsOut)
async def list_package_versions(
    key: str,
    ctx: AuthContext = Depends(require_packages_read),
    store=Depends(get_studio_definition_store_dep),
) -> PackageVersionsOut:
    agent = resolve_dev_advisor(store, ctx.org_id, key)
    items = [
        PackageVersionOut(
            versao=v.versao_semver, sha=v.package_sha, status=v.status, published_at=v.published_at,
            tem_arvore=bool(store.get_package_tree(ctx.org_id, v.id)),
        )
        for v in _published(store, ctx.org_id, agent)
    ]
    return PackageVersionsOut(key=agent.key, items=items)


def _package_meta(key: str, version, files: list[dict[str, str]]) -> dict[str, Any]:
    """``PACKAGE.json`` from the tree when present (the build's own record),
    else rebuilt from the version row; ``sha`` always agrees with the row."""
    meta: dict[str, Any] = {}
    for f in files:
        if f["caminho"] == f"agents/{key}/PACKAGE.json":
            try:
                parsed = json.loads(f["conteudo"])
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                meta = parsed
            break
    meta.setdefault("key", key)
    meta.setdefault("versao", version.versao_semver)
    meta.setdefault("sha", version.package_sha)
    if "compiled_hash" not in meta and version.compiled_hash:
        meta["compiled_hash"] = version.compiled_hash
    return meta


@router.get("/{key}/{versao}", response_model=PackageOut)
async def get_package(
    key: str,
    versao: str,
    ctx: AuthContext = Depends(require_packages_read),
    store=Depends(get_studio_definition_store_dep),
) -> PackageOut:
    agent = resolve_dev_advisor(store, ctx.org_id, key)
    if versao == "latest":
        active = store.get_active_version(ctx.org_id, agent.id)
        version = active if active is not None and active.versao_semver else None
    elif _SEMVER.match(versao):
        version = next((v for v in _published(store, ctx.org_id, agent) if v.versao_semver == versao), None)
    else:
        version = None
    if version is None:
        raise http_error(404, "package_version_not_found", "Versão do pacote não encontrada.")
    files = store.get_package_tree(ctx.org_id, version.id)
    if not files:
        raise http_error(
            404, "package_tree_not_found",
            "Esta versão foi importada sem a árvore `claude` e não pode ser servida.",
        )
    return PackageOut(
        files=[PackageFileOut(path=f["caminho"], conteudo=f["conteudo"]) for f in files],
        package=_package_meta(agent.key, version, files),
    )


__all__ = ["router", "resolve_dev_advisor"]
