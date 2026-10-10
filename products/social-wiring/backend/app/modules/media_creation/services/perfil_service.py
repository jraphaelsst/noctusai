"""Meu Perfil — "Informações de criação" per marca (geracao-contract.md §2.1, §4.1).

ONE service, two callers: the Meu Perfil page (``/perfil``) and the Cérebro bio card
(``/cerebro/perfil``) both read and write the same ``cs_marca_perfil`` row through
:class:`PerfilService`, so ``bio`` has a single source of truth.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.geracao_taxonomias import (
    FORMATOS_VIDEO,
    GATILHOS,
    NICHO_IDS,
    NICHOS,
    PROFISSAO_IDS,
    PROFISSOES,
    TONS,
)
from app.modules.media_creation.prompts.methodology import METODO_TRIGGERS

logger = logging.getLogger(__name__)

PERFIL = "cs_marca_perfil"
MAX_ITENS = 3
#: ``tom`` ids are CoreStudio's 10..15 (contract §4.4); ``TONS`` is ordered by them.
TOM_ID_BASE = 10


class PerfilError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _formulas() -> dict[str, str]:
    """The 7 trigger formulas, parsed from the methodology text (single source of truth)."""
    quoted = re.findall(r'^\d\.\s+\*\*[^*]+\*\*\s+—\s+"(.+?)"', METODO_TRIGGERS, flags=re.MULTILINE)
    if len(quoted) != len(GATILHOS):
        raise RuntimeError(
            f"METODO_TRIGGERS has {len(quoted)} parseable formulas, expected {len(GATILHOS)}"
        )
    return {slug: quoted[i] for i, (slug, _) in enumerate(GATILHOS)}


def taxonomias() -> dict[str, Any]:
    """``Taxonomias`` (contract §4.8). Pure constants: no DB, no org."""
    formulas = _formulas()
    return {
        "nichos": [{"id": i, "nome": n} for i, n in NICHOS],
        "profissoes": sorted(({"id": i, "nome": n} for i, n in PROFISSOES), key=lambda t: t["nome"].casefold()),
        "formatos": [{"id": i, "nome": n, "definicao": d} for i, n, d in FORMATOS_VIDEO],
        "gatilhos": [{"slug": s, "nome": n, "formula": formulas[s]} for s, n in GATILHOS],
        # `slug` is extra to the TS `Taxon` on purpose: persisted/validated tom values are slugs.
        "tons": [{"id": TOM_ID_BASE + i, "nome": n, "slug": s} for i, (s, n) in enumerate(TONS)],
    }


def _check_ids(label: str, plural: str, ids: list[int], valid: frozenset[int]) -> list[int]:
    if len(ids) > MAX_ITENS:
        raise PerfilError(422, f"Selecione até {MAX_ITENS} {plural}")
    if len(set(ids)) != len(ids):
        raise PerfilError(422, f"Seleção duplicada em {plural}")
    unknown = [i for i in ids if i not in valid]
    if unknown:
        raise PerfilError(422, f"Id(s) de {label} desconhecido(s): {', '.join(map(str, unknown))}")
    return ids


class PerfilService:
    def __init__(self, db, org_id: str, user_id: str):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id")
            .eq("id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise PerfilError(404, "Marca não encontrada")

    def _empty(self, marca_id: str) -> dict[str, Any]:
        return {
            "marca_id": marca_id, "bio": "", "nichos": [], "profissoes": [],
            "apresentacao_magnetica": "", "ctas": "", "updated_at": None,
        }

    def get(self, marca_id: str) -> dict[str, Any]:
        self.assert_marca(marca_id)
        rows = (
            self.db.table(PERFIL)
            .select("marca_id,bio,nichos,profissoes,apresentacao_magnetica,ctas,updated_at")
            .eq("marca_id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            return self._empty(marca_id)
        r = rows[0]
        return {
            "marca_id": marca_id,
            "bio": r.get("bio") or "",
            "nichos": list(r.get("nichos") or []),
            "profissoes": list(r.get("profissoes") or []),
            "apresentacao_magnetica": r.get("apresentacao_magnetica") or "",
            "ctas": r.get("ctas") or "",
            "updated_at": r.get("updated_at"),
        }

    def save(
        self, marca_id: str, *, bio: Optional[str] = None, nichos: Optional[list[int]] = None,
        profissoes: Optional[list[int]] = None, apresentacao_magnetica: Optional[str] = None,
        ctas: Optional[str] = None,
    ) -> dict[str, Any]:
        """PATCH semantics: ``None`` = leave untouched. Returns the full profile."""
        self.assert_marca(marca_id)
        patch: dict[str, Any] = {}
        if bio is not None:
            patch["bio"] = bio
        if nichos is not None:
            patch["nichos"] = _check_ids("nicho", "nichos", nichos, NICHO_IDS)
        if profissoes is not None:
            patch["profissoes"] = _check_ids("profissão", "profissões", profissoes, PROFISSAO_IDS)
        if apresentacao_magnetica is not None:
            patch["apresentacao_magnetica"] = apresentacao_magnetica
        if ctas is not None:
            patch["ctas"] = ctas
        if not patch:
            return self.get(marca_id)

        patch.update({"updated_by": self.user_id, "updated_at": _iso()})
        existing = (
            self.db.table(PERFIL).select("marca_id")
            .eq("marca_id", marca_id).eq("org_id", self.org_id).execute().data
        )

        def update() -> None:
            self.db.table(PERFIL).update(patch).eq("marca_id", marca_id).eq("org_id", self.org_id).execute()

        if existing:
            update()
        else:
            try:
                self.db.table(PERFIL).insert({"marca_id": marca_id, "org_id": self.org_id, **patch}).execute()
            except Exception as exc:  # noqa: BLE001 - concurrent first save: the row exists now, update it
                if not is_unique_violation(exc):
                    raise
                update()
        return self.get(marca_id)
