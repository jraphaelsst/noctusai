"""Cadastro service — contract §Identity, slice BE-A. PUBLIC self-signup.

Reuses the seed's identity primitives VERBATIM
(`noctusai_lib.domain.org.provision_invited_identity` /
`.attach_user_to_org`) — the SAME mechanism the seed's own `team`
standard router uses for invite-accept (`noctusai_seed.routers.
_create_team_router`). Turnstile is checked with the exact SAME
resolution helper `/api/checkout` uses (`checkout_service.
_default_turnstile_verifier`) — reused, not copied, so the two public
forms never drift on how a key is resolved.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.org import attach_user_to_org, provision_invited_identity
from noctusai_lib.integrations.turnstile import TurnstileVerifier

from app.dependencies import MEMBRO_ORG_ROLE
from app.services.checkout_service import _default_turnstile_verifier
from app.services.eventos_service import registrar_evento

logger = logging.getLogger(__name__)

_MEMBROS_TABLE = "membros"
_PLANOS_TABLE = "planos"


class CadastroServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _resolve_free_plano_id(client: Any, *, org_id: str) -> Optional[str]:
    """The active plan with `preco_centavos = 0` and the lowest `ordem`
    (contract §Tiers: "the free plan" everywhere). None when the org
    hasn't run `POST /api/planos/padrao` yet."""
    rows = (
        client.table(_PLANOS_TABLE)
        .select("id,ordem")
        .eq("org_id", org_id)
        .eq("ativo", True)
        .eq("preco_centavos", 0)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("ordem") or 0)
    return rows[0]["id"]


class CadastroService:
    def __init__(
        self,
        admin_client: Any,
        core_client: Any,
        *,
        org_id: UUID,
        turnstile_verifier: Optional[TurnstileVerifier] = None,
    ) -> None:
        self._client = admin_client
        self._core = core_client
        self._org_id = str(org_id)
        self._turnstile = turnstile_verifier or _default_turnstile_verifier(self._org_id)

    async def cadastrar(self, *, payload: dict, remote_ip: Optional[str] = None) -> dict:
        if not payload.get("aceite_termos"):
            raise CadastroServiceError("É preciso aceitar os termos.", status_code=400)

        token = payload.get("turnstile_token") or ""
        verification = await self._turnstile.verify(token, remote_ip=remote_ip)
        if not verification.success:
            raise CadastroServiceError(
                "Verificação de segurança falhou. Recarregue a página e tente novamente.",
                status_code=403,
            )

        email = payload["email"]
        nome = payload["nome"]

        user_id, created = provision_invited_identity(
            self._core, email=email, password=payload["senha"], nome=nome,
        )
        if not created:
            raise CadastroServiceError(
                "Este e-mail já tem cadastro. Entre com sua senha.", status_code=409,
            )

        attach_user_to_org(
            self._core, user_id, org_id=self._org_id, email=email, nome=nome,
            org_role=MEMBRO_ORG_ROLE,
        )

        membro = self._find_or_link_membro(payload=payload, user_id=user_id)

        registrar_evento(
            self._client, org_id=self._org_id, membro_id=membro["id"], tipo="acesso",
            descricao="Cadastro realizado pelo site",
        )

        return {"membro_id": membro["id"], "email": email, "proximo_passo": "entrar"}

    # ── writes ───────────────────────────────────────────────────────

    def _find_or_link_membro(self, *, payload: dict, user_id: str) -> dict:
        email = payload["email"]
        existing = (
            self._client.table(_MEMBROS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("email", email)
            .execute()
            .data
            or []
        )
        if existing:
            row = existing[0]
            update: dict[str, Any] = {"user_id": user_id}
            if not row.get("plano_id"):
                free_id = _resolve_free_plano_id(self._client, org_id=self._org_id)
                if not free_id:
                    raise CadastroServiceError(
                        "Plano gratuito não configurado.", status_code=409,
                    )
                update["plano_id"] = free_id
            result = (
                self._client.table(_MEMBROS_TABLE)
                .update(update)
                .eq("org_id", self._org_id)
                .eq("id", row["id"])
                .execute()
            )
            return result.data[0] if result.data else {**row, **update}

        free_id = _resolve_free_plano_id(self._client, org_id=self._org_id)
        if not free_id:
            raise CadastroServiceError("Plano gratuito não configurado.", status_code=409)
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()), "org_id": self._org_id, "nome": payload["nome"],
            "email": email, "telefone": payload.get("telefone"), "status": "ativo",
            "plano_id": free_id, "origem": "cadastro", "tags": [], "observacoes": None,
            "user_id": user_id, "entrou_em": now, "created_at": now, "updated_at": now,
        }
        result = self._client.table(_MEMBROS_TABLE).insert(row).execute()
        if not result.data:
            raise CadastroServiceError("Falha ao criar cadastro.")
        return result.data[0]
