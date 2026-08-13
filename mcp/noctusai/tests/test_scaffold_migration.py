"""Tests for `noctus.dev.scaffold_migration`.

The tool's path resolution defaults to ``settings.PRODUCTS_DIR``, but the
public function exposes a ``products_dir=`` injection seam (consumer-injection
Protocol-over-Callable rule applied at function-arg level: a Path injection
is the simplest test seam that doesn't require monkey-patching our own
module). Tests pass tmp_path-based fake products via the seam — fully
hermetic, no production-code patching.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Wire test sys.path the same way test_scaffold.py does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from noctusai_lib.domain.sql_templates import (  # noqa: E402
    rls_subquery_policy,
    set_search_path,
    updated_at_function,
    updated_at_trigger,
)
from noctusai_lib.sql import (  # noqa: E402
    prelude as sql_prelude,
    updated_at_trigger as sql_updated_at_trigger,
)

from tools.noctus.dev import scaffold_migration as sm  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_products_dir(tmp_path: Path) -> Path:
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    return products_dir


def _make_fake_product(
    products_dir: Path,
    slug: str,
    *,
    migration_files: list[str] | None = None,
) -> Path:
    """Create a minimal product dir under `products_dir`.

    `migration_files`: list of filenames to drop under backend/migrations/
    (each gets a stub `-- placeholder` body). None or `[]` = empty migrations
    dir. Caller can omit calling this helper to skip creating migrations/.
    """
    product_dir = products_dir / slug
    migrations = product_dir / "backend" / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)
    if migration_files:
        for name in migration_files:
            (migrations / name).write_text(f"-- placeholder for {name}\n")
    return product_dir


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Numbering / basic emission
# ---------------------------------------------------------------------------


class TestNumbering:
    def test_next_number_after_001(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration("demo", "add_users", products_dir=products)

        assert result.get("created") is True, result
        assert result["number"] == 2
        assert Path(result["path"]).name == "002_add_users.sql"
        assert Path(result["path"]).exists()

    def test_next_number_after_005(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(
            products,
            "demo",
            migration_files=["001_seed.sql", "005_other.sql"],
        )

        result = sm.scaffold_migration("demo", "next_thing", products_dir=products)

        assert result["created"] is True
        assert result["number"] == 6
        assert Path(result["path"]).name == "006_next_thing.sql"

    def test_three_digit_zero_padded(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration("demo", "x", products_dir=products)
        assert Path(result["path"]).name.startswith("002_")

    def test_ignores_non_numeric_files(self, tmp_path):
        """README.md / extra .sql without numeric prefix should not advance numbering."""
        products = _make_products_dir(tmp_path)
        product = _make_fake_product(products, "demo", migration_files=["001_seed.sql"])
        (product / "backend" / "migrations" / "README.md").write_text("docs\n")
        (product / "backend" / "migrations" / "scratch.sql").write_text("--\n")

        result = sm.scaffold_migration("demo", "thing", products_dir=products)
        assert result["number"] == 2


# ---------------------------------------------------------------------------
# Schema resolution
# ---------------------------------------------------------------------------


class TestSchemaResolution:
    def test_default_schema_dashes_to_underscores(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(
            products, "youtube-crawler", migration_files=["001_seed.sql"]
        )

        result = sm.scaffold_migration(
            "youtube-crawler", "oauth_credentials", products_dir=products
        )

        assert result["schema"] == "youtube_crawler"
        body = Path(result["path"]).read_text()
        assert "Schema: youtube_crawler" in body
        assert "SET search_path = youtube_crawler, public" in body

    def test_explicit_schema_used_as_is(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(
            products, "youtube-crawler", migration_files=["001_seed.sql"]
        )

        result = sm.scaffold_migration(
            "youtube-crawler", "oauth_credentials", schema="foo", products_dir=products
        )

        assert result["schema"] == "foo"
        body = Path(result["path"]).read_text()
        assert "Schema: foo" in body
        assert "SET search_path = foo, public" in body
        # Negative: did NOT silently use the slug-derived default.
        assert "youtube_crawler" not in body


# ---------------------------------------------------------------------------
# `with_table=` block
# ---------------------------------------------------------------------------


class TestWithTable:
    def test_with_table_emits_full_block(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "add_users", schema="demo", with_table="users", products_dir=products
        )

        body = Path(result["path"]).read_text()
        assert "CREATE TABLE IF NOT EXISTS demo.users" in body

        # Idempotent updated_at function call (verbatim helper output).
        expected_fn = updated_at_function("demo")
        assert _normalize_ws(expected_fn) in _normalize_ws(body)

        # Trigger.
        expected_trigger = updated_at_trigger("demo", "users")
        assert _normalize_ws(expected_trigger) in _normalize_ws(body)

        # RLS subquery policy stub.
        expected_policy = rls_subquery_policy(
            "demo",
            "users",
            "users_select_own",
            "SELECT",
            using="(SELECT auth.uid()) IS NOT NULL  -- TODO: tighten to ownership predicate",
        )
        assert _normalize_ws(expected_policy) in _normalize_ws(body)

        # Enable RLS line is present.
        assert "ALTER TABLE demo.users ENABLE ROW LEVEL SECURITY" in body

    def test_without_table_omits_block(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration("demo", "no_table", products_dir=products)
        body = Path(result["path"]).read_text()

        assert "CREATE TABLE" not in body
        assert "ENABLE ROW LEVEL SECURITY" not in body


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_product_dir_missing(self, tmp_path):
        products = _make_products_dir(tmp_path)

        result = sm.scaffold_migration("does-not-exist", "thing", products_dir=products)

        assert "error" in result
        assert "not found" in result["error"]
        assert "scaffold the product first" in result["error"].lower()

    def test_migrations_dir_missing(self, tmp_path):
        products = _make_products_dir(tmp_path)
        # Product exists but migrations/ does not.
        product_dir = products / "demo"
        (product_dir / "backend").mkdir(parents=True)

        result = sm.scaffold_migration("demo", "thing", products_dir=products)

        assert "error" in result
        assert "no backend/migrations/" in result["error"]

    def test_empty_migrations_dir(self, tmp_path):
        """Empty migrations/ → must error, NOT silently start at 001
        (that would step on noctus.dev.scaffold_product's territory)."""
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=[])

        result = sm.scaffold_migration("demo", "thing", products_dir=products)

        assert "error" in result
        assert "empty migrations/" in result["error"]

    def test_empty_product_slug(self, tmp_path):
        products = _make_products_dir(tmp_path)
        result = sm.scaffold_migration("", "thing", products_dir=products)
        assert "error" in result
        assert "product_slug" in result["error"]

    def test_empty_migration_name(self, tmp_path):
        products = _make_products_dir(tmp_path)
        result = sm.scaffold_migration("demo", "", products_dir=products)
        assert "error" in result
        assert "migration_name" in result["error"]

    def test_name_collision_advances_number(self, tmp_path):
        """Existing 002_users.sql + new request to scaffold `users` →
        next number is 003 (numbers prefix; collision-free by construction)."""
        products = _make_products_dir(tmp_path)
        _make_fake_product(
            products,
            "demo",
            migration_files=["001_seed.sql", "002_users.sql"],
        )

        result = sm.scaffold_migration("demo", "users", products_dir=products)

        assert result["created"] is True
        assert result["number"] == 3
        assert Path(result["path"]).name == "003_users.sql"
        # Both files exist (no overwrite of 002_users.sql).
        assert (products / "demo" / "backend" / "migrations" / "002_users.sql").exists()
        assert Path(result["path"]).exists()


