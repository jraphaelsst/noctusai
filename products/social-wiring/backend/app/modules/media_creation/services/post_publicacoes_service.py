"""``cs_post_publicacoes``: schedule / reschedule / cancel a publication target, validated against the matrix.

A target is valid when ``post_formatos.validar_alvo`` passes for the post's CURRENT asset set; otherwise 422 with the
coded reasons. Events (``publicacao_agendada`` / ``_reagendada`` / ``_cancelada``) are written by the AFTER trigger of
migration 342 in the same transaction as the row.

NOC-REMEDIATE[cs-media-approval-gate]: spec T8 schedules from ``midia_aprovada``; the approval organ lands in S2/S3,
so for now the gate is "no asset reprovado" — tighten to "every current asset aprovado" then — 2026-11-13.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.modules.media_creation.post_formatos import PROVIDER_DA_REDE, validar_alvo
from app.modules.media_creation.services.post_assets_service import (
    ASSETS,
    POSTS,
    PostAssetError,
    atuais,
    fato_do_asset,
)

PUBLICACOES = "cs_post_publicacoes"
ACCOUNTS = "integration_accounts"


class PublicacaoError(PostAssetError):
    pass


class PostPublicacoesService:
    def __init__(self, db: Any, org_id: str, user_id: str):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    def _post(self, post_id: str) -> None:
        if not self.db.table(POSTS).select("id").eq("id", post_id).eq("org_id", self.org_id).execute().data:
            raise PublicacaoError(404, {"code": "post_nao_encontrado", "detail": "Post não encontrado"})

    def listar(self, post_id: str) -> list[dict[str, Any]]:
        self._post(post_id)
        return (
            self.db.table(PUBLICACOES).select("*").eq("post_id", post_id).eq("org_id", self.org_id)
            .order("created_at").execute().data or []
        )

    def _conta(self, rede: str, conta_id: str) -> None:
        rows = self.db.table(ACCOUNTS).select("id,provider").eq("id", conta_id).eq("org_id", self.org_id).execute().data
        if not rows or rows[0].get("provider") != PROVIDER_DA_REDE.get(rede):
            raise PublicacaoError(422, {"code": "conta_invalida", "detail": f"Conta inválida para {rede}", "conta_id": conta_id})

    def criar(self, post_id: str, *, rede: str, formato: str, conta_id: str, publicar_em: datetime) -> dict[str, Any]:
        self._post(post_id)
        atuais_ = atuais(
            self.db.table(ASSETS).select("*").eq("post_id", post_id).eq("org_id", self.org_id).execute().data or []
        )
        motivos = validar_alvo(rede, formato, [fato_do_asset(a) for a in atuais_])
        if motivos:
            first = motivos[0]
            raise PublicacaoError(422, {**first.as_detail(), "motivos": [m.as_detail() for m in motivos]})
        if any(a["status"] == "reprovado" for a in atuais_):
            raise PublicacaoError(422, {"code": "midia_reprovada", "detail": "Há mídia reprovada no post"})
        if publicar_em.tzinfo is None:
            raise PublicacaoError(422, {"code": "publicar_em_sem_fuso", "detail": "publicar_em precisa de fuso horário"})
        if publicar_em <= datetime.now(timezone.utc):
            raise PublicacaoError(422, {"code": "publicar_em_no_passado", "detail": "publicar_em precisa estar no futuro"})
        self._conta(rede, conta_id)
        dup = (
            self.db.table(PUBLICACOES).select("id").eq("post_id", post_id).eq("org_id", self.org_id)
            .eq("rede", rede).eq("formato", formato).eq("conta_id", conta_id).in_("status", ["agendado", "publicado"]).execute().data
        )
        if dup:
            raise PublicacaoError(409, {"code": "alvo_duplicado", "detail": "Este alvo já está agendado ou publicado"})
        row = {
            "org_id": self.org_id, "post_id": post_id, "rede": rede, "formato": formato, "conta_id": conta_id,
            "publicar_em": publicar_em.isoformat(), "status": "agendado", "origem": "app",
            "assets_ids": [str(a["id"]) for a in atuais_], "criado_por": self.user_id, "atualizado_por": self.user_id,
        }
        res = self.db.table(PUBLICACOES).insert(row).execute().data
        if not res:
            raise PublicacaoError(500, {"code": "publicacao_nao_gravada", "detail": "Falha ao gravar a publicação"})
        return res[0]

    def atualizar(self, post_id: str, pub_id: str, *, publicar_em: Optional[datetime], status: Optional[str]) -> dict[str, Any]:
        self._post(post_id)
        rows = self.db.table(PUBLICACOES).select("*").eq("id", pub_id).eq("post_id", post_id).eq("org_id", self.org_id).execute().data
        if not rows:
            raise PublicacaoError(404, {"code": "publicacao_nao_encontrada", "detail": "Publicação não encontrada"})
        if rows[0]["status"] != "agendado":
            raise PublicacaoError(409, {"code": "publicacao_nao_agendada", "detail": "Só publicações agendadas podem ser alteradas"})
        patch: dict[str, Any] = {"atualizado_por": self.user_id, "updated_at": datetime.now(timezone.utc).isoformat()}
        if status:
            patch["status"] = status
        if publicar_em is not None:
            if publicar_em.tzinfo is None or publicar_em <= datetime.now(timezone.utc):
                raise PublicacaoError(422, {"code": "publicar_em_no_passado", "detail": "publicar_em precisa estar no futuro, com fuso"})
            patch["publicar_em"] = publicar_em.isoformat()
        if len(patch) == 2:
            raise PublicacaoError(422, {"code": "nada_a_alterar", "detail": "Informe publicar_em ou status"})
        res = self.db.table(PUBLICACOES).update(patch).eq("id", pub_id).eq("org_id", self.org_id).execute().data
        return res[0]
