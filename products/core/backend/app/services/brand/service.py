"""Org brand identity — service layer (CONTRACT §1–§4).

Org resolution (who is this request for?):

* Management routes (``settings:manage``) act ONLY in the caller's trusted home
  org (``noctus_users.org_id``) like every other core org-scoped route; an
  ``X-Noctus-Acting-Org`` naming a different org REFUSES the request
  (``409 org_selection_changed``) — the header narrows, never widens.
* ``GET /current`` is read by every product's shell for the SELECTED org. The
  header is honoured only when it names an org the caller is ALREADY entitled
  to by the trusted rows the seed effective-org resolver itself uses: an ACTIVE
  non-customer ``org_memberships`` row, or (platform staff) a LIVE
  ``platform_org_selections`` row bound to this very login (token
  ``session_id``). Anything else → 409. It can never reach an org the caller
  could not already act in.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import anyio
from fastapi import HTTPException

from noctusai_lib.api.auth.effective_org import org_selection_changed, platform_staff_role
from noctusai_lib.api.auth.mfa.aal import read_session_claims
from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository
from noctusai_lib.primitives.roles import is_customer_role

from app.services.brand import tokens as T
from app.services.brand import uploads as U
from app.services.brand.extraction import (
    EXTRACTION_MODEL,
    EXTRACTION_PROVIDER,
    BrandVoice,
    ExtractionFailed,
    extract_brand,
)
from app.services.brand.repository import ActivationRefused, BrandRepo, VersionConflict

logger = logging.getLogger(__name__)

BUCKET = "brand-identities"
JOB_TYPE = "brand.ingest"
PERMISSION = "settings:manage"
SIGNED_URL_TTL_S = 600
CURRENT_SCHEMA = "noctus.brand-current/v1"
_VERSION_ATTEMPTS = 3

EXTRACTION_QUEUED, EXTRACTION_RUNNING, EXTRACTION_DONE, EXTRACTION_FAILED = "queued", "running", "done", "failed"
_JOB_STATUS = {EXTRACTION_QUEUED: "queued", EXTRACTION_RUNNING: "running",
               EXTRACTION_DONE: "done", EXTRACTION_FAILED: "failed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Identidade visual não encontrada")


def _uuid_or_404(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise _not_found()


def _conflict(codigo: str, detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": codigo, "detail": detail})


def _extraction(row: dict) -> dict:
    return dict(((row.get("source") or {}).get("extraction")) or {})


@dataclass
class Caller:
    user_id: str
    token: Optional[str]
    org_id: str


# ── org resolution ──────────────────────────────────────────────────────────

def _clean_header(value: Any) -> Optional[str]:
    """A usable ``X-Noctus-Acting-Org`` value (non-blank str, lower-cased) else ``None``."""
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value or None


def _home_profile(core: Any, user_id: str) -> dict:
    rows = (
        core.table("noctus_users").select("org_id, org_role").eq("id", user_id).limit(1).execute().data or []
    )
    if not rows or not rows[0].get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organização não encontrada")
    return rows[0]


def resolve_manage_org(core: Any, user_id: str, acting_header: Optional[str]) -> str:
    """SYNC. The caller's home org; a pin naming any other org refuses (narrow-only)."""
    home = str(_home_profile(core, user_id)["org_id"])
    pin = _clean_header(acting_header)
    if pin is not None and pin != home.lower():
        raise org_selection_changed()
    return home


