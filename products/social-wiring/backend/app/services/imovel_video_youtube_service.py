"""The ONE published YouTube video of an imóvel (`imovel_video_youtube`, migration 371) -- owned by Social Wiring.

CONTRACT (project `julia-videos-prontos-youtube`, slice S1; the sibling slice calls these exact names):

    svc = build_imovel_video_youtube_service(client)          # client = the social_wiring-scoped admin client
    svc.obter(org_id, codigo)                                 -> ImovelVideoYoutube | None
    svc.definir(org_id, codigo, *, youtube_video_id, origem, motivo, upload_job_id=None, definido_por=None) -> ImovelVideoYoutube
    svc.remover(org_id, codigo, *, motivo, definido_por=None) -> ImovelVideoYoutube | None   (the removed value)

WHAT GOES HERE: the standard (horizontal) video only -- a Short never does (`extrair_video_id` refuses a /shorts/ link).
`origem` = `julia` (Julia published it) | `manual` (a user set it) | `vista` (imported from Vista's `VideoDestaque`).

`definir` -- REPLACE semantics (owner: the newest wins):
  1. the código is canonicalised and must be in `imovel_registry` (`exigir_imovel_cadastrado`: the contract's 404 otherwise);
  2. the row is upserted on (org_id, codigo); the SAME id again is a no-op (a retried upload never writes twice);
  3. `imovel_historico` gets `video_youtube_definido` (previous URL in `valor_anterior`, the motivo in `detalhe`);
  4. ONLY when the org switch `vista_divergencias_config.vista_escrita_ativa` is ON and the value did NOT come from Vista
     (`origem != 'vista'`: no echo write), Vista's `VideoDestaque` is set with the motivo + our dated line at the top of the
     ObsVenda log -- the seed `atualizar_imovel` / `observacoes` mechanism the Vista sync already uses (header untouched, a
     failed read writes nothing). Sent => history `enviado_ao_vista` (detalhe = the line written). Failed => history
     `envio_vista_falhou` with the failure's class name; never raised (our value is already saved), never silent.

`remover` clears our row and writes `video_youtube_removido`. It does NOT clear Vista's `VideoDestaque` (deleting data in
Vista is an owner call, not a side effect of clearing ours -- open question of S1).

ATOMICITY: the row and its history row are two PostgREST calls (as the rest of `imovel_historico`'s writers): a failed
history insert raises to the caller after the row changed. NOC-REMEDIATE[imovel-video-youtube-rpc]: fold row + history into
one SQL function (one transaction) if the history ever needs to be a strict guarantee -- 2026-11-27
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from noctusai_lib.primitives.tasks import run_coro_sync

from app.modules.imovel_hub._relacionamentos import exigir_imovel_cadastrado
from app.services import imovel_historico_service as hist

logger = logging.getLogger(__name__)

T_VIDEO = "imovel_video_youtube"
#: The history `campo` of every row this module writes.
CAMPO = "video_youtube"
#: Vista's featured-video field of a listing.
CAMPO_VISTA = "VideoDestaque"
ORIGENS = ("julia", "manual", "vista")
#: Our origem -> the `imovel_historico.origem` it is recorded under.
_ORIGEM_HISTORICO = {"julia": "julia", "manual": "usuario", "vista": "vista_sync"}
#: Who "informs" in the Vista note (`DD/MM/YY <fonte> informa via <canal>: ...`).
_FONTE_NOTA = {"julia": "Julia", "manual": "Usuário"}
URL_BASE = "https://www.youtube.com/watch?v="
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}


class VideoYoutubeInvalido(ValueError):
    """The value is not a usable YouTube video (bad id/URL, a Short, an unknown origem, no motivo) -- a 422 on the API."""


class VideoYoutubeShort(VideoYoutubeInvalido):
    """A `/shorts/` link: a real YouTube video that does NOT belong in this field (the Vista import counts it `short_ignorado`)."""


@dataclass(frozen=True)
class ImovelVideoYoutube:
    org_id: str
    codigo: str
    youtube_video_id: str
    youtube_url: str
    origem: str
    upload_job_id: Optional[str] = None
    definido_por: Optional[str] = None
    criado_em: Optional[str] = None
    atualizado_em: Optional[str] = None

    def para_api(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo, "youtube_video_id": self.youtube_video_id, "youtube_url": self.youtube_url, "origem": self.origem,
            "upload_job_id": self.upload_job_id, "definido_por": self.definido_por, "criado_em": self.criado_em,
            "atualizado_em": self.atualizado_em,
        }


def url_de(video_id: str) -> str:
    """The canonical watch URL -- the same expression as the table's generated `youtube_url` column."""
    return URL_BASE + video_id


