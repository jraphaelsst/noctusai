"""Deterministic typed chat commands to manage already-uploaded YouTube videos.

No LLM involved. The operator types ``<CODE> <command> [args]`` in the web or
WhatsApp upload chat and this module parses + executes it. Self-contained: the
chat dispatcher calls :meth:`YouTubeChatCommands.try_handle` first and falls
through to its own state machine when it returns ``None``.

Layers:
  * :func:`parse_command` — pure grammar (no IO).
  * :class:`YouTubeChatCommands` — executor with injected Protocol deps.
  * :class:`SupabaseJobLookup` / :class:`SupabaseCatalogSync` /
    :class:`UploadServiceRetrier` — real adapters over the existing product
    tables/services (mirroring what the dashboard routers do).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from uuid import UUID

from noctusai_lib.domain.real_estate import PRODUCT_CODE_SCAN_PATTERN
from noctusai_lib.primitives.accents import fold_accents

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
TITLE_MAX = 100
DESCRIPTION_MAX = 5000
CONFIRM_TTL_SECONDS = 600
CONFIRM_KEY_PREFIX = "ytcmd:confirm:"
_PUBLISHED_STATUSES = ("published", "notified")

_PRIVACY_WORDS = {
    "publico": "public",
    "public": "public",
    "privado": "private",
    "privada": "private",
    "private": "private",
    "nao listado": "unlisted",
    "nao listada": "unlisted",
    "unlisted": "unlisted",
}
_PRIVACY_LABEL = {"public": "público", "private": "privado", "unlisted": "não listado"}
_YES = {"sim", "s", "yes", "y"}
_NO = {"nao", "n", "no", "cancelar", "cancela"}

HELP_TEXT = (
    "*Comandos de vídeos do YouTube* (código do imóvel primeiro):\n"
    "• `ONE10874 titulo Novo título`\n"
    "• `ONE10874 descricao Nova descrição` (pode ter várias linhas)\n"
    "• `ONE10874 privacidade publico | privado | nao listado`\n"
    "• `ONE10874 apagar` (pede confirmação; também `excluir`/`deletar`)\n"
    "• `ONE10874 tentar de novo` (também `refazer`/`retry`) — refaz uploads que falharam\n"
    "• `ONE10874 status` — lista os vídeos do código\n"
    "Para atuar só no vídeo normal ou só no Short, coloque `video` ou `short` "
    "logo após o código: `ONE10874 short privacidade publico`.\n"
    "Sem isso, o comando vale para todos os vídeos publicados do código."
)


def _fold(text: str) -> str:
    """Lowercase + strip accents, preserving string length 1:1."""
    return "".join((fold_accents(c) or c)[:1] for c in text).lower()


# ─── Parsing ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ChatCommand:
    """Parsed command. ``kind`` in help/titulo/descricao/privacidade/apagar/
    retry/status. ``arg`` is the raw argument (titulo/descricao) or the
    normalised privacy value (None when the privacy word was not recognised).
    ``target`` is None (all), ``"video"`` or ``"short"``."""

    kind: str
    code: str | None = None
    target: str | None = None
    arg: str | None = None


_QUALIFIERS = {"short": "short", "shorts": "short", "video": "video", "videos": "video"}
_STRICT_KINDS = (  # whole remainder must be the keyword (no trailing free text)
    ("apagar", ("apagar", "excluir", "deletar")),
    ("retry", ("tentar de novo", "tentar novamente", "refazer", "retry")),
    ("status", ("status",)),
)
_ARG_KINDS = (
    ("titulo", "titulo"),
    ("descricao", "descricao"),
    ("privacidade", "privacidade"),
)


def _strip_trailing_punct(s: str) -> str:
    return s.strip().rstrip(".!?;,").strip()


def parse_command(text: str) -> ChatCommand | None:
    """Parse a typed command; ``None`` when ``text`` is not one (fall through)."""
    if not text or not text.strip():
        return None
    stripped = text.strip()
    folded_all = _strip_trailing_punct(_fold(stripped).lstrip("/"))
    if folded_all in ("ajuda", "comandos", "comando"):
        return ChatCommand(kind="help")

    m = PRODUCT_CODE_SCAN_PATTERN.match(stripped)
    if not m:
        return None
    code = m.group(0).upper()
    rest = stripped[m.end():]
    if rest and not rest[0].isspace():
        return None
    rest = rest.lstrip()
    if not rest:
        return None
    folded = _fold(rest)

    target: str | None = None
    first, _, tail = folded.partition(" ")
    if first in _QUALIFIERS:
        target = _QUALIFIERS[first]
        skip = len(rest) - len(rest[len(first):].lstrip())
        rest, folded = rest[skip:], folded[skip:]
        if not rest:
            return None

    whole = _strip_trailing_punct(" ".join(folded.split()))
    for kind, words in _STRICT_KINDS:
        if whole in words:
            return ChatCommand(kind=kind, code=code, target=target)

    for kind, word in _ARG_KINDS:
        if folded.startswith(word) and (len(folded) == len(word) or not folded[len(word)].isalnum()):
            arg = rest[len(word):].lstrip(" \t")
            if arg[:1] in (":", "-", "–", "—"):
                arg = arg[1:]
            arg = arg.strip()
            if kind == "privacidade":
                key = " ".join(_fold(_strip_trailing_punct(arg)).split())
                return ChatCommand(
                    kind=kind, code=code, target=target, arg=_PRIVACY_WORDS.get(key)
                )
            return ChatCommand(kind=kind, code=code, target=target, arg=arg)
    return None


# ─── Dependencies (Protocols) ────────────────────────────────────────────
class YouTubeOps(Protocol):
    """Subset of ``YouTubeService`` used here (sync; run in a thread)."""

    def update_video_metadata(
        self,
        *,
        org_id: UUID,
        video_id: str,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> Any: ...

    def delete_youtube_video(self, *, org_id: UUID, video_id: str) -> None: ...


class JobLookup(Protocol):
    def list_jobs(self, code: str) -> list[dict[str, Any]]:
        """upload_jobs rows for ``code`` (org-scoped), most recent first."""
        ...


class JobRetrier(Protocol):
    def retry(self, job_id: str) -> None:
        """Re-queue a failed job AND kick its run. Raises with a pt-BR-safe
        message on failure."""
        ...


class CatalogSync(Protocol):
    def mirror_update(self, video_id: str, patch: dict[str, Any]) -> None: ...

    def mirror_delete(self, video_id: str) -> None: ...


# ─── Executor ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Video:
    video_id: str
    job_id: str
    kind: str  # "short" | "video"
    title: str
    privacy: str | None


def _kind_of(row: dict[str, Any]) -> str:
    return "short" if row.get("target_format") == "shorts" else "video"


def _kind_label(kind: str) -> str:
    return "Short" if kind == "short" else "vídeo"


def _link(video_id: str) -> str:
    return f"https://youtu.be/{video_id}"


class YouTubeChatCommands:
    def __init__(
        self,
        *,
        org_id: UUID,
        youtube: YouTubeOps,
        jobs: JobLookup,
        retrier: JobRetrier,
        redis_client: Any,
        catalog: CatalogSync | None = None,
        confirm_ttl_seconds: int = CONFIRM_TTL_SECONDS,
    ) -> None:
        self._org_id = org_id
        self._yt = youtube
        self._jobs = jobs
        self._retrier = retrier
        self._redis = redis_client
        self._catalog = catalog
        self._ttl = confirm_ttl_seconds

    # -- confirmation state --------------------------------------------
    @staticmethod
    def _key(session_id: str) -> str:
        return f"{CONFIRM_KEY_PREFIX}{session_id}"

    def _load_pending(self, session_id: str) -> dict[str, Any] | None:
        raw = self._redis.get(self._key(session_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    def has_pending_confirmation(self, session_id: str) -> bool:
        return self._redis.get(self._key(session_id)) is not None

    # -- entry point ----------------------------------------------------
    async def try_handle(self, session_id: str, text: str) -> str | None:
        pending = self._load_pending(session_id)
        if pending is not None:
            answer = _strip_trailing_punct(_fold(text.strip()))
            if answer in _YES:
                self._redis.delete(self._key(session_id))
                return await self._do_delete(pending)
            if answer in _NO:
                self._redis.delete(self._key(session_id))
                return "Ok, nada foi apagado."

        cmd = parse_command(text)
        if cmd is None:
            return None
        if pending is not None:
            # A new command supersedes a stale pending confirmation.
            self._redis.delete(self._key(session_id))
        if cmd.kind == "help":
            return HELP_TEXT
        assert cmd.code is not None
        try:
            if cmd.kind == "status":
                return await self._status(cmd)
            if cmd.kind == "retry":
                return await self._retry(cmd)
            return await self._mutating(session_id, cmd)
        except Exception as exc:  # noqa: BLE001 — surfaced to the operator, logged
            logger.exception("youtube chat command %s failed for %s", cmd.kind, cmd.code)
            return f"Não consegui executar o comando em {cmd.code}: {exc}"

    # -- lookups --------------------------------------------------------
    async def _rows(self, code: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._jobs.list_jobs, code)

    def _published(self, rows: list[dict[str, Any]], target: str | None) -> list[_Video]:
        seen: set[str] = set()
        out: list[_Video] = []
        for r in rows:
            vid = r.get("youtube_video_id")
            if not vid or r.get("status") not in _PUBLISHED_STATUSES or vid in seen:
                continue
            kind = _kind_of(r)
            if target and kind != target:
                continue
            seen.add(vid)
            out.append(
                _Video(vid, str(r.get("id", "")), kind, r.get("title") or "", r.get("privacy_status"))
            )
        return out

    def _none_found(self, code: str, target: str | None) -> str:
        qual = {"short": "Shorts ", "video": "vídeos "}.get(target or "", "vídeos ")
        return f"Não encontrei {qual}publicados de {code}."

    # -- commands -------------------------------------------------------
    async def _status(self, cmd: ChatCommand) -> str:
        rows = [
            r for r in await self._rows(cmd.code or "")
            if not cmd.target or _kind_of(r) == cmd.target
        ]
        if not rows:
            return f"Não encontrei vídeos de {cmd.code}."
        lines = [f"*{cmd.code}* — {len(rows)} envio(s):"]
        for r in rows[:15]:
            vid = r.get("youtube_video_id")
            link = _link(vid) if vid else "(sem link)"
            priv = _PRIVACY_LABEL.get(r.get("privacy_status") or "", r.get("privacy_status") or "?")
            line = f"• {link} — {_kind_label(_kind_of(r))} — {priv} — {r.get('status')}"
            if r.get("status") == "failed" and r.get("error_message"):
                line += f" ({str(r['error_message'])[:120]})"
            lines.append(line)
        return "\n".join(lines)

    async def _retry(self, cmd: ChatCommand) -> str:
        code = cmd.code or ""
        failed = [
            r for r in await self._rows(code)
            if r.get("status") == "failed" and (not cmd.target or _kind_of(r) == cmd.target)
        ]
        if not failed:
            return f"Não há envios com falha de {code} para refazer."
        lines = []
        for r in failed:
            jid = str(r.get("id"))
            try:
                await asyncio.to_thread(self._retrier.retry, jid)
                lines.append(f"• {_kind_label(_kind_of(r))}: reenfileirado ✅")
            except Exception as exc:  # noqa: BLE001
                logger.exception("retry failed for job %s", jid)
                lines.append(f"• {_kind_label(_kind_of(r))}: não consegui refazer — {exc}")
        return f"*{code}* — tentando de novo:\n" + "\n".join(lines)

    async def _mutating(self, session_id: str, cmd: ChatCommand) -> str:
        code = cmd.code or ""
        patch_args: dict[str, Any] = {}
        if cmd.kind == "titulo":
            if not cmd.arg:
                return f"Faltou o novo título. Exemplo: `{code} titulo Casa linda no centro`"
            title = cmd.arg if cmd.arg.upper().startswith(code) else f"{code} — {cmd.arg}"
            if len(title) > TITLE_MAX:
                return (
                    f"Título longo demais ({len(title)} caracteres, máximo {TITLE_MAX} "
                    f"incluindo o código). Nada foi alterado."
                )
            patch_args["title"] = title
        elif cmd.kind == "descricao":
            if not cmd.arg:
                return f"Faltou a nova descrição. Exemplo: `{code} descricao Texto novo`"
            if len(cmd.arg) > DESCRIPTION_MAX:
                return (
                    f"Descrição longa demais ({len(cmd.arg)} caracteres, máximo "
                    f"{DESCRIPTION_MAX}). Nada foi alterado."
                )
            patch_args["description"] = cmd.arg
        elif cmd.kind == "privacidade":
            if cmd.arg is None:
                return "Privacidade inválida. Use: *publico*, *privado* ou *nao listado*."
            patch_args["privacy_status"] = cmd.arg

        videos = self._published(await self._rows(code), cmd.target)
        if not videos:
            return self._none_found(code, cmd.target)

        if cmd.kind == "apagar":
            payload = {"code": code, "videos": [{"id": v.video_id, "kind": v.kind} for v in videos]}
            self._redis.set(self._key(session_id), json.dumps(payload), ex=self._ttl)
            listing = "\n".join(
                f"• {_link(v.video_id)} — {_kind_label(v.kind)} — {v.title or 'sem título'}"
                for v in videos
            )
            return (
                f"⚠️ Vou apagar *definitivamente* do YouTube ({code}):\n{listing}\n\n"
                "Responda *SIM* para apagar ou *NÃO* para cancelar."
            )

        lines = []
        for v in videos:
            try:
                await asyncio.to_thread(
                    self._yt.update_video_metadata,
                    org_id=self._org_id, video_id=v.video_id, **patch_args,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("update failed for %s", v.video_id)
                lines.append(f"• {_kind_label(v.kind)} {_link(v.video_id)}: falhou — {exc}")
                continue
            warn = await self._mirror(v.video_id, patch_args)
            lines.append(f"• {_kind_label(v.kind)} {_link(v.video_id)}: atualizado ✅{warn}")
        what = {"titulo": "título", "descricao": "descrição", "privacidade": "privacidade"}[cmd.kind]
        return f"*{code}* — {what}:\n" + "\n".join(lines)

    async def _mirror(self, video_id: str, patch: dict[str, Any]) -> str:
        if self._catalog is None:
            return ""
        try:
            await asyncio.to_thread(self._catalog.mirror_update, video_id, patch)
        except Exception:  # noqa: BLE001
            logger.exception("catalog mirror (update) failed for %s", video_id)
            return " (aviso: o catálogo local não foi sincronizado; rode a sincronização do painel)"
        return ""

    async def _do_delete(self, pending: dict[str, Any]) -> str:
        code = pending.get("code", "")
        lines = []
        for v in pending.get("videos", []):
            vid = v["id"]
            label = _kind_label(v.get("kind", "video"))
            try:
                await asyncio.to_thread(
                    self._yt.delete_youtube_video, org_id=self._org_id, video_id=vid
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("delete failed for %s", vid)
                lines.append(f"• {label} {_link(vid)}: falhou — {exc} (nada foi apagado)")
                continue
            warn = ""
            if self._catalog is not None:
                try:
                    await asyncio.to_thread(self._catalog.mirror_delete, vid)
                except Exception:  # noqa: BLE001
                    logger.exception("catalog mirror (delete) failed for %s", vid)
                    warn = " (aviso: catálogo local não sincronizado)"
            lines.append(f"• {label} {_link(vid)}: apagado ✅{warn}")
        return f"*{code}* — exclusão:\n" + "\n".join(lines)


# ─── Real adapters ───────────────────────────────────────────────────────
class SupabaseJobLookup:
    def __init__(self, admin_supabase: Any, org_id: UUID, *, limit: int = 50) -> None:
        self._admin, self._org_id, self._limit = admin_supabase, org_id, limit

    def list_jobs(self, code: str) -> list[dict[str, Any]]:
        resp = (
            self._admin.schema(_SCHEMA)
            .table("upload_jobs")
            .select("id,product_code,youtube_video_id,status,target_format,privacy_status,title,error_message,created_at")
            .eq("org_id", str(self._org_id))
            .eq("product_code", code.upper())
            .order("created_at", desc=True)
            .limit(self._limit)
            .execute()
        )
        return list(resp.data or [])


class SupabaseCatalogSync:
    """Mirrors the dashboard: catalog rows (videos/shorts) + the upload_jobs row."""

    _CATALOGS = ("youtube_videos", "youtube_shorts")

    def __init__(self, admin_supabase: Any, org_id: UUID) -> None:
        self._admin, self._org_id = admin_supabase, org_id

    def _t(self, name: str) -> Any:
        return self._admin.schema(_SCHEMA).table(name)

    def mirror_update(self, video_id: str, patch: dict[str, Any]) -> None:
        from datetime import datetime, timezone

        for table in self._CATALOGS:
            self._t(table).update({**patch, "synced_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("org_id", str(self._org_id)).eq("youtube_video_id", video_id).execute()
        self._t("upload_jobs").update(patch) \
            .eq("org_id", str(self._org_id)).eq("youtube_video_id", video_id).execute()

    def mirror_delete(self, video_id: str) -> None:
        for table in self._CATALOGS:
            self._t(table).delete() \
                .eq("org_id", str(self._org_id)).eq("youtube_video_id", video_id).execute()


class UploadServiceRetrier:
    """``UploadService.retry_failed_job`` + kick ``run_upload_job`` (what the
    dashboard router does with BackgroundTasks). ``schedule`` runs the job; the
    default spawns a daemon thread."""

    def __init__(
        self,
        upload_service: Any,
        org_id: UUID,
        schedule: Callable[[Callable[..., None], UUID], None] | None = None,
    ) -> None:
        self._svc, self._org_id = upload_service, org_id
        self._schedule = schedule or self._thread

    @staticmethod
    def _thread(fn: Callable[..., None], job_id: UUID) -> None:
        threading.Thread(target=fn, kwargs={"job_id": job_id}, daemon=True).start()

    def retry(self, job_id: str) -> None:
        jid = UUID(job_id)
        self._svc.retry_failed_job(job_id=jid, org_id=self._org_id)
        self._schedule(self._svc.run_upload_job, jid)


__all__ = [
    "ChatCommand", "parse_command", "YouTubeChatCommands", "HELP_TEXT",
    "SupabaseJobLookup", "SupabaseCatalogSync", "UploadServiceRetrier",
]