def resolve_current_org(core: Any, user_id: str, token: Optional[str], acting_header: Optional[str]) -> str:
    """SYNC. Home org, or the pinned org when the trusted rows already entitle the caller."""
    profile = _home_profile(core, user_id)
    home = str(profile["org_id"])
    pin = _clean_header(acting_header)
    if pin is None or pin == home.lower():
        return home
    try:
        pin = str(uuid.UUID(pin))
    except ValueError:
        raise org_selection_changed()
    if not is_customer_role(profile.get("org_role")):
        member = (
            core.table("org_memberships").select("org_id, org_role")
            .eq("user_id", user_id).eq("org_id", pin).eq("status", "active").limit(1).execute().data or []
        )
        if member and not is_customer_role(member[0].get("org_role")):
            return pin
    if platform_staff_role(core, user_id) is not None:
        session_id, _aal = read_session_claims(token, user_id=user_id)
        if session_id:
            live = (
                core.table("platform_org_selections").select("id")
                .eq("user_id", user_id).eq("target_org_id", pin).eq("auth_session_id", session_id)
                .is_("ended_at", "null").limit(1).execute().data or []
            )
            if live:
                return pin
    raise org_selection_changed()


# ── service ─────────────────────────────────────────────────────────────────

PermissionCheck = Callable[[str, str, str], Awaitable[None]]