def extrair_video_id(valor: str) -> str:
    """The 11-char video id from a bare id or a YouTube URL (watch?v= / youtu.be / embed / live / v). A Short is refused."""
    texto = (valor or "").strip()
    if _ID.match(texto):
        return texto
    if "://" not in texto:
        texto = "https://" + texto
    try:
        url = urlparse(texto)
    except ValueError as exc:
        raise VideoYoutubeInvalido("Link do YouTube inválido.") from exc
    host = (url.hostname or "").lower()
    partes = [p for p in url.path.split("/") if p]
    candidato: Optional[str] = None
    if host in ("youtu.be", "www.youtu.be"):
        candidato = partes[0] if partes else None
    elif host in _HOSTS:
        if partes and partes[0] == "shorts":
            raise VideoYoutubeShort("Shorts não entram aqui: informe o vídeo padrão (horizontal) do imóvel.")
        if partes[:1] == ["watch"] or not partes:
            candidato = (parse_qs(url.query).get("v") or [None])[0]
        elif len(partes) >= 2 and partes[0] in ("embed", "live", "v"):
            candidato = partes[1]
    if not candidato or not _ID.match(candidato):
        raise VideoYoutubeInvalido("Link do YouTube inválido: informe a URL do vídeo ou o seu ID.")
    return candidato


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _de_linha(row: dict) -> ImovelVideoYoutube:
    vid = str(row["youtube_video_id"])
    return ImovelVideoYoutube(
        org_id=str(row["org_id"]), codigo=str(row["codigo"]), youtube_video_id=vid, youtube_url=url_de(vid), origem=str(row["origem"]),
        upload_job_id=str(row["upload_job_id"]) if row.get("upload_job_id") else None,
        definido_por=str(row["definido_por"]) if row.get("definido_por") else None,
        criado_em=row.get("criado_em"), atualizado_em=row.get("atualizado_em"),
    )


def _motivo(motivo: Optional[str]) -> str:
    m = " ".join(str(motivo or "").split())
    if not m:
        raise VideoYoutubeInvalido("Informe o motivo: toda alteração do vídeo do imóvel é registrada com o motivo.")
    return m


def _escrita_vista_ativa(db: Any, org_id: Any) -> bool:
    from app.services import vista_divergencias

    return bool(vista_divergencias.config(db, org_id)["vista_escrita_ativa"])


def _provider_padrao(org_id: Any) -> Any:
    from app.services import vista_credenciais

    return vista_credenciais.adapter_da_org(org_id)


