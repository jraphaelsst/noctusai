"""ONE-TIME backfill: copy an org's Julia knowledge into the agents app (julia-v2 CONTRACT Q1 / 0.3).

Julia is hosted in agents; the imobiliaria's knowledge (policies, documents, guarantees, phones, recess) now lives there
as an ORG SPEC -- the exact text the model sees, edited in the agents app. This job reads the org's
`julia_conhecimento_secoes` (the SW form), renders them with the form->markdown renderer
(`julia_conhecimento_service.render_md`, used here for the LAST time) and writes the result to agents through its API:

    PUT {agents}/api/studio/agents/{agent_key}/specs      {"valores": {"<spec_chave>": "<rendered text>"}}

The route is the ORG ADMIN's (the org's own signed-in admin session): the channel `pk_*` token cannot write specs, by
design, and a platform token cannot either (org specs are the org's). So the job takes that admin's bearer from the
environment (`--token-env`, default `NOCTUS_AGENTS_ADMIN_TOKEN`) and handles ONE org per run.

DRY-RUN by DEFAULT. Without `--apply` it reads, renders and (when a token is available) asks agents what it has, and prints
the plan -- it writes nothing. The output carries counts, sizes and a hash prefix ONLY, never the text (the knowledge is
the org's business data and the platform's prompt-adjacent content: it must not reach a terminal log or a transcript).

IDEMPOTENT: an org whose agents value already equals the rendered text is `unchanged`; a re-run after an edit in agents
OVERWRITES that edit unless `--keep-existing` is given (use it once the owner has started editing in agents).

Usage (from `products/social-wiring/backend`):

    python -m app.jobs.julia_conhecimento_backfill --org <org-uuid>                 # dry run
    python -m app.jobs.julia_conhecimento_backfill --org <org-uuid> --apply         # write
    python -m app.jobs.julia_conhecimento_backfill --org <org-uuid> --apply --keep-existing

Exit code: 0 ok / planned / unchanged, 1 on any error (nothing partial: one PUT per run).

NOC-REMEDIATE[julia-v2-conhecimento-spec-key]: the spec key (`--spec-chave`, default `conhecimento`) must match the key the
platform definition declares in `agent_version_specs` (the DATA slice seeds it); until then agents answers 422
`spec_nao_declarada` and the job reports it -- 2026-10-19
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any, Optional
from urllib.parse import quote
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

DEFAULT_AGENT_KEY = "julia"
DEFAULT_SPEC_CHAVE = "conhecimento"
DEFAULT_TOKEN_ENV = "NOCTUS_AGENTS_ADMIN_TOKEN"
TIMEOUT_S = 30.0


@dataclass(frozen=True)
class BackfillResult:
    org_id: str
    agent_key: str
    spec_chave: str
    #: planned | unchanged | updated | skipped_existing | sem_conhecimento | error
    status: str
    secoes: int = 0
    chars: int = 0
    sha12: Optional[str] = None
    chars_no_agents: Optional[int] = None
    erro: Optional[str] = None
    applied: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha12(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def renderizar(client: Any, org_id: UUID | str) -> tuple[str, int]:
    """`(rendered markdown, how many sections the org has stored)`. Empty org = `("", 0)`."""
    from app.services import julia_conhecimento_service as conhecimento

    rows = client.table(conhecimento.TABLE).select("secao").eq("org_id", str(org_id)).execute().data or []
    if not rows:
        return "", 0
    return conhecimento.render_md(client, org_id).strip(), len(rows)


async def _ler_no_agents(http: httpx.AsyncClient, agent_key: str, spec_chave: str) -> Optional[str]:
    """The org's current value of the spec in agents (None = not set / unreadable is raised)."""
    r = await http.get(f"/api/studio/agents/{quote(agent_key, safe='')}/specs")
    r.raise_for_status()
    for v in (r.json() or {}).get("valores") or []:
        if v.get("chave") == spec_chave:
            return v.get("valor") or None
    return None