# ---------------------------------------------------------------------------
# Keeper-detector-style: scaffold output must match helper output
# ---------------------------------------------------------------------------


class TestSqlTemplatesIntegration:
    """Catches drift between the scaffold tool and the canonical helpers.

    Same intent as `TestSqlTemplatesIntegration` in test_scaffold.py, but for
    scaffold_migration. If the helpers' output format ever changes, the
    scaffold's emitted SQL must change in lockstep — and these tests fail
    loudly until both are aligned.
    """

    def test_set_search_path_line_matches_helper(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "thing", schema="ai_chat", products_dir=products
        )
        body = Path(result["path"]).read_text()

        expected = set_search_path("ai_chat") + ";"
        assert expected in body, (
            f"scaffold_migration's SET search_path drifted from "
            f"set_search_path() helper.\nExpected: {expected!r}\n"
            f"Body head:\n{body[:400]}"
        )

    def test_updated_at_function_matches_helper(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "add_users", schema="demo", with_table="users", products_dir=products
        )
        body = Path(result["path"]).read_text()

        expected = updated_at_function("demo")
        assert _normalize_ws(expected) in _normalize_ws(body)

    def test_updated_at_trigger_matches_helper(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "add_users", schema="demo", with_table="users", products_dir=products
        )
        body = Path(result["path"]).read_text()

        expected = updated_at_trigger("demo", "users")
        assert _normalize_ws(expected) in _normalize_ws(body)


