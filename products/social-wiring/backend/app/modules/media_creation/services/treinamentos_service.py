"""Treinamentos — platform-wide training lessons (geracao-contract.md §2.7, §4.2).

``cs_treinamentos`` has no ``org_id``: every org sees the same lessons, and writes are
reserved to platform admins (the router's ``require_platform_admin``; this service
trusts its caller on that and only validates data).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

logger = logging.getLogger(__name__)

TABLE = "cs_treinamentos"
COLS = "id,ordem,titulo,descricao,video_url,ativo"
#: Hosts a lesson video may be embedded from (mirrored by the FE's embed builder).
TREINAMENTO_VIDEO_HOSTS = frozenset({
    "iframe.mediadelivery.net",
    "player.vimeo.com",
    "www.youtube.com",
    "www.youtube-nocookie.com",
})


class TreinamentoError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def validar_video_url(url: Optional[str]) -> Optional[str]:
    """``None`` clears the video; anything else must be https on an allow-listed host."""
    if url is None:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in TREINAMENTO_VIDEO_HOSTS:
        raise TreinamentoError(
            422, "O vídeo deve ser um link https de: " + ", ".join(sorted(TREINAMENTO_VIDEO_HOSTS))
        )
    return url


def _out(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"], "ordem": r["ordem"], "titulo": r["titulo"],
        "descricao": r.get("descricao") or "", "video_url": r.get("video_url"),
        "ativo": bool(r.get("ativo", True)),
    }


class TreinamentosService:
    def __init__(self, db, user_id: str = ""):
        self.db = db
        self.user_id = user_id

    def _t(self):
        return self.db.table(TABLE)

    def listar(self) -> list[dict[str, Any]]:
        rows = self._t().select(COLS).eq("ativo", True).order("ordem").execute().data or []
        return [_out(r) for r in sorted(rows, key=lambda r: r["ordem"])]

    def _get(self, treinamento_id: str) -> dict[str, Any]:
        rows = self._t().select(COLS).eq("id", treinamento_id).execute().data
        if not rows:
            raise TreinamentoError(404, "Treinamento não encontrado")
        return rows[0]

    def _proxima_ordem(self) -> int:
        rows = self._t().select("ordem").execute().data or []
        return max((r["ordem"] for r in rows), default=0) + 1

    def criar(self, *, titulo: str, descricao: str, video_url: Optional[str], ativo: bool,
              ordem: Optional[int]) -> dict[str, Any]:
        row = {
            "ordem": ordem if ordem is not None else self._proxima_ordem(),
            "titulo": titulo.strip(), "descricao": descricao,
            "video_url": validar_video_url(video_url), "ativo": ativo,
            "updated_by": self.user_id or None,
        }
        if not row["titulo"]:
            raise TreinamentoError(422, "Informe o título")
        try:
            created = self._t().insert(row).execute().data
        except Exception as exc:  # noqa: BLE001 - only the unique-ordem collision is translated
            if is_unique_violation(exc):
                raise TreinamentoError(409, "Já existe um treinamento com essa ordem") from exc
            raise
        return _out(created[0])

    def atualizar(self, treinamento_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        atual = self._get(treinamento_id)
        if not patch:
            return _out(atual)
        values = dict(patch)
        if "video_url" in values:
            values["video_url"] = validar_video_url(values["video_url"])
        if "titulo" in values:
            values["titulo"] = values["titulo"].strip()
            if not values["titulo"]:
                raise TreinamentoError(422, "Informe o título")
        values["updated_by"] = self.user_id or None
        values["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._t().update(values).eq("id", treinamento_id).execute()
        except Exception as exc:  # noqa: BLE001 - only the unique-ordem collision is translated
            if is_unique_violation(exc):
                raise TreinamentoError(409, "Já existe um treinamento com essa ordem") from exc
            raise
        return _out(self._get(treinamento_id))

    def excluir(self, treinamento_id: str) -> None:
        self._get(treinamento_id)
        self._t().delete().eq("id", treinamento_id).execute()
