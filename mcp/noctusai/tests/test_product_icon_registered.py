"""Regression test for `check_product_icon_registered` (product-icon-registry).

Every product must ship a REAL icon. `ProductIcon`
(core/frontend/src/lib/product-icon.tsx) renders a value that is a key in its
`ICONS` registry as an SVG, an emoji (non-ASCII) verbatim, and any other ASCII
value as raw TEXT. So a lucide name NOT in the registry shows up literally on
the dashboard / admin panel (the "Sprout" bug, 2026-05-25). The detector folds
the core product-catalog migrations into the final live catalog and flags any
product whose icone is EMPTY or an unregistered ASCII name. Emoji + registered
names + retired (deleted) products are clean.

All tests use `tmp_path` — no dependency on the live `products/` tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_product_icon_registered  # noqa: E402


_REGISTRY = """\
import { Building2, Wallet, Box, type LucideIcon } from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  Building2,
  Wallet,
  Box, // scaffolder default
};

export function ProductIcon() { return null; }
"""


def _mk_repo(tmp_path: Path, *, registry: str | None = _REGISTRY) -> Path:
    """Create a minimal repo with a ProductIcon registry + empty migrations dir."""
    if registry is not None:
        reg = tmp_path / "products" / "core" / "frontend" / "src" / "lib" / "product-icon.tsx"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(registry)
    migs = tmp_path / "products" / "core" / "backend" / "migrations"
    migs.mkdir(parents=True, exist_ok=True)
    return tmp_path


def _add_migration(repo: Path, name: str, body: str) -> None:
    (repo / "products" / "core" / "backend" / "migrations" / name).write_text(body)


_INSERT = (
    "INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)\n"
    "VALUES (\n"
    "    '{nome}',\n"
    "    '{slug}',\n"
    "    'Some description; with a semicolon and (parens) inside.',\n"
    "    '{icone}',\n"
    "    'http://localhost:8080',\n"
    "    '#10b981',\n"
    "    true\n"
    ") ON CONFLICT (slug) DO NOTHING;\n"
)


class TestCheckProductIconRegistered:
    def test_registered_name_is_clean(self, tmp_path: Path) -> None:
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="ERP", slug="erp", icone="Building2"))
        assert check_product_icon_registered(repo) == []

    def test_emoji_is_clean(self, tmp_path: Path) -> None:
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="Legacy", slug="legacy", icone="🏠"))
        assert check_product_icon_registered(repo) == []

    def test_unregistered_ascii_name_is_flagged(self, tmp_path: Path) -> None:
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="Seed", slug="seed", icone="Sprout"))
        issues = check_product_icon_registered(repo)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["product"] == "core"
        assert "Sprout" in issues[0]["issue"]
        assert "seed" in issues[0]["issue"]

    def test_empty_icone_is_flagged(self, tmp_path: Path) -> None:
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="Empty", slug="empty", icone=""))
        issues = check_product_icon_registered(repo)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "EMPTY" in issues[0]["issue"]

    def test_retired_product_not_flagged(self, tmp_path: Path) -> None:
        """A product seeded with a bad icone but DELETEd by a later migration
        is no longer live → must not be flagged."""
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="Media", slug="media-scheduling", icone="CalendarDays"))
        _add_migration(repo, "020_retire.sql",
                       "DELETE FROM public.products WHERE slug IN (\n"
                       "    'media-scheduling',\n"
                       "    'imobi-scheduling'\n"
                       ");\n")
        assert check_product_icon_registered(repo) == []

    def test_delete_then_readd_uses_final_icone(self, tmp_path: Path) -> None:
        """`seed` deleted by an earlier migration, re-added by a later one → the
        re-added (final) icone is what gets validated."""
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "030_delete.sql",
                       "DELETE FROM public.products WHERE slug = 'seed';\n")
        # Re-add with a REGISTERED icon → clean.
        _add_migration(repo, "040_readd.sql",
                       _INSERT.format(nome="Seed", slug="seed", icone="Box"))
        assert check_product_icon_registered(repo) == []
        # Re-add with an UNREGISTERED icon → flagged.
        _add_migration(repo, "040_readd.sql",
                       _INSERT.format(nome="Seed", slug="seed", icone="Sprout"))
        issues = check_product_icon_registered(repo)
        assert len(issues) == 1
        assert "Sprout" in issues[0]["issue"]

    def test_update_overrides_insert(self, tmp_path: Path) -> None:
        """An UPDATE that reconciles a legacy emoji to a registered name wins."""
        repo = _mk_repo(tmp_path)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="ERP", slug="erp", icone="🏠"))
        _add_migration(repo, "020_reconcile.sql",
                       "UPDATE public.products SET icone = 'Building2' "
                       "WHERE slug = 'erp' AND icone = '🏠';\n")
        assert check_product_icon_registered(repo) == []

    def test_missing_registry_degrades_to_empty(self, tmp_path: Path) -> None:
        repo = _mk_repo(tmp_path, registry=None)
        _add_migration(repo, "010_seed.sql",
                       _INSERT.format(nome="Seed", slug="seed", icone="Sprout"))
        # No registry → cannot validate → degrade to [] (logged, not a crash).
        assert check_product_icon_registered(repo) == []