# ---------------------------------------------------------------------------
# Prelude shape — the new `noctusai_lib.sql.prelude(...)` comment block
# ---------------------------------------------------------------------------


class TestPreludeShape:
    """Pin the `noctusai_lib.sql.prelude(...)` shape at the top of every
    new migration. Matches the seed-migration-prelude project (2026-05-10):
    every new migration ships the schema-lock with a why-block.
    """

    def test_prelude_comment_block_present(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "thing", schema="ai_chat", products_dir=products
        )
        body = Path(result["path"]).read_text()

        # Why-block names both rationales — RLS + cross-product safety.
        assert "RLS isolation" in body
        assert "Cross-product safety" in body
        # Schema-lock line is verbatim.
        assert "SET search_path = ai_chat, public;" in body

    def test_prelude_matches_helper_output(self, tmp_path):
        # Emitted prelude block matches `sql_prelude(...)` verbatim.
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "thing", schema="ai_chat", products_dir=products
        )
        body = Path(result["path"]).read_text()

        # `prelude(...)` returns a comment block + schema-lock + trailing
        # newline. Strip the trailing newline because the body re-joins
        # parts with `\n\n`.
        expected = sql_prelude("ai_chat").rstrip("\n")
        assert expected in body, (
            f"scaffold_migration prelude drifted from sql_prelude() helper.\n"
            f"Expected:\n{expected!r}\n"
            f"Body head:\n{body[:600]}"
        )


# ---------------------------------------------------------------------------
# `with_updated_at=` block — multi-table updated_at trigger emission
# ---------------------------------------------------------------------------


class TestWithUpdatedAt:
    def test_single_table_emits_function_and_trigger(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo",
            "touch_posts",
            schema="blog",
            with_updated_at=["posts"],
            products_dir=products,
        )

        assert result["created"] is True
        body = Path(result["path"]).read_text()
        assert "CREATE OR REPLACE FUNCTION blog.set_updated_at()" in body
        assert "BEFORE UPDATE ON blog.posts" in body
        assert "CREATE OR REPLACE TRIGGER set_updated_at_posts" in body

    def test_multi_table_emits_function_once(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo",
            "auto_touch_all",
            schema="blog",
            with_updated_at=["posts", "comments", "tags"],
            products_dir=products,
        )

        body = Path(result["path"]).read_text()
        # Function declared exactly once despite 3 triggers.
        assert body.count("CREATE OR REPLACE FUNCTION blog.set_updated_at()") == 1
        # All three triggers present.
        assert "CREATE OR REPLACE TRIGGER set_updated_at_posts" in body
        assert "CREATE OR REPLACE TRIGGER set_updated_at_comments" in body
        assert "CREATE OR REPLACE TRIGGER set_updated_at_tags" in body
        # All three tables targeted.
        assert "BEFORE UPDATE ON blog.posts" in body
        assert "BEFORE UPDATE ON blog.comments" in body
        assert "BEFORE UPDATE ON blog.tags" in body

    def test_with_table_and_with_updated_at_compose(self, tmp_path):
        # `with_table=` (single full block with RLS) AND `with_updated_at=`
        # (multi-table touch) should both emit. Same migration adding a
        # new table + auto-touch on existing tables.
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo",
            "extend_blog",
            schema="blog",
            with_table="reactions",
            with_updated_at=["posts", "comments"],
            products_dir=products,
        )

        body = Path(result["path"]).read_text()
        # `with_table=` block.
        assert "CREATE TABLE IF NOT EXISTS blog.reactions" in body
        # `with_updated_at=` block.
        assert "BEFORE UPDATE ON blog.posts" in body
        assert "BEFORE UPDATE ON blog.comments" in body

    def test_omitted_emits_no_block(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo", "nothing", schema="demo", products_dir=products
        )

        body = Path(result["path"]).read_text()
        # Without with_table or with_updated_at, no trigger emitted.
        assert "CREATE OR REPLACE TRIGGER" not in body
        assert "BEFORE UPDATE ON" not in body

    def test_invalid_type_returns_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo",
            "bad",
            with_updated_at="posts",  # type: ignore[arg-type]
            products_dir=products,
        )
        assert "error" in result
        assert "list" in result["error"]

    def test_empty_string_in_list_returns_error(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo",
            "bad",
            with_updated_at=["posts", "  "],
            products_dir=products,
        )
        assert "error" in result
        assert "non-empty" in result["error"]

    def test_emitted_block_matches_helper(self, tmp_path):
        # Drift-detection: scaffold output for a single-table
        # `with_updated_at=[t]` must contain exactly what
        # `sql_updated_at_trigger(t, schema=s)` returns.
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])

        result = sm.scaffold_migration(
            "demo",
            "touch",
            schema="blog",
            with_updated_at=["posts"],
            products_dir=products,
        )
        body = Path(result["path"]).read_text()

        expected = sql_updated_at_trigger("posts", schema="blog")
        assert _normalize_ws(expected) in _normalize_ws(body)