@dataclass
class BrandService:
    repo: BrandRepo
    storage: Any
    jobs: JobRepository
    get_core_client: Callable[[], Any]
    require_permission: PermissionCheck
    chat: Optional[Callable[..., Awaitable[Any]]] = None
    llm_provider: str = EXTRACTION_PROVIDER
    llm_model: str = EXTRACTION_MODEL
    signed_url_ttl_s: int = SIGNED_URL_TTL_S
    clock: Callable[[], float] = time.time
    _platform_cache: dict = field(default_factory=dict)

    async def _run(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))

    # ---- callers ----------------------------------------------------------

    async def manager(self, user: Any, token: Optional[str], acting_header: Optional[str]) -> Caller:
        uid = str(user.id)
        org_id = await self._run(resolve_manage_org, self.get_core_client(), uid, acting_header)
        await self.require_permission(uid, org_id, PERMISSION)
        return Caller(user_id=uid, token=token, org_id=org_id)

    async def reader(self, user: Any, token: Optional[str], acting_header: Optional[str]) -> Caller:
        uid = str(user.id)
        org_id = await self._run(resolve_current_org, self.get_core_client(), uid, token, acting_header)
        return Caller(user_id=uid, token=token, org_id=org_id)

    # ---- platform ---------------------------------------------------------

    async def platform_row(self) -> Optional[dict]:
        return await self._run(self.repo.active, None)

    async def platform_tokens(self) -> dict:
        row = await self.platform_row()
        if row is not None:
            try:
                return T.assert_servable(row["tokens"])
            except T.BrandTokensError as exc:
                logger.error("brand.platform_row_invalid id=%s errors=%s", row.get("id"), exc.errors[:5])
        return T.platform_tokens()

    # ---- GET /current -----------------------------------------------------

    async def signed_assets(self, org_id: Optional[str], assets: dict) -> dict:
        out: dict[str, Any] = {slot: None for slot in U.IMAGE_SLOTS}
        out["fonts"] = []
        prefix = f"{org_id}/"
        for slot in U.IMAGE_SLOTS:
            path = assets.get(slot)
            if isinstance(path, str) and org_id and path.startswith(prefix):
                out[slot] = await self.storage.signed_url(
                    bucket=BUCKET, key=path, expires_in_seconds=self.signed_url_ttl_s)
        for font in assets.get("fonts") or []:
            path = font.get("path") if isinstance(font, dict) else None
            family = font.get("family") if isinstance(font, dict) else None
            if not (isinstance(path, str) and org_id and path.startswith(prefix)):
                continue
            if not (isinstance(family, str) and T.FONT_FAMILY_RE.match(family)):
                continue
            url = await self.storage.signed_url(bucket=BUCKET, key=path, expires_in_seconds=self.signed_url_ttl_s)
            out["fonts"].append({"family": family, "weight": font.get("weight"), "url": url})
        return out

    def _etag(self, row_id: Optional[str], version: Any, stamp: Any, tokens: dict, assets: dict) -> str:
        # The URL-validity bucket is part of the tag: a 304 is only ever answered
        # while the signed URLs the client holds still have >= TTL/2 to live.
        bucket = int(self.clock() // max(1, self.signed_url_ttl_s // 2))
        raw = json.dumps([row_id, version, stamp, tokens, assets, bucket], sort_keys=True, default=str)
        return '"' + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32] + '"'

    async def current(self, caller: Caller) -> tuple[dict, str]:
        row = await self._run(self.repo.active, caller.org_id)
        source = "org"
        tokens: Optional[dict] = None
        if row is not None:
            try:
                tokens = T.assert_servable(row["tokens"])
            except T.BrandTokensError as exc:
                logger.error("brand.active_row_invalid org=%s id=%s errors=%s",
                             caller.org_id, row.get("id"), exc.errors[:5])
                row = None
        if row is None:
            source = "platform"
            row = await self.platform_row()
            tokens = await self.platform_tokens()
            if row is None:
                logger.error("brand.platform_row_missing — serving the built-in NOC standard (migration 089 applied?)")
        assets_src = (row or {}).get("assets") or {}
        assets = await self.signed_assets(caller.org_id if source == "org" else None, assets_src)
        body = {
            "schema": CURRENT_SCHEMA,
            "source": source,
            "org_id": caller.org_id,
            "identity_id": (row or {}).get("id"),
            "version": (row or {}).get("version"),
            "tokens": tokens,
            "assets": assets,
            "updated_at": (row or {}).get("activated_at") or (row or {}).get("created_at"),
        }
        etag = self._etag(body["identity_id"], body["version"], body["updated_at"], tokens, assets_src)
        return body, etag

    # ---- management reads -------------------------------------------------

    async def list_identities(self, caller: Caller) -> list[dict]:
        rows = await self._run(self.repo.list_for, caller.org_id)
        return [self._summary(r) for r in rows]

    def _summary(self, row: dict) -> dict:
        return {k: row.get(k) for k in ("id", "version", "status", "tokens", "assets", "validation",
                                         "created_by", "created_at", "activated_at")}

    async def get_identity(self, caller: Caller, identity_id: str) -> dict:
        row = await self._get_or_404(caller, identity_id)
        return {k: row.get(k) for k in ("id", "org_id", "version", "status", "tokens", "brand_book", "voice",
                                         "assets", "source", "validation", "created_by", "created_at",
                                         "activated_at")}

    async def _get_or_404(self, caller: Caller, identity_id: str) -> dict:
        row = await self._run(self.repo.get, _uuid_or_404(identity_id), caller.org_id)
        if row is None:
            raise _not_found()
        return row

    # ---- ingestion --------------------------------------------------------

    async def _insert_draft(self, base: dict) -> dict:
        last: Optional[Exception] = None
        for _ in range(_VERSION_ATTEMPTS):
            version = await self._run(self.repo.next_version, base["org_id"])
            try:
                return await self._run(self.repo.insert, {**base, "version": version})
            except VersionConflict as exc:
                last = exc
        raise HTTPException(status_code=409, detail="Conflito ao numerar a versão; tente novamente") from last

    async def ingest(self, caller: Caller, files: list[U.AcceptedFile], descriptions: dict[str, str]) -> dict:
        identity_id = str(uuid.uuid4())
        stored: list[dict] = []
        try:
            for f in files:
                key = f"{caller.org_id}/{identity_id}/source/{f.index:02d}.{f.stored_ext}"
                await self.storage.put(bucket=BUCKET, key=key, data=f.data, content_type=f.mime)
                stored.append({"index": f.index, "name": f.name, "kind": f.kind, "mime": f.mime,
                               "size": f.size, "sha256": f.sha256, "path": key,
                               "description": descriptions.get(f.name, "")})
        except Exception as exc:
            logger.error("brand.upload_store_failed org=%s err=%s", caller.org_id, type(exc).__name__)
            for s in stored:
                try:
                    await self.storage.delete(bucket=BUCKET, key=s["path"])
                except Exception as cleanup_exc:  # noqa: BLE001 — logged; the bucket prefix is orphan-swept by path
                    logger.warning("brand.upload_cleanup_failed path_index=%s err=%s",
                                   s["index"], type(cleanup_exc).__name__)
            raise HTTPException(status_code=503, detail="Falha ao armazenar os arquivos; tente novamente") from exc

        platform = await self.platform_tokens()
        row = await self._insert_draft({
            "id": identity_id, "org_id": caller.org_id, "status": "draft",
            "tokens": platform, "brand_book": "", "voice": {}, "assets": {},
            "source": {"files": stored, "extraction": {"status": EXTRACTION_QUEUED, "job_id": None,
                                                        "model": self.llm_model, "queued_at": _now_iso()}},
            "validation": {}, "created_by": caller.user_id,
        })
        try:
            job = await self.jobs.enqueue(
                type=JOB_TYPE, payload={"identity_id": identity_id, "org_id": caller.org_id},
                max_retries=0, dedupe_key=f"{JOB_TYPE}:{identity_id}",
            )
        except Exception as exc:
            logger.error("brand.enqueue_failed identity=%s err=%s", identity_id, type(exc).__name__)
            await self._fail(row, "fila_indisponivel", "não foi possível agendar a extração")
            raise HTTPException(status_code=503, detail="Fila de processamento indisponível; tente novamente") from exc
        source = dict(row.get("source") or {})
        source["extraction"] = {**_extraction(row), "job_id": job.id}
        updated = await self._run(self.repo.update, identity_id, caller.org_id, {"source": source},
                                  statuses=("draft", "failed"))
        if updated is None:
            logger.error("brand.job_link_failed identity=%s job=%s", identity_id, job.id)
        return {"job_id": job.id, "identity_id": identity_id}

    async def job_status(self, caller: Caller, job_id: str) -> dict:
        if not isinstance(job_id, str) or not job_id or len(job_id) > 64:
            raise HTTPException(status_code=404, detail="Job não encontrado")
        row = await self._run(self.repo.find_by_job, job_id, caller.org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Job não encontrado")
        ext = _extraction(row)
        status = _JOB_STATUS.get(ext.get("status"), "failed")
        out: dict[str, Any] = {"job_id": job_id, "status": status, "identity_id": row["id"]}
        if status == "failed":
            out["error"] = {"code": ext.get("error_code") or "desconhecido",
                            "detail": ext.get("error") or "falha sem detalhe registrado"}
        return out

    async def _fail(self, row: dict, codigo: str, detail: str) -> None:
        source = dict(row.get("source") or {})
        source["extraction"] = {**_extraction(row), "status": EXTRACTION_FAILED, "error_code": codigo,
                                "error": detail[:500], "finished_at": _now_iso()}
        updated = await self._run(self.repo.update, row["id"], row["org_id"],
                                  {"status": "failed", "source": source}, statuses=("draft",))
        if updated is None:
            logger.error("brand.fail_write_lost identity=%s codigo=%s", row.get("id"), codigo)

    async def handle_job(self, job: Job) -> None:
        """Seed jobs ``Worker`` handler. Idempotent: a finished/failed identity is left alone."""
        payload = job.payload or {}
        identity_id, org_id = payload.get("identity_id"), payload.get("org_id")
        if not identity_id or not org_id:
            raise DeadLetterError("payload sem identity_id/org_id")
        row = await self._run(self.repo.get, identity_id, org_id)
        if row is None or row["status"] != "draft" or _extraction(row).get("status") in (EXTRACTION_DONE, EXTRACTION_FAILED):
            return
        source = dict(row.get("source") or {})
        source["extraction"] = {**_extraction(row), "status": EXTRACTION_RUNNING, "started_at": _now_iso()}
        row = await self._run(self.repo.update, identity_id, org_id, {"source": source}, statuses=("draft",)) or row

        try:
            files, descriptions = await self._load_files(row)
            result = await extract_brand(
                files, descriptions, org_id=org_id, chat=self.chat,
                provider=self.llm_provider, model=self.llm_model,
            )
        except ExtractionFailed as exc:
            logger.warning("brand.extraction_failed identity=%s codigo=%s", identity_id, exc.codigo)
            await self._fail(row, exc.codigo, exc.detail)
            raise DeadLetterError(exc.codigo)

        platform = await self.platform_tokens()
        validated = T.validate_tokens(result.extraction.tokens, platform=platform, lenient=True)
        assets = self._map_assets(row, files, validated.tokens)
        source = dict(row.get("source") or {})
        source["extraction"] = {**_extraction(row), "status": EXTRACTION_DONE, "finished_at": _now_iso(),
                                "model": result.model, "provider": self.llm_provider,
                                "usage": result.usage, "usage_measured": result.usage is not None}
        if result.usage is None:
            logger.warning("brand.extraction_usage_unmeasured identity=%s model=%s", identity_id, result.model)
        updated = await self._run(self.repo.update, identity_id, org_id, {
            "tokens": validated.tokens,
            "brand_book": result.extraction.brand_book,
            "voice": result.extraction.voice.model_dump(mode="json"),
            "assets": assets,
            "validation": validated.as_validation(),
            "source": source,
        }, statuses=("draft",))
        if updated is None:
            logger.warning("brand.extraction_result_dropped identity=%s (row left draft state)", identity_id)

    async def _load_files(self, row: dict) -> tuple[list[U.AcceptedFile], dict[str, str]]:
        files: list[U.AcceptedFile] = []
        descriptions: dict[str, str] = {}
        for meta in (row.get("source") or {}).get("files") or []:
            blob = await self.storage.get(bucket=BUCKET, key=meta["path"])
            if blob is None:
                raise ExtractionFailed("arquivo_indisponivel", f"arquivo #{meta.get('index')} não encontrado no armazenamento")
            files.append(U.AcceptedFile(index=int(meta["index"]), name=meta["name"], kind=meta["kind"],
                                        mime=meta["mime"], data=blob.data))
            if meta.get("description"):
                descriptions[meta["name"]] = meta["description"]
        return files, descriptions

    def _map_assets(self, row: dict, files: list[U.AcceptedFile], tokens: dict) -> dict:
        by_index = {m["index"]: m for m in (row.get("source") or {}).get("files") or []}
        assets: dict[str, Any] = {slot: None for slot in U.IMAGE_SLOTS}
        assets["fonts"] = []
        families = {spec["family"].lower(): spec["family"] for spec in (tokens.get("fonts") or {}).values()}
        for f in files:
            meta = by_index.get(f.index, {})
            if f.kind == U.KIND_IMAGE:
                slot = U.slot_for_image(f.name, meta.get("description", ""))
                if slot and assets[slot] is None:
                    assets[slot] = meta.get("path")
            elif f.kind == U.KIND_FONT and len(assets["fonts"]) < U.MAX_FONTS:
                guess = U.font_family_from_name(f.name)
                family = families.get(guess.lower(), guess)
                assets["fonts"].append({"path": meta.get("path"), "family": family, "weight": None})
        return assets

    # ---- edits ------------------------------------------------------------

    def _editable(self, row: dict) -> None:
        if row["status"] != "draft":
            raise _conflict("nao_rascunho", "Apenas rascunhos podem ser editados")
        status = _extraction(row).get("status")
        if status in (EXTRACTION_QUEUED, EXTRACTION_RUNNING):
            raise _conflict("extracao_em_andamento", "A extração ainda está em andamento")

    async def patch(self, caller: Caller, identity_id: str, *, tokens: Optional[dict],
                    brand_book: Optional[str], voice: Optional[BrandVoice]) -> dict:
        row = await self._get_or_404(caller, identity_id)
        self._editable(row)
        fields: dict[str, Any] = {}
        if tokens is not None:
            merged = _merge_tokens(row.get("tokens") or {}, tokens)
            try:
                validated = T.validate_tokens(merged, platform=await self.platform_tokens(), lenient=False)
            except T.BrandTokensError as exc:
                raise HTTPException(status_code=422, detail={"code": "tokens_invalidos", "errors": exc.errors})
            fields["tokens"] = validated.tokens
            fields["validation"] = validated.as_validation()
        if brand_book is not None:
            fields["brand_book"] = brand_book
        if voice is not None:
            fields["voice"] = voice.model_dump(mode="json")
        if not fields:
            return await self.get_identity(caller, identity_id)
        updated = await self._run(self.repo.update, row["id"], caller.org_id, fields, statuses=("draft",))
        if updated is None:
            raise _conflict("nao_rascunho", "A identidade mudou de estado; recarregue")
        return await self.get_identity(caller, identity_id)

    async def activate(self, caller: Caller, identity_id: str) -> dict:
        row = await self._get_or_404(caller, identity_id)
        if row["status"] == "draft":
            self._editable(row)
        try:
            T.assert_servable(row.get("tokens"))
        except T.BrandTokensError as exc:
            raise HTTPException(status_code=422, detail={"code": "tokens_invalidos", "errors": exc.errors})
        try:
            await self._run(self.repo.activate, row["id"], caller.org_id)
        except ActivationRefused as exc:
            if exc.codigo == "not_found":
                raise _not_found()
            raise _conflict("status_invalido", "Esta versão não pode ser ativada")
        return await self.get_identity(caller, identity_id)

    async def upload_asset(self, caller: Caller, identity_id: str, *, slot: str, file: U.AcceptedFile,
                           family: Optional[str]) -> dict:
        row = await self._get_or_404(caller, identity_id)
        self._editable(row)
        if slot not in U.ASSET_SLOTS:
            raise HTTPException(status_code=422, detail={"code": "slot_invalido", "slots": list(U.ASSET_SLOTS)})
        assets = dict(row.get("assets") or {})
        if slot == "font":
            if file.kind != U.KIND_FONT:
                raise HTTPException(status_code=422, detail={"code": "tipo_incompativel", "detail": "slot font exige .woff2"})
            fam = family or U.font_family_from_name(file.name)
            if not T.FONT_FAMILY_RE.match(fam):
                raise HTTPException(status_code=422, detail={"code": "familia_invalida"})
            fonts = list(assets.get("fonts") or [])
            if len(fonts) >= U.MAX_FONTS:
                raise _conflict("fontes_demais", f"No máximo {U.MAX_FONTS} fontes")
        elif file.kind != U.KIND_IMAGE:
            raise HTTPException(status_code=422, detail={"code": "tipo_incompativel", "detail": "logos exigem PNG, JPG ou WEBP"})
        key = f"{caller.org_id}/{row['id']}/assets/{slot}-{uuid.uuid4().hex[:12]}.{file.stored_ext}"
        try:
            await self.storage.put(bucket=BUCKET, key=key, data=file.data, content_type=file.mime)
        except Exception as exc:
            logger.error("brand.asset_store_failed identity=%s err=%s", row["id"], type(exc).__name__)
            raise HTTPException(status_code=503, detail="Falha ao armazenar o arquivo; tente novamente") from exc
        if slot == "font":
            assets["fonts"] = fonts + [{"path": key, "family": fam, "weight": None}]
        else:
            assets[slot] = key
        updated = await self._run(self.repo.update, row["id"], caller.org_id, {"assets": assets}, statuses=("draft",))
        if updated is None:
            raise _conflict("nao_rascunho", "A identidade mudou de estado; recarregue")
        return await self.get_identity(caller, identity_id)


def _merge_tokens(current: dict, patch: dict) -> dict:
    """Field-level partial update. ``light``/``dark`` merge per key; ``"dark": null``
    drops the dark palette (re-derived from light); ``radius``/``fonts`` replace.
    Unknown top-level keys are passed through so strict validation refuses them."""
    if not isinstance(patch, dict):
        return patch
    merged = {k: v for k, v in current.items()}
    for key, value in patch.items():
        if key in ("light", "dark") and isinstance(value, dict) and isinstance(current.get(key), dict):
            merged[key] = {**current[key], **value}
        elif key == "dark" and value is None:
            merged.pop("dark", None)
        else:
            merged[key] = value
    return merged