class ImovelVideoYoutubeService:
    def __init__(self, client: Any, *, vista_provider: Callable[[Any], Any] = _provider_padrao) -> None:
        self._db = client
        self._vista_provider = vista_provider

    # ── reads ──────────────────────────────────────────────────────────────
    def _linha(self, org_id: Any, codigo: str) -> Optional[dict]:
        rows = (self._db.table(T_VIDEO).select("*").eq("org_id", str(org_id)).eq("codigo", codigo).limit(1).execute().data or [])
        return rows[0] if rows else None

    def obter(self, org_id: UUID | str, codigo: str) -> Optional[ImovelVideoYoutube]:
        """The imóvel's published video, or None (an unknown código is simply None here -- reads never 404)."""
        canonico = (codigo or "").strip().upper()
        if not canonico:
            return None
        row = self._linha(org_id, canonico)
        return _de_linha(row) if row else None

    # ── writes ─────────────────────────────────────────────────────────────
    def definir(
        self, org_id: UUID | str, codigo: str, *, youtube_video_id: str, origem: str, motivo: str,
        upload_job_id: Optional[UUID | str] = None, definido_por: Optional[UUID | str] = None,
    ) -> ImovelVideoYoutube:
        if origem not in ORIGENS:
            raise VideoYoutubeInvalido(f"origem {origem!r} inválida (use {', '.join(ORIGENS)}).")
        vid = extrair_video_id(youtube_video_id)
        m = _motivo(motivo)
        canonico = exigir_imovel_cadastrado(self._db, UUID(str(org_id)), codigo)
        atual = self._linha(org_id, canonico)
        if atual and str(atual["youtube_video_id"]) == vid:
            return _de_linha(atual)  # the same video again (a retried upload): nothing to record, nothing to send
        agora = _agora()
        linha = {
            "org_id": str(org_id), "codigo": canonico, "youtube_video_id": vid, "origem": origem,
            "upload_job_id": str(upload_job_id) if upload_job_id else None, "definido_por": str(definido_por) if definido_por else None,
            "atualizado_em": agora,
        }
        if not atual:
            linha["criado_em"] = agora
        gravada = (self._db.table(T_VIDEO).upsert(linha, on_conflict="org_id,codigo").execute().data or [None])[0] or {**(atual or {}), **linha}
        anterior = url_de(str(atual["youtube_video_id"])) if atual else None
        novo = url_de(vid)
        hist.registrar(self._db, org_id, canonico, origem=_ORIGEM_HISTORICO[origem], acao="video_youtube_definido", campo=CAMPO,
                       anterior=anterior, novo=novo, ator=definido_por, detalhe=m)
        if origem != "vista" and _escrita_vista_ativa(self._db, org_id):
            self._enviar_ao_vista(org_id, canonico, novo, anterior, motivo=m, origem=origem, ator=definido_por)
        return _de_linha(gravada)

    def remover(self, org_id: UUID | str, codigo: str, *, motivo: str, definido_por: Optional[UUID | str] = None) -> Optional[ImovelVideoYoutube]:
        """Clear the imóvel's video (history `video_youtube_removido`); None when there was none. Vista is NOT touched."""
        m = _motivo(motivo)
        canonico = exigir_imovel_cadastrado(self._db, UUID(str(org_id)), codigo)
        atual = self._linha(org_id, canonico)
        if not atual:
            return None
        self._db.table(T_VIDEO).delete().eq("org_id", str(org_id)).eq("codigo", canonico).execute()
        removido = _de_linha(atual)
        hist.registrar(self._db, org_id, canonico, origem="usuario" if definido_por else "sistema", acao="video_youtube_removido",
                       campo=CAMPO, anterior=removido.youtube_url, novo=None, ator=definido_por, detalhe=m)
        return removido

    # ── Vista write-back ───────────────────────────────────────────────────
    def _enviar_ao_vista(self, org_id: Any, codigo: str, url: str, anterior: Optional[str], *, motivo: str, origem: str, ator: Any) -> None:
        """Set Vista's `VideoDestaque` + our ObsVenda line; the outcome lands in the history either way, never raised."""
        try:
            adapter = self._vista_provider(org_id)
            nota = run_coro_sync(lambda: adapter.atualizar_imovel(
                codigo, {CAMPO_VISTA: url}, motivo=motivo, autor="NoctusAI", canal="YouTube", fonte=_FONTE_NOTA[origem],
                finalidade="venda", rotulos={CAMPO_VISTA: "vídeo do YouTube"}))
        except Exception as exc:  # the class name only: a Vista 401 body embeds the key
            logger.warning("imovel video youtube: Vista write of %s failed org=%s (%s)", codigo, org_id, type(exc).__name__)
            hist.registrar(self._db, org_id, codigo, origem=_ORIGEM_HISTORICO[origem], acao="envio_vista_falhou", campo=CAMPO,
                           anterior=anterior, novo=url, ator=ator,
                           detalhe=f"Não foi possível enviar o vídeo ao Vista ({type(exc).__name__}). O vídeo ficou salvo no NoctusAI.")
            return
        hist.registrar(self._db, org_id, codigo, origem=_ORIGEM_HISTORICO[origem], acao="enviado_ao_vista", campo=CAMPO,
                       anterior=anterior, novo=url, ator=ator, detalhe=nota)


def build_imovel_video_youtube_service(client: Any, *, vista_provider: Optional[Callable[[Any], Any]] = None) -> ImovelVideoYoutubeService:
    """The service over the `social_wiring`-scoped client. `vista_provider(org_id) -> adapter` defaults to the org's Real Vista
    adapter (`vista_credenciais.adapter_da_org`; raises `VistaConfigError` without a credential -> recorded as a failed send)."""
    return ImovelVideoYoutubeService(client, vista_provider=vista_provider or _provider_padrao)


__all__ = [
    "CAMPO", "CAMPO_VISTA", "ORIGENS", "ImovelVideoYoutube", "ImovelVideoYoutubeService", "VideoYoutubeInvalido", "VideoYoutubeShort",
    "build_imovel_video_youtube_service", "extrair_video_id", "url_de",
]