# ---------------------------------------------------------------------------
# Return-shape contract
# ---------------------------------------------------------------------------


class TestReturnShape:
    def test_success_keys(self, tmp_path):
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql"])
        result = sm.scaffold_migration("demo", "thing", products_dir=products)
        # `warnings` is new (2026-08-13, next_migration_number wiring): the
        # number is now computed from disk + origin/dev + local branches, and
        # a degraded source (no git repo here — a bare tmp_path) surfaces as
        # a warning rather than silently. Always present, normally non-empty
        # in a hermetic tmp_path fixture (no git repo behind it).
        assert set(result.keys()) == {"created", "path", "number", "schema", "warnings"}
        assert result["created"] is True
        assert isinstance(result["path"], str)
        assert isinstance(result["number"], int)
        assert isinstance(result["schema"], str)
        assert isinstance(result["warnings"], list)

    def test_error_shape(self, tmp_path):
        products = _make_products_dir(tmp_path)
        result = sm.scaffold_migration("nope", "thing", products_dir=products)
        assert "error" in result
        assert "created" not in result


# ---------------------------------------------------------------------------
# worktree_path — caller-aware path resolution (the
# `projects/mcp-worktree-path-resolution/` fix).
# ---------------------------------------------------------------------------


class TestWorktreeAwarePathResolution:
    """`scaffold_migration` honors `worktree_path` so engineers in
    git worktrees don't get their migrations written to noc main.
    """

    def _make_fake_worktree(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text("gitdir: /tmp/fake/.git\n", encoding="utf-8")
        (root / ".noctusai-workspace").write_text(
            "workspace_kind=primary\n"
            "workspace_name=fake\n"
            f"noctusai_home={root}\n",
            encoding="utf-8",
        )
        return root

    def test_migration_lands_in_worktree(self, tmp_path):
        wt = self._make_fake_worktree(tmp_path / "wt")
        # Plant a product with an existing migration inside the worktree.
        _make_fake_product(
            wt / "products",
            "wt-product",
            migration_files=["001_seed.sql"],
        )
        result = sm.scaffold_migration(
            "wt-product", "add_thing", worktree_path=wt,
        )
        assert result.get("created") is True, result
        new_file = wt / "products" / "wt-product" / "backend" / "migrations" / "002_add_thing.sql"
        assert new_file.exists(), (
            f"scaffold_migration with worktree_path={wt} must place the new "
            f"migration under {new_file}, got result={result}"
        )

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-wt"
        bad.mkdir()
        # The helper raises before any side effect.
        import pytest
        with pytest.raises(ValueError):
            sm.scaffold_migration(
                "anything", "thing", worktree_path=bad,
            )

    def test_explicit_products_dir_overrides_worktree_path(self, tmp_path):
        """Test seam wins — explicit products_dir wins over worktree_path."""
        wt = self._make_fake_worktree(tmp_path / "wt")
        sink = tmp_path / "sink"
        _make_fake_product(
            sink, "sink-product", migration_files=["001_seed.sql"],
        )
        result = sm.scaffold_migration(
            "sink-product",
            "thing",
            worktree_path=wt,
            products_dir=sink,
        )
        assert result.get("created") is True, result
        assert (sink / "sink-product" / "backend" / "migrations" / "002_thing.sql").exists()


# ---------------------------------------------------------------------------
# `noctus.dev.next_migration_number` — correct-by-construction numbering.
#
# Real `git` repos throughout this section (not the FakeGit-style injection
# used elsewhere in the platform's test suite) — the whole point of the tool
# is real git plumbing (origin/dev ls-tree + local-branch diffing), so a
# fake would not exercise the code that actually matters. Every fixture
# degrades to `pytest.skip` if git is unusable in the sandbox, mirroring
# `TestCheckMigrationNumberCollision._git_repo()` in test_compliance.py.
# ---------------------------------------------------------------------------


def _git_ok(*args: str, cwd: Path) -> bool:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def _git_out(*args: str, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def _write_migration(repo: Path, product: str, name: str) -> None:
    mig = repo / "products" / product / "backend" / "migrations"
    mig.mkdir(parents=True, exist_ok=True)
    (mig / name).write_text("-- migration\nSELECT 1;\n")


def _init_repo(repo: Path) -> bool:
    return (
        _git_ok("init", "-q", "-b", "dev", cwd=repo)
        and _git_ok("config", "user.email", "t@test.local", cwd=repo)
        and _git_ok("config", "user.name", "t", cwd=repo)
    )


class TestNextMigrationNumberRealIncident:
    """Reconstructs the VERIFIED 2026-08-13 incident.

    `049_imoveis_place_name_collision_fix.sql` was authored in a PARALLEL
    worktree and merged (applied to production) FIRST. THIS worktree —
    mid-authoring `049_cliente_revisao_rejeitadas.sql` — had not rebased, so
    its own `migrations/` directory never saw the sibling's file: the naive
    `ls migrations/` signal alone gives `049`, the exact collision that
    shipped and cost ~1600 lines of rework. `next_migration_number` must
    return `050` by reading `origin/dev` directly — independent of whether
    THIS worktree's own checkout has caught up.
    """

    def _setup(self, tmp_path: Path) -> Path | None:
        repo = tmp_path
        if not _init_repo(repo):
            return None
        # Base: erp-imobiliario ships up through 048.
        _write_migration(repo, "erp-imobiliario", "048_prior.sql")
        if not (_git_ok("add", "-A", cwd=repo) and _git_ok("commit", "-qm", "base", cwd=repo)):
            return None
        base_sha = _git_out("rev-parse", "HEAD", cwd=repo)

        # The PARALLEL worktree's migration lands and merges to dev first —
        # the real incident's `049_imoveis_place_name_collision_fix.sql`.
        _write_migration(repo, "erp-imobiliario", "049_imoveis_place_name_collision_fix.sql")
        if not (_git_ok("add", "-A", cwd=repo)
                and _git_ok("commit", "-qm", "049 place-name fix", cwd=repo)):
            return None
        # `origin/dev` reflects the merge — a local-ref stand-in (no real
        # remote), the same idiom test_compliance.py's `_git_repo()` uses.
        if not _git_ok("update-ref", "refs/remotes/origin/dev", "HEAD", cwd=repo):
            return None

        # THIS worktree: branched off BEFORE the sibling's fix landed, so its
        # own checkout has never seen it (exactly the incident's shape).
        if not _git_ok("checkout", "-q", "-b", "feat/lead-card-hub-slice-b", base_sha, cwd=repo):
            return None
        return repo

    def test_returns_050_before_any_work_starts(self, tmp_path):
        repo = self._setup(tmp_path)
        if repo is None:
            import pytest
            pytest.skip("git unavailable in this environment")

        result = sm.next_migration_number("erp-imobiliario", products_dir=repo / "products")

        assert result.get("next_number") == 50, result
        # The claim naming the REAL incident file must be visible, sourced
        # from origin/dev — NOT from this worktree's own (stale) disk, which
        # never had it.
        origin_claims = [c for c in result["claims"] if c["source"] == "origin/dev"]
        assert any(
            c["file"] == "049_imoveis_place_name_collision_fix.sql" for c in origin_claims
        ), result

    def test_naive_local_disk_scan_alone_would_have_returned_the_collision(self, tmp_path):
        """Negative control proving the fix is real: THIS worktree's own
        directory — the pre-fix signal `scaffold_migration` used to trust
        alone — contains only `048_prior.sql`. A naive max(local NN)+1 is
        `049`: the exact number that collided in production."""
        repo = self._setup(tmp_path)
        if repo is None:
            import pytest
            pytest.skip("git unavailable in this environment")

        mig = repo / "products" / "erp-imobiliario" / "backend" / "migrations"
        local_files = sorted(p.name for p in mig.glob("*.sql"))
        assert local_files == ["048_prior.sql"], (
            f"fixture sanity check failed — expected the naive local-disk view "
            f"to be blind to the sibling's 049, got {local_files}"
        )

    def test_scaffold_migration_emits_050_not_049(self, tmp_path):
        """End-to-end: the actual authoring tool, not just the number
        computation, produces the collision-free file."""
        repo = self._setup(tmp_path)
        if repo is None:
            import pytest
            pytest.skip("git unavailable in this environment")

        result = sm.scaffold_migration(
            "erp-imobiliario", "cliente_revisao_rejeitadas", products_dir=repo / "products",
        )
        assert result.get("created") is True, result
        assert Path(result["path"]).name == "050_cliente_revisao_rejeitadas.sql", result


class TestNextMigrationNumberUnpushedSiblingBranch:
    """The 2026-08-03 shape (`check_migration_number_collision`'s own origin
    incident): a sibling branch has COMMITTED — but not PUSHED — a migration
    that both this worktree's disk AND `origin/dev` miss. Local git refs are
    shared across every worktree of one clone, so the branch is visible via
    `git branch --format` even though nothing was pushed anywhere.
    """

    def _setup(self, tmp_path: Path) -> Path | None:
        repo = tmp_path
        if not _init_repo(repo):
            return None
        _write_migration(repo, "core", "040_base.sql")
        if not (_git_ok("add", "-A", cwd=repo) and _git_ok("commit", "-qm", "base", cwd=repo)):
            return None
        if not _git_ok("update-ref", "refs/remotes/origin/dev", "HEAD", cwd=repo):
            return None
        # Sibling worktree (shares this .git) commits 041 on a branch it has
        # NOT pushed.
        if not _git_ok("checkout", "-q", "-b", "feat/sibling", "dev", cwd=repo):
            return None
        _write_migration(repo, "core", "041_sibling_work.sql")
        if not (_git_ok("add", "-A", cwd=repo)
                and _git_ok("commit", "-qm", "sibling 041", cwd=repo)):
            return None
        # Back to dev — THIS worktree's own checkout only ever had 040.
        if not _git_ok("checkout", "-q", "dev", cwd=repo):
            return None
        return repo

    def test_next_number_sees_unpushed_sibling_and_skips_past_it(self, tmp_path):
        repo = self._setup(tmp_path)
        if repo is None:
            import pytest
            pytest.skip("git unavailable in this environment")

        result = sm.next_migration_number("core", products_dir=repo / "products")

        assert result.get("next_number") == 42, result
        branch_claims = [c for c in result["claims"] if c["source"].startswith("branch:")]
        assert any(c["file"] == "041_sibling_work.sql" for c in branch_claims), result
        assert any("feat/sibling" in c["source"] for c in branch_claims), result


class TestNextMigrationNumberErrorsAndDegradation:
    def test_missing_product_matches_scaffold_migration_error_text(self, tmp_path):
        """Same resolver, same wording — a caller must not see two different
        error strings for the same failure from two different tools."""
        products = _make_products_dir(tmp_path)
        result = sm.next_migration_number("does-not-exist", products_dir=products)
        assert "error" in result
        assert "not found" in result["error"]
        assert "scaffold the product first" in result["error"].lower()

    def test_empty_everywhere_is_an_error_not_a_silent_1(self, tmp_path):
        """Mirrors scaffold_migration's own guard: an empty migrations/ dir
        with no signal from origin/dev or any branch must NOT silently
        propose `1` — that would step on noctus.dev.scaffold_product's
        territory (which ships 001_seed.sql)."""
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=[])
        result = sm.next_migration_number("demo", products_dir=products)
        assert "error" in result
        assert "empty migrations/" in result["error"]

    def test_no_git_repo_degrades_to_disk_only_with_warnings(self, tmp_path):
        """A bare tmp_path (no git at all, e.g. every OTHER test in this
        file's `products_dir=` seam) must still answer correctly from disk
        alone — degraded, not broken. `origin/dev` unavailable surfaces as a
        warning, never a silent wrong answer."""
        products = _make_products_dir(tmp_path)
        _make_fake_product(products, "demo", migration_files=["001_seed.sql", "002_x.sql"])
        result = sm.next_migration_number("demo", products_dir=products)
        assert result.get("next_number") == 3, result
        assert result["warnings"], "expected a warning when origin/dev cannot be read at all"

    def test_git_repo_with_no_origin_dev_ref_warns_but_still_answers(self, tmp_path):
        repo = tmp_path
        if not _init_repo(repo):
            import pytest
            pytest.skip("git unavailable in this environment")
        _write_migration(repo, "demo", "001_seed.sql")
        if not (_git_ok("add", "-A", cwd=repo) and _git_ok("commit", "-qm", "base", cwd=repo)):
            import pytest
            pytest.skip("git commit unavailable in this environment")
        # No `refs/remotes/origin/dev` created — origin/dev genuinely cannot
        # resolve here.
        result = sm.next_migration_number("demo", products_dir=repo / "products")
        assert result.get("next_number") == 2, result
        assert any("did not resolve" in w for w in result["warnings"]), result

    def test_skip_fetch_true_still_reads_local_origin_dev_ref(self, tmp_path):
        """`skip_fetch=True` must skip the network round-trip, NOT the
        signal itself — a worktree that already has a fresh-enough
        `origin/dev` ref locally still benefits from source 2."""
        repo = tmp_path
        if not _init_repo(repo):
            import pytest
            pytest.skip("git unavailable in this environment")
        _write_migration(repo, "demo", "001_seed.sql")
        if not (_git_ok("add", "-A", cwd=repo) and _git_ok("commit", "-qm", "base", cwd=repo)):
            import pytest
            pytest.skip("git commit unavailable in this environment")
        if not _git_ok("update-ref", "refs/remotes/origin/dev", "HEAD", cwd=repo):
            import pytest
            pytest.skip("git update-ref unavailable in this environment")

        result = sm.next_migration_number(
            "demo", products_dir=repo / "products", skip_fetch=True,
        )
        assert result.get("next_number") == 2, result
        origin_claims = [c for c in result["claims"] if c["source"] == "origin/dev"]
        assert any(c["file"] == "001_seed.sql" for c in origin_claims), result


class TestScaffoldMigrationWarningsPassthrough:
    def test_warning_surfaces_when_origin_dev_unreadable(self, tmp_path):
        repo = tmp_path
        if not _init_repo(repo):
            import pytest
            pytest.skip("git unavailable in this environment")
        _write_migration(repo, "demo", "001_seed.sql")
        if not (_git_ok("add", "-A", cwd=repo) and _git_ok("commit", "-qm", "base", cwd=repo)):
            import pytest
            pytest.skip("git commit unavailable in this environment")

        result = sm.scaffold_migration("demo", "thing", products_dir=repo / "products")
        assert result.get("created") is True, result
        assert result["warnings"], "expected scaffold_migration to surface the degraded source"
