"""``cs_post_assets``: register files (media kind, aspect ratio, duration READ from the bytes), version, status.

Events are written by the AFTER triggers of migration 342 in the same transaction as the row; this service's job
is to put the actor on the row (``criado_por`` / ``atualizado_por``) so the trigger can record it.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noctusai_lib.integrations.media import FfmpegNotInstalled, MediaProbeError, probe_video

from app.modules.media_creation.post_formatos import AssetFato, classificar_proporcao

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
ASSETS = "cs_post_assets"
#: PRIVATE bucket (migration 342). Key convention: ``org/<org>/posts/<post>/...`` (slice S5 refines the sub-prefixes).
MIDIA_BUCKET = "sw-posts-midia"

EXT_IMAGEM = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
EXT_VIDEO = frozenset({".mp4", ".mov", ".m4v", ".webm"})
MAX_BYTES = 500 * 1024 * 1024
#: A status that takes a file out of the current set / out of use.
STATUS_INUTILIZAVEL = ("reprovado", "arquivado")


class PostAssetError(Exception):
    def __init__(self, status: int, detail: dict[str, Any]):
        super().__init__(detail.get("detail", ""))
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class MidiaFato:
    tipo_midia: str
    largura: int
    altura: int
    duracao_s: Optional[float]


#: The probe seam: (bytes, filename) -> MidiaFato; raises PostAssetError(422) for an unreadable / unsupported file.
MidiaProbe = Callable[[bytes, str], MidiaFato]


#: Size seam: (bucket, key) -> stored object size in bytes from storage METADATA (no download), None when absent.
MidiaStat = Callable[[str, str], Optional[int]]


def stat_midia(client: Any, bucket: str, key: str) -> Optional[int]:
    """Real stat: the object size from Supabase Storage list metadata — never downloads the object."""
    pasta, _, nome = key.rpartition("/")
    itens = client.storage.from_(bucket).list(pasta, {"search": nome, "limit": 100}) or []
    for it in itens:
        if it.get("name") == nome:
            tam = (it.get("metadata") or {}).get("size")
            if tam is None:
                raise PostAssetError(422, {"code": "tamanho_indisponivel", "detail": "Tamanho do arquivo indisponível"})
            return int(tam)
    return None


_MAGIC_OK = {
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",), ".webm": (b"\x1a\x45\xdf\xa3",),
}


def checar_magic(dados: bytes, filename: str) -> None:
    """The header bytes must match the extension's container (never trust the name); ISO-BMFF ('ftyp') for mp4/mov/m4v."""
    ext = os.path.splitext(filename)[1].lower()
    cab = dados[:16]
    if ext in (".mp4", ".mov", ".m4v"):
        ok = cab[4:8] == b"ftyp"
    else:
        ok = any(cab.startswith(m) for m in _MAGIC_OK.get(ext, ()))
    if not ok:
        raise PostAssetError(422, {"code": "tipo_arquivo_inconsistente", "detail": "O conteúdo do arquivo não corresponde à extensão"})


def probe_midia(dados: bytes, filename: str) -> MidiaFato:
    """Real probe (ffprobe via the seed media layer): kind by container, size + duration from the stream."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in EXT_IMAGEM:
        tipo = "imagem"
    elif ext in EXT_VIDEO:
        tipo = "video"
    else:
        raise PostAssetError(422, {"code": "tipo_arquivo_nao_suportado", "detail": f"Extensão não suportada: {ext or '(nenhuma)'}"})
    with tempfile.TemporaryDirectory(prefix="cs-midia-") as tmp:
        path = os.path.join(tmp, f"in{ext}")
        with open(path, "wb") as fh:
            fh.write(dados)
        try:
            pr = probe_video(path)
        except FfmpegNotInstalled:
            logger.error("ffprobe not installed — cannot read post media (image must be FROM the media base)")
            raise PostAssetError(503, {"code": "leitor_midia_indisponivel", "detail": "Leitor de mídia indisponível"})
        except MediaProbeError as exc:
            logger.info("post media unreadable (%s)", type(exc).__name__)
            raise PostAssetError(422, {"code": "arquivo_ilegivel", "detail": "Não foi possível ler o arquivo de mídia"})
    duracao: Optional[float] = None
    if tipo == "video":
        if not pr.duration_s or pr.duration_s <= 0:
            raise PostAssetError(422, {"code": "arquivo_ilegivel", "detail": "Vídeo sem duração legível"})
        duracao = round(float(pr.duration_s), 3)
    return MidiaFato(tipo, pr.display_width, pr.display_height, duracao)


def atuais(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The post's CURRENT asset set: the highest ``versao`` of each ``ordem`` (an archived top version removes the slot)."""
    topo: dict[int, dict[str, Any]] = {}
    for a in assets:
        if a["ordem"] not in topo or a["versao"] > topo[a["ordem"]]["versao"]:
            topo[a["ordem"]] = a
    return [topo[o] for o in sorted(topo) if topo[o]["status"] != "arquivado"]


