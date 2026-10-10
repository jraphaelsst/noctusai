"""Branding service — the richer brand-kit model (tokens, brand book,
components, assets), per org, database only.

A *branding* is a ``mc_brand_kits`` row (see migration 204). Owners are BRANDS:
``marca_id`` links to ``social_wiring.marcas``. The org's **Branding Template**
is the single row with ``is_template = true`` (no marca); "create from template"
copies it, blobs included.

Writes go through the service-role client and always filter on ``org_id``
(resolved from the token). Binary assets live in the PRIVATE
``social-wiring-branding`` bucket under ``{org_id}/branding/{kit_id}/…`` (the
first path segment is the org — the object-RLS key) and are exposed to the UI
only as short-TTL signed URLs minted per read.

There are no multi-statement transactions through PostgREST: ``import_bundle``
therefore VALIDATES the whole bundle first (``parse_bundle``) and only then
writes; the write path is idempotent (upsert by slug / component name / asset
kind+label), so a partial failure is repaired by re-running the same import.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
import uuid
from typing import Any, Optional

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.accents import fold_accents_ascii

from app.modules.media_creation.branding.bundle import (
    COMPONENT_NAME,
    MAX_ASSET_BYTES,
    ParsedBundle,
    parse_bundle,
    sniff_asset,
)
from app.modules.media_creation.branding.html_guard import (
    PreviewHtmlRejected,
    validate_preview_html,
)
from app.modules.media_creation.branding.tokens_schema import (
    TokensValidationError,
    validate_tokens,
)
from app.modules.media_creation.deps import BRANDING_BUCKET, SIGNED_URL_TTL_SECONDS

logger = logging.getLogger(__name__)

_KIT_SUMMARY_COLS = "id,name,slug,marca_id,is_template,default_lang,created_at,updated_at"
_KIND_FAMILY = {"logo": "image", "model": "image", "font": "font"}


class BrandingError(Exception):
    """A branding operation was refused. ``status`` is the HTTP status."""

    def __init__(self, message: str, status: int = 400, errors: Optional[list[str]] = None):
        super().__init__(message)
        self.status = status
        #: Every individual problem when there are several (a bundle that failed
        #: validation); empty when the single ``message`` says it all.
        self.errors = errors or []


class BrandingNotFound(BrandingError):
    def __init__(self, message: str = "Branding não encontrado"):
        super().__init__(message, status=404)


def slugify(text: str) -> str:
    norm = fold_accents_ascii(text)
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug or "branding"


def _safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", label)[:120] or "file"


def decode_b64(value: str, *, where: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BrandingError(f"{where}: invalid base64") from exc


class BrandingService:
    def __init__(self, db, org_id: str, storage: StorageBackend):
        self.db = db
        self.org_id = org_id
        self.storage = storage

    # ── reads ────────────────────────────────────────────────────────────

    def overview(self) -> dict[str, Any]:
        """Brandings grouped by marca (+ unassigned + the template)."""
        marcas = (
            self.db.table("marcas")
            .select("id,name,slug,kind")
            .eq("org_id", self.org_id)
            .order("name")
            .execute()
            .data
            or []
        )
        kits = (
            self.db.table("mc_brand_kits")
            .select(_KIT_SUMMARY_COLS)
            .eq("org_id", self.org_id)
            .order("name")
            .execute()
            .data
            or []
        )
        template = next((k for k in kits if k.get("is_template")), None)
        by_marca: dict[str, list[dict]] = {}
        unassigned: list[dict] = []
        known = {m["id"] for m in marcas}
        for kit in kits:
            if kit.get("is_template"):
                continue
            if kit.get("marca_id") in known:
                by_marca.setdefault(kit["marca_id"], []).append(kit)
            else:
                unassigned.append(kit)
        return {
            "template": template,
            "marcas": [{**m, "brandings": by_marca.get(m["id"], [])} for m in marcas],
            "unassigned": unassigned,
        }

    def _kit_row(self, kit_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table("mc_brand_kits")
            .select("*")
            .eq("id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def _require_kit(self, kit_id: str) -> dict[str, Any]:
        kit = self._kit_row(kit_id)
        if not kit:
            raise BrandingNotFound()
        return kit

    async def detail(self, kit_id: str) -> dict[str, Any]:
        kit = self._require_kit(kit_id)
        marca = None
        if kit.get("marca_id"):
            rows = (
                self.db.table("marcas")
                .select("id,name,slug,kind")
                .eq("id", kit["marca_id"])
                .eq("org_id", self.org_id)
                .execute()
                .data
            )
            marca = rows[0] if rows else None
        components = (
            self.db.table("mc_brand_components")
            .select("*")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .order("position")
            .execute()
            .data
            or []
        )
        refs = (
            self.db.table("mc_brand_references")
            .select("*")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .order("created_at")
            .execute()
            .data
            or []
        )
        assets = [await self._with_signed_url(r) for r in refs]
        return {**kit, "marca": marca, "components": components, "assets": assets}

    async def _with_signed_url(self, ref: dict[str, Any]) -> dict[str, Any]:
        out = {**ref, "signed_url": None, "signed_url_error": None}
        path = ref.get("storage_path")
        if not path:
            return out
        try:
            out["signed_url"] = await self.storage.signed_url(
                bucket=BRANDING_BUCKET, key=path, expires_in_seconds=SIGNED_URL_TTL_SECONDS
            )
        except Exception as exc:  # surfaced on the row, never swallowed
            logger.warning("branding: signing %s failed: %s", path, exc)
            out["signed_url_error"] = str(exc)[:200]
        return out

    # ── helpers ──────────────────────────────────────────────────────────

    def _check_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas")
            .select("id")
            .eq("id", marca_id)
            .eq("org_id", self.org_id)
            .execute()
            .data
        )
        if not rows:
            raise BrandingError("Marca não encontrada", status=404)

    def _unique_slug(self, marca_id: Optional[str], name: str) -> str:
        base = slugify(name)
        q = self.db.table("mc_brand_kits").select("slug").eq("org_id", self.org_id)
        q = q.eq("marca_id", marca_id) if marca_id else q.is_("marca_id", "null")
        taken = {r["slug"] for r in (q.execute().data or []) if r.get("slug")}
        slug, n = base, 2
        while slug in taken:
            slug = f"{base}-{n}"
            n += 1
        return slug

    def _template_row(self) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table("mc_brand_kits")
            .select("*")
            .eq("org_id", self.org_id)
            .eq("is_template", True)
            .execute()
            .data
        )
        return rows[0] if rows else None

    # ── create / update / delete ─────────────────────────────────────────

    async def create(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        marca_id = data.get("marca_id")
        if marca_id:
            self._check_marca(marca_id)
        template = None
        if data.get("from_template"):
            template = self._template_row()
            if not template:
                raise BrandingError(
                    "Não há Branding Template nesta organização — importe-o primeiro", status=409
                )
        kit_id = str(uuid.uuid4())
        row: dict[str, Any] = {
            "id": kit_id,
            "org_id": self.org_id,
            "created_by": user_id,
            "name": data["name"],
            "slug": self._unique_slug(marca_id, data["name"]),
            "marca_id": marca_id,
            "persona": data.get("persona", ""),
            "design_system": "",
            "default_lang": data.get("default_lang", "pt-BR"),
            "is_template": False,
            "tokens": None,
            "brand_book": "",
            "sections": [],
        }
        if template:
            row.update(
                tokens=template.get("tokens"),
                brand_book=template.get("brand_book") or "",
                sections=template.get("sections") or [],
            )
        self.db.table("mc_brand_kits").insert(row).execute()
        if template:
            await self._copy_children(template["id"], kit_id)
        return await self.detail(kit_id)

    async def _copy_children(self, from_kit: str, to_kit: str) -> None:
        comps = (
            self.db.table("mc_brand_components")
            .select("*")
            .eq("brand_kit_id", from_kit)
            .eq("org_id", self.org_id)
            .execute()
            .data
            or []
        )
        for c in comps:
            self.db.table("mc_brand_components").insert(
                {
                    "id": str(uuid.uuid4()),
                    "org_id": self.org_id,
                    "brand_kit_id": to_kit,
                    "name": c["name"],
                    "guideline_md": c.get("guideline_md") or "",
                    "preview_html": c.get("preview_html") or "",
                    "position": c.get("position") or 0,
                }
            ).execute()
        refs = (
            self.db.table("mc_brand_references")
            .select("*")
            .eq("brand_kit_id", from_kit)
            .eq("org_id", self.org_id)
            .execute()
            .data
            or []
        )
        for r in refs:
            if r.get("storage_path"):
                blob = await self.storage.get(bucket=BRANDING_BUCKET, key=r["storage_path"])
                if blob is None:
                    raise BrandingError(
                        f"Arquivo do template ausente no storage: {r.get('label')}", status=409
                    )
                await self._store_asset(
                    to_kit, r["kind"], r["label"], blob.data, r.get("content_type") or "", r.get("notes")
                )
            else:
                self.db.table("mc_brand_references").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "org_id": self.org_id,
                        "brand_kit_id": to_kit,
                        "kind": r["kind"],
                        "label": r["label"],
                        "asset_url": r.get("asset_url"),
                        "notes": r.get("notes"),
                    }
                ).execute()

    async def update(self, kit_id: str, data: dict[str, Any]) -> dict[str, Any]:
        kit = self._require_kit(kit_id)
        patch = dict(data)
        if "marca_id" in patch:
            if kit.get("is_template") and patch["marca_id"]:
                raise BrandingError("O Branding Template não pertence a nenhuma marca")
            if patch["marca_id"]:
                self._check_marca(patch["marca_id"])
        if patch.get("tokens") is not None:
            try:
                patch["tokens"] = validate_tokens(patch["tokens"])
            except TokensValidationError as exc:
                raise BrandingError(f"tokens inválidos: {exc}", status=422) from exc
        elif "tokens" in patch:
            patch.pop("tokens")  # null does not clear: a branding keeps its tokens
        if patch.get("sections") is not None:
            patch["sections"] = [
                {"title": s["title"], "markdown": s.get("markdown", "")} for s in patch["sections"]
            ]
        patch = {k: v for k, v in patch.items() if v is not None or k == "marca_id"}
        if patch:
            self.db.table("mc_brand_kits").update(patch).eq("id", kit_id).eq(
                "org_id", self.org_id
            ).execute()
        return await self.detail(kit_id)

    async def delete(self, kit_id: str) -> dict[str, Any]:
        kit = self._require_kit(kit_id)
        if kit.get("is_template"):
            raise BrandingError("O Branding Template não pode ser removido", status=409)
        used = (
            self.db.table("mc_posts")
            .select("id")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .limit(1)
            .execute()
        )
        if used.data:
            raise BrandingError(
                "Branding em uso — exclua os posts antes de remover este branding", status=400
            )
        refs = (
            self.db.table("mc_brand_references")
            .select("storage_path")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
            .data
            or []
        )
        self.db.table("mc_brand_kits").delete().eq("id", kit_id).eq("org_id", self.org_id).execute()
        orphaned = 0
        for r in refs:
            if r.get("storage_path"):
                try:
                    await self.storage.delete(bucket=BRANDING_BUCKET, key=r["storage_path"])
                except Exception as exc:
                    orphaned += 1
                    logger.warning("branding: orphaned blob %s after delete: %s", r["storage_path"], exc)
        return {"deleted": kit_id, "orphaned_assets": orphaned}

    # ── components ───────────────────────────────────────────────────────

    def upsert_component(self, kit_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_kit(kit_id)
        name = data["name"].strip()
        if not COMPONENT_NAME.match(name):
            raise BrandingError(f"Nome de componente inválido: {name!r}", status=422)
        try:
            if data.get("preview_html"):
                validate_preview_html(data["preview_html"])
        except PreviewHtmlRejected as exc:
            raise BrandingError(f"preview_html rejeitado: {exc}", status=422) from exc
        existing = (
            self.db.table("mc_brand_components")
            .select("*")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .eq("name", name)
            .execute()
            .data
        )
        fields = {
            "guideline_md": data.get("guideline_md", ""),
            "preview_html": data.get("preview_html", ""),
        }
        if existing:
            res = (
                self.db.table("mc_brand_components")
                .update(fields)
                .eq("id", existing[0]["id"])
                .eq("org_id", self.org_id)
                .execute()
            )
            return res.data[0] if res.data else {**existing[0], **fields}
        count = (
            self.db.table("mc_brand_components")
            .select("id")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .execute()
            .data
            or []
        )
        row = {
            "id": str(uuid.uuid4()),
            "org_id": self.org_id,
            "brand_kit_id": kit_id,
            "name": name,
            "position": len(count),
            **fields,
        }
        res = self.db.table("mc_brand_components").insert(row).execute()
        return res.data[0] if res.data else row

    def delete_component(self, component_id: str) -> None:
        rows = (
            self.db.table("mc_brand_components")
            .select("id")
            .eq("id", component_id)
            .eq("org_id", self.org_id)
            .execute()
            .data
        )
        if not rows:
            raise BrandingError("Componente não encontrado", status=404)
        self.db.table("mc_brand_components").delete().eq("id", component_id).eq(
            "org_id", self.org_id
        ).execute()

    # ── assets ───────────────────────────────────────────────────────────

    async def add_asset(
        self, kit_id: str, kind: str, label: str, data: bytes, notes: Optional[str]
    ) -> dict[str, Any]:
        self._require_kit(kit_id)
        if len(data) > MAX_ASSET_BYTES:
            raise BrandingError(
                f"Arquivo maior que {MAX_ASSET_BYTES // (1024 * 1024)} MB", status=413
            )
        sniffed = sniff_asset(data)
        if sniffed is None:
            raise BrandingError(
                "Tipo de arquivo não aceito (PNG/JPEG/WebP/GIF ou fonte WOFF/WOFF2/TTF/OTF)",
                status=415,
            )
        ctype, family = sniffed
        if _KIND_FAMILY[kind] != family:
            raise BrandingError(f"Um arquivo {family} não pode ser {kind!r}", status=422)
        row = await self._store_asset(kit_id, kind, label, data, ctype, notes)
        return await self._with_signed_url(row)

    async def _store_asset(
        self, kit_id: str, kind: str, label: str, data: bytes, ctype: str, notes: Optional[str]
    ) -> dict[str, Any]:
        sniffed = sniff_asset(data)
        content_type = sniffed[0] if sniffed else ctype
        key = f"{self.org_id}/branding/{kit_id}/{kind}/{uuid.uuid4().hex[:12]}-{_safe_label(label)}"
        await self.storage.put(
            bucket=BRANDING_BUCKET,
            key=key,
            data=data,
            content_type=content_type,
            metadata={"kit_id": kit_id, "kind": kind},
        )
        existing = (
            self.db.table("mc_brand_references")
            .select("*")
            .eq("brand_kit_id", kit_id)
            .eq("org_id", self.org_id)
            .eq("kind", kind)
            .eq("label", label)
            .execute()
            .data
        )
        fields = {
            "storage_path": key,
            "content_type": content_type,
            "size_bytes": len(data),
            "asset_url": None,
            "notes": notes,
        }
        old_path = None
        if existing and existing[0].get("storage_path"):
            old_path = existing[0]["storage_path"]
        if existing:
            res = (
                self.db.table("mc_brand_references")
                .update(fields)
                .eq("id", existing[0]["id"])
                .eq("org_id", self.org_id)
                .execute()
            )
            row = res.data[0] if res.data else {**existing[0], **fields}
        else:
            row = {
                "id": str(uuid.uuid4()),
                "org_id": self.org_id,
                "brand_kit_id": kit_id,
                "kind": kind,
                "label": label,
                **fields,
            }
            res = self.db.table("mc_brand_references").insert(row).execute()
            row = res.data[0] if res.data else row
        if old_path and old_path != key:
            try:
                await self.storage.delete(bucket=BRANDING_BUCKET, key=old_path)
            except Exception as exc:
                logger.warning("branding: orphaned replaced blob %s: %s", old_path, exc)
        return row

    async def delete_asset(self, reference_id: str) -> None:
        rows = (
            self.db.table("mc_brand_references")
            .select("id,storage_path")
            .eq("id", reference_id)
            .eq("org_id", self.org_id)
            .execute()
            .data
        )
        if not rows:
            raise BrandingError("Referência não encontrada", status=404)
        self.db.table("mc_brand_references").delete().eq("id", reference_id).eq(
            "org_id", self.org_id
        ).execute()
        path = rows[0].get("storage_path")
        if path:
            try:
                await self.storage.delete(bucket=BRANDING_BUCKET, key=path)
            except Exception as exc:
                logger.warning("branding: orphaned blob %s: %s", path, exc)

    # ── import ───────────────────────────────────────────────────────────

    async def import_bundle(
        self,
        *,
        files: list[tuple[str, bytes]],
        marca_id: Optional[str],
        is_template: bool,
        name: Optional[str],
        user_id: str,
    ) -> dict[str, Any]:
        """Create or update a branding from a design-system folder's files.

        Everything is validated BEFORE the first write. Re-running the same
        import is safe (idempotent upserts), which is also the repair path
        after a partial failure.
        """
        if is_template and marca_id:
            raise BrandingError("O Branding Template não pertence a uma marca", status=422)
        if not is_template and not marca_id:
            raise BrandingError("Escolha a marca dona do branding (marca_id)", status=422)
        if marca_id:
            self._check_marca(marca_id)
        from app.modules.media_creation.branding.bundle import BundleError

        try:
            parsed: ParsedBundle = parse_bundle(files)
        except BundleError as exc:
            raise BrandingError(
                "Pacote de design system inválido", status=422, errors=exc.errors
            ) from exc
        display_name = (name or parsed.name).strip()

        if is_template:
            existing = self._template_row()
        else:
            slug = slugify(display_name)
            rows = (
                self.db.table("mc_brand_kits")
                .select("*")
                .eq("org_id", self.org_id)
                .eq("marca_id", marca_id)
                .eq("slug", slug)
                .execute()
                .data
            )
            existing = rows[0] if rows else None

        fields = {
            "name": display_name,
            "tokens": parsed.tokens,
            "brand_book": parsed.brand_book,
            "sections": parsed.sections,
        }
        if existing:
            kit_id, action = existing["id"], "updated"
            self.db.table("mc_brand_kits").update(fields).eq("id", kit_id).eq(
                "org_id", self.org_id
            ).execute()
        else:
            kit_id, action = str(uuid.uuid4()), "created"
            self.db.table("mc_brand_kits").insert(
                {
                    "id": kit_id,
                    "org_id": self.org_id,
                    "created_by": user_id,
                    "slug": "branding-template" if is_template else slugify(display_name),
                    "marca_id": None if is_template else marca_id,
                    "is_template": is_template,
                    "persona": "",
                    "design_system": "",
                    "default_lang": "pt-BR",
                    **fields,
                }
            ).execute()

        for comp in parsed.components:
            self.upsert_component(
                kit_id,
                {
                    "name": comp.name,
                    "guideline_md": comp.guideline_md,
                    "preview_html": comp.preview_html,
                },
            )
        for asset in parsed.assets:
            await self._store_asset(kit_id, asset.kind, asset.label, asset.data, asset.content_type, None)

        return {
            "id": kit_id,
            "action": action,
            "is_template": is_template,
            "name": display_name,
            "components": len(parsed.components),
            "assets": len(parsed.assets),
            "sections": len(parsed.sections),
            "ignored": parsed.ignored,
            "warnings": parsed.warnings,
        }