async def executar(
    client: Any, org_id: UUID | str, *, agents_url: str, token: Optional[str], agent_key: str = DEFAULT_AGENT_KEY,
    spec_chave: str = DEFAULT_SPEC_CHAVE, apply: bool = False, keep_existing: bool = False,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> BackfillResult:
    """Plan (and with `apply=True`, perform) the copy for ONE org. Never prints or returns the text."""
    org = str(org_id)
    base = dict(org_id=org, agent_key=agent_key, spec_chave=spec_chave)
    texto, secoes = renderizar(client, org_id)
    if not texto:
        return BackfillResult(status="sem_conhecimento", secoes=secoes, **base)
    info = dict(secoes=secoes, chars=len(texto), sha12=_sha12(texto), **base)
    if not token:
        if apply:
            return BackfillResult(status="error", erro="token_ausente", **info)
        return BackfillResult(status="planned", **info)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(base_url=agents_url.rstrip("/"), headers=headers, timeout=TIMEOUT_S,
                                     transport=transport) as http:
            atual = await _ler_no_agents(http, agent_key, spec_chave)
            no_agents = len(atual) if atual else None
            if atual is not None and atual.strip() == texto:
                return BackfillResult(status="unchanged", chars_no_agents=no_agents, **info)
            if atual and keep_existing:
                return BackfillResult(status="skipped_existing", chars_no_agents=no_agents, **info)
            if not apply:
                return BackfillResult(status="planned", chars_no_agents=no_agents, **info)
            r = await http.put(f"/api/studio/agents/{quote(agent_key, safe='')}/specs", json={"valores": {spec_chave: texto}})
            if r.status_code >= 400:
                codigo = _codigo_de_erro(r)
                return BackfillResult(status="error", erro=f"http_{r.status_code}:{codigo}", chars_no_agents=no_agents, **info)
            return BackfillResult(status="updated", applied=True, chars_no_agents=no_agents, **info)
    except httpx.HTTPError as exc:
        return BackfillResult(status="error", erro=f"rede:{type(exc).__name__}", **info)


def _codigo_de_erro(response: httpx.Response) -> str:
    """agents' error `code` only -- never the body (it may echo content)."""
    try:
        body = response.json()
    except ValueError:
        return "sem_corpo"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict) and detail.get("code"):
        return str(detail["code"])[:60]
    return str((body or {}).get("code") or "desconhecido")[:60] if isinstance(body, dict) else "desconhecido"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--org", required=True, help="the org uuid (one org per run)")
    ap.add_argument("--agents-url", default=None, help="agents base URL (default: the product-URL registry)")
    ap.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="env var holding the org ADMIN bearer for agents")
    ap.add_argument("--agent-key", default=DEFAULT_AGENT_KEY)
    ap.add_argument("--spec-chave", default=DEFAULT_SPEC_CHAVE)
    ap.add_argument("--apply", action="store_true", help="WRITE to agents (default: dry run)")
    ap.add_argument("--keep-existing", action="store_true", help="never overwrite a value already in agents")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        org = UUID(args.org)
    except ValueError:
        print(json.dumps({"status": "error", "erro": "org_invalida"}))
        return 1
    from noctusai_lib.config.product_urls import resolve_product_url

    from app.dependencies import get_scoped_admin_client

    try:
        url = args.agents_url or resolve_product_url("agents")
    except ValueError:
        print(json.dumps({"status": "error", "erro": "agents_url_indisponivel"}))
        return 1
    result = asyncio.run(executar(
        get_scoped_admin_client("social_wiring"), org, agents_url=url, token=os.environ.get(args.token_env) or None,
        agent_key=args.agent_key, spec_chave=args.spec_chave, apply=args.apply, keep_existing=args.keep_existing,
    ))
    print(json.dumps({**result.as_dict(), "dry_run": not args.apply}, ensure_ascii=False))
    return 1 if result.status == "error" else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