def fato_do_asset(a: dict[str, Any]) -> AssetFato:
    return AssetFato(a["tipo_midia"], a["proporcao"], float(a["duracao_s"]) if a.get("duracao_s") is not None else None)


class PostAssetsService:
    def __init__(self, db: Any, org_id: str, user_id: str):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    def _post(self, post_id: str) -> dict[str, Any]:
        rows = self.db.table(POSTS).select("id").eq("id", post_id).eq("org_id", self.org_id).execute().data
        if not rows:
            raise PostAssetError(404, {"code": "post_nao_encontrado", "detail": "Post não encontrado"})
        return rows[0]

    def prefixo(self, post_id: str) -> str:
        return f"org/{self.org_id}/posts/{post_id}/"

    def todos(self, post_id: str) -> list[dict[str, Any]]:
        self._post(post_id)
        return self._todos(post_id)

    def _todos(self, post_id: str) -> list[dict[str, Any]]:
        return (
            self.db.table(ASSETS).select("*").eq("post_id", post_id).eq("org_id", self.org_id)
            .order("ordem").order("versao").execute().data or []
        )

    def listar(self, post_id: str, *, historico: bool = False) -> list[dict[str, Any]]:
        todos = self.todos(post_id)
        return todos if historico else atuais(todos)

    def validar_caminho(self, post_id: str, storage_path: str) -> None:
        """The file must live under THIS org's and post's prefix: a foreign path is never registered."""
        self._post(post_id)
        if ".." in storage_path or not storage_path.startswith(self.prefixo(post_id)):
            raise PostAssetError(422, {"code": "caminho_invalido", "detail": "O arquivo não pertence a este post"})

    def registrar(
        self, post_id: str, *, storage_path: str, ordem: Optional[int], fato: MidiaFato,
        mime_type: Optional[str] = None, tamanho_bytes: Optional[int] = None,
    ) -> dict[str, Any]:
        self.validar_caminho(post_id, storage_path)
        todos = self._todos(post_id)
        if ordem is None:
            ordem = max((a["ordem"] for a in todos), default=0) + 1
        versao = max((a["versao"] for a in todos if a["ordem"] == ordem), default=0) + 1
        row = {
            "org_id": self.org_id, "post_id": post_id, "tipo_midia": fato.tipo_midia, "ordem": ordem, "versao": versao,
            "proporcao": classificar_proporcao(fato.largura, fato.altura), "largura": fato.largura, "altura": fato.altura,
            "duracao_s": fato.duracao_s, "storage_path": storage_path, "mime_type": mime_type, "tamanho_bytes": tamanho_bytes,
            "status": "pronto", "criado_por": self.user_id, "atualizado_por": self.user_id,
        }
        res = self.db.table(ASSETS).insert(row).execute().data
        if not res:
            raise PostAssetError(500, {"code": "asset_nao_gravado", "detail": "Falha ao gravar a mídia"})
        return res[0]

    def atualizar_status(self, post_id: str, asset_id: str, status: str) -> dict[str, Any]:
        self._post(post_id)
        res = (
            self.db.table(ASSETS)
            .update({"status": status, "atualizado_por": self.user_id, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", asset_id).eq("post_id", post_id).eq("org_id", self.org_id).execute().data
        )
        if not res:
            raise PostAssetError(404, {"code": "asset_nao_encontrado", "detail": "Mídia não encontrada"})
        return res[0]
