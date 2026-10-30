"""Platform template library -- business rules (admin > Templates).

Edit = new version: a DRAFT is edited in place; an ACTIVE/ARCHIVED version is frozen, so editing
it spawns a new draft (version N+1) seeded from it. ``activate`` archives the previous active
version of the same (product, kind, key) atomically (the migration's RPC).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from .repository import FrozenVersion, NotFound, PlatformTemplateRepo, VersionConflict  # noqa: F401
from app.services.brand import tokens as brand_tokens

KINDS = ("design_system", "agent", "message", "document", "repo_workflow")
KIND_LABELS = {
    "design_system": "Design system",
    "agent": "Agentes e prompts",
    "message": "Mensagens",
    "document": "Documentos",
    "repo_workflow": "Repositorio e workflow",
}
FORMATS = ("json", "markdown", "text")
STATUSES = ("draft", "active", "archived")
MAX_BODY_CHARS = 200_000


class TemplateInvalid(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_body(kind: str, fmt: str, body: str) -> None:
    """Format validation. JSON bodies must parse to an object; a design-system template must
    additionally satisfy the strict ``noctus.brand-tokens/v1`` rules (the same regexes that guard
    what reaches the browser)."""
    if len(body) > MAX_BODY_CHARS:
        raise TemplateInvalid([f"body: maximo de {MAX_BODY_CHARS} caracteres"])
    if fmt != "json":
        return
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TemplateInvalid([f"JSON invalido (linha {exc.lineno}, coluna {exc.colno}): {exc.msg}"]) from exc
    if not isinstance(parsed, dict):
        raise TemplateInvalid(["JSON: a raiz deve ser um objeto"])
    if kind == "design_system":
        try:
            brand_tokens.validate_tokens(parsed, lenient=False)
        except brand_tokens.BrandTokensError as exc:
            raise TemplateInvalid(list(exc.errors)) from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformTemplateService:
    def __init__(self, repo: PlatformTemplateRepo) -> None:
        self.repo = repo

    # -- reads ----------------------------------------------------------------------
    def list(self, *, product: Optional[str] = None, kind: Optional[str] = None, q: Optional[str] = None,
             status: Optional[str] = None) -> list[dict]:
        """Latest version per (product, kind, key) -- the active one when there is one, else the
        newest draft/archived -- plus the count of versions."""
        rows = self.repo.list(product=product, kind=kind)
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            groups.setdefault((r["product"], r["kind"], r["key"]), []).append(r)
        out = []
        for versions in groups.values():
            versions.sort(key=lambda r: r["version"], reverse=True)
            active = next((v for v in versions if v["status"] == "active"), None)
            head = dict(active or versions[0])
            head["versions"] = len(versions)
            head["latest_version"] = versions[0]["version"]
            head["has_draft"] = any(v["status"] == "draft" for v in versions)
            out.append(head)
        if status:
            out = [r for r in out if r["status"] == status]
        if q:
            needle = q.strip().lower()
            out = [r for r in out if needle in " ".join(
                str(r.get(f) or "") for f in ("key", "title", "description", "product", "kind")).lower()]
        return sorted(out, key=lambda r: (r["kind"], r["product"] or "", r["key"]))

    def get(self, template_id: str) -> dict:
        row = self.repo.get(template_id)
        if row is None:
            raise NotFound(template_id)
        return row

    def history(self, template_id: str) -> list[dict]:
        row = self.get(template_id)
        return self.repo.history(row["product"], row["kind"], row["key"])

    # -- writes ---------------------------------------------------------------------
    def create(self, *, product: Optional[str], kind: str, key: str, title: str, description: str,
               fmt: str, body: str, user_id: Optional[str]) -> dict:
        validate_body(kind, fmt, body)
        version = self.repo.next_version(product, kind, key)
        return self.repo.insert({
            "product": product, "kind": kind, "key": key, "title": title, "description": description,
            "format": fmt, "body": body, "version": version, "status": "draft",
            "created_by": user_id, "updated_by": user_id,
        })

    def update(self, template_id: str, *, fields: dict[str, Any], user_id: Optional[str]) -> dict:
        """Draft -> edited in place. Any other status -> a NEW draft (version N+1) from it."""
        current = self.get(template_id)
        merged = {**{k: current[k] for k in ("title", "description", "format", "body")},
                  **{k: v for k, v in fields.items() if v is not None}}
        validate_body(current["kind"], merged["format"], merged["body"])
        if current["status"] == "draft":
            row = self.repo.update_draft(template_id, {**merged, "updated_by": user_id, "updated_at": _now()})
            if row is None:  # raced with an activation
                raise FrozenVersion(template_id)
            return row
        return self.repo.insert({
            "product": current["product"], "kind": current["kind"], "key": current["key"], **merged,
            "version": self.repo.next_version(current["product"], current["kind"], current["key"]),
            "status": "draft", "created_by": user_id, "updated_by": user_id,
        })

    def activate(self, template_id: str, *, user_id: Optional[str]) -> dict:
        current = self.get(template_id)
        validate_body(current["kind"], current["format"], current["body"])
        return self.repo.activate(template_id)

    def archive(self, template_id: str, *, user_id: Optional[str]) -> dict:
        current = self.get(template_id)
        if current["status"] == "archived":
            return current
        row = self.repo.archive(template_id, user_id)
        if row is None:
            raise NotFound(template_id)
        return row
