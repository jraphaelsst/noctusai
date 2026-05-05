"""Product scaffolding — create new products from the seed framework.

Migrations emitted by the scaffolded product MUST keep the canonical SQL
DDL conventions used elsewhere in the platform. Helpers live at
`noctusai_lib.domain.sql_templates` (`set_search_path`, `updated_at_function`,
`updated_at_trigger`, `rls_subquery_policy`). The bundled `001_seed.sql`
template uses placeholders that resolve to schema-correct SQL on scaffold;
the regression tests at `tests/test_scaffold.py` (TestSqlTemplatesIntegration)
assert the scaffolded migration's `SET search_path` line + RLS policy line
match the helpers' output, so future drift is caught at CI rather than
discovered via a broken migration.
"""
import logging
import re
import shutil
from pathlib import Path

from workspace import get_noctusai_home, get_workspace_root

logger = logging.getLogger(__name__)

# Workspace-aware: products/ created under the workspace's own root (so
# scaffold_product from a template lands in template's products/, not
# noc's). The seed template lives only in noc — fetched via get_noctusai_home().
# See mcp/noctusai/workspace.py + KB § PATTERNS/seed-workspace.md.
REPO_ROOT = get_workspace_root()
PRODUCTS_DIR = REPO_ROOT / "products"
TEMPLATE_DIR = get_noctusai_home() / "templates" / "product-seed"


# Reserved port ranges — derived from `start.sh` per-product allocations.
# Each entry is (port, product_owner). When extending, also update start.sh
# AND `KB § CONTEXT/02-LANDSCAPE.md` Products table. The `reserve_port_range`
# function uses this list to skip occupied blocks; `list_available_ports`
# uses it to compute the next free port.
RESERVED_RANGES: list[tuple[int, str]] = [
    # Backend ports (8000-range)
    (8000, "core"),
    (8001, "erp-imobiliario"),
    (8002, "personal-finance"),
    (8003, "therapy-platform"),
    (8004, "seed"),
    (8005, "daily-life"),
    (8006, "mailing"),
    (8096, "media-scheduling"),
    (8140, "scheduling"),  # legacy/in-flight allocation
    # Frontend ports (5173 + 8080-range)
    (5173, "core"),                # Core frontend (Vite default)
    (8080, "erp-imobiliario"),     # ERP frontend
    (8090, "personal-finance"),    # PF frontend
    (8095, "therapy-platform"),    # Therapy frontend
    (8100, "seed"),                # Seed frontend
    (8110, "daily-life"),          # Daily Life frontend
    (8120, "mailing"),             # Mailing frontend
    (8130, "media-scheduling"),    # Media Scheduling frontend
]


# Known binary file extensions — skipped from text substitution. Anything
# else is treated as text; UnicodeDecodeError caught at read time keeps the
# whitelist short and forward-compatible (previously a positive whitelist of
# code suffixes excluded `.env.example`, `.yaml`, `.toml` etc. — silently
# leaving placeholders un-substituted).
_BINARY_SUFFIXES: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svgz",
    ".pdf", ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".webm", ".mov", ".wav", ".ogg",
    ".so", ".dylib", ".dll", ".exe", ".class", ".pyc",
})


def scaffold_product(
    name: str,
    slug: str,
    schema: str,
    backend_port: int,
    frontend_port: int,
    icon: str = "Box",
    *,
    products_dir: Path | None = None,
    template_dir: Path | None = None,
) -> dict:
    """Create a new product from the seed template.

    Replaces {{PLACEHOLDERS}} with actual values.
    Returns {created: bool, path: str, files: int}.

    Args:
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to module-level :data:`PRODUCTS_DIR`. Tests pass
            tmp_path-based dirs; production callers leave it as None.
        template_dir: Override for the seed template root (test seam).
            Defaults to :data:`TEMPLATE_DIR` (noc's
            ``templates/product-seed/``). Tests targeting an in-worktree
            template variant pass an explicit path.
    """
    base_products_dir = products_dir if products_dir is not None else PRODUCTS_DIR
    base_template_dir = template_dir if template_dir is not None else TEMPLATE_DIR
    target = base_products_dir / slug
    if target.exists():
        return {"error": f"Product '{slug}' already exists at {target}"}

    if not base_template_dir.exists():
        return {"error": f"Template not found at {base_template_dir}"}

    # Copy template
    shutil.copytree(base_template_dir, target, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".backup", "*.egg-info"))

    # Replace placeholders. {{PRODUCT_SLUG}} added 2026-05-04 (sh-yt-scaffold-polish
    # Phase 3.4) so README + MASTER-PROMPT path references resolve to the new
    # product slug instead of leaking the literal `seed/` from the source tree.
    replacements = {
        "{{PRODUCT_NAME}}": name,
        "{{PRODUCT_SLUG}}": slug,
        "{{SCHEMA_NAME}}": schema,
        "{{BACKEND_PORT}}": str(backend_port),
        "{{FRONTEND_PORT}}": str(frontend_port),
        "{{PRODUCT_ICON}}": icon,
    }

    file_count = 0
    skipped: list[str] = []
    for f in target.rglob("*"):
        if not f.is_file():
            continue
        # Skip known binary extensions; everything else is treated as text.
        # If decode fails the file is reported (no silent skip) so unexpected
        # binaries become visible.
        if f.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("scaffold: %s is not utf-8 text, skipping substitution", f)
            skipped.append(str(f.relative_to(target)))
            continue
        except OSError as exc:
            logger.warning("scaffold: cannot read %s (%s), skipping", f, exc)
            skipped.append(str(f.relative_to(target)))
            continue
        new_content = content
        for placeholder, value in replacements.items():
            new_content = new_content.replace(placeholder, value)
        if new_content != content:
            try:
                f.write_text(new_content, encoding="utf-8")
            except OSError as exc:
                logger.warning("scaffold: cannot write %s (%s)", f, exc)
                skipped.append(str(f.relative_to(target)))
                continue
        file_count += 1

    return {
        "created": True,
        "path": str(target),
        "files_processed": file_count,
        "skipped_files": skipped,
        "next_steps": [
            f"Add to start.sh (backend {backend_port}, frontend {frontend_port})",
            f"Add to CLAUDE.md product table",
            f"Run migration: mcp/noctusai tools → noctusai_apply_migration",
            f"Insert into public.products table",
            f"Add to PRODUCT_MAP in vite.config.factory.ts",
        ],
    }


def _scan_start_sh_ports() -> tuple[set[int], set[int]]:
    """Parse start.sh for `--port <N>` occurrences. Returns (backend, frontend).

    Heuristic: ports < 8100 (and != 5173) → backend; everything else → frontend.
    Kept tolerant — start.sh missing returns empty sets, never raises.
    """
    used_backend: set[int] = set()
    used_frontend: set[int] = set()
    start_sh = REPO_ROOT / "start.sh"
    if not start_sh.exists():
        return used_backend, used_frontend
    content = start_sh.read_text()
    for match in re.finditer(r"--port (\d+)", content):
        port = int(match.group(1))
        if port == 5173 or port >= 8080 and port < 8100 or port >= 8100:
            # 5173 is the Vite default for Core frontend; 8080+ are frontends
            if port < 8080:
                used_backend.add(port)
            else:
                used_frontend.add(port)
        else:
            used_backend.add(port)
    return used_backend, used_frontend


def list_available_ports() -> dict:
    """Find the next available backend and frontend ports.

    The set of "used" ports unions the static :data:`RESERVED_RANGES` table
    with whatever `start.sh` actually wires (defensive — methodology says the
    table IS the source of truth, but products land in start.sh first when
    docs lag).
    """
    used_backend: set[int] = {p for p, _ in RESERVED_RANGES if p < 8080 and p != 5173}
    used_frontend: set[int] = {p for p, _ in RESERVED_RANGES if p == 5173 or p >= 8080}

    sh_backend, sh_frontend = _scan_start_sh_ports()
    used_backend |= sh_backend
    used_frontend |= sh_frontend

    next_backend = max(used_backend) + 1 if used_backend else 8000
    next_frontend = max(used_frontend) + 10 if used_frontend else 8080

    return {
        "next_backend_port": next_backend,
        "next_frontend_port": next_frontend,
        "used_backend": sorted(used_backend),
        "used_frontend": sorted(used_frontend),
    }


def _find_contiguous_block(used: set[int], start: int, count: int, *, step: int = 1) -> int:
    """Return the first port `p >= start` such that `p, p+step, ..., p+(count-1)*step`
    are all absent from `used`. Pure / deterministic — used by the
    range-reservation helper.
    """
    if count <= 0:
        raise ValueError("count must be >= 1")
    candidate = start
    while True:
        block = [candidate + i * step for i in range(count)]
        if not any(b in used for b in block):
            return candidate
        # Skip past the first collision to avoid quadratic walks.
        candidate += step


def reserve_port_range(
    *,
    product_slug: str,
    count_backend: int = 1,
    count_frontend: int = 1,
) -> dict:
    """Reserve a contiguous backend block + a contiguous frontend block.

    Returns the FIRST available block of `count_backend` consecutive backend
    ports (default starts at the next free port after the highest reserved)
    and the same shape for frontend. Default `count=1` keeps back-compat with
    single-port allocations: `reserve_port_range(product_slug="x")` yields one
    backend + one frontend port equivalent to `list_available_ports()`'s
    `next_*` keys.

    Does NOT mutate :data:`RESERVED_RANGES` — caller is responsible for
    landing the allocation in start.sh + KB landscape table + this constant.
    The function's contract is "tell me the next free block"; persistence
    stays a human/architect step.

    Returns:
        {
            "product_slug": str,
            "backend_ports": [int, ...],   # length == count_backend
            "frontend_ports": [int, ...],  # length == count_frontend
            "rationale": str,              # human-readable picked-because text
        }
    """
    if count_backend < 1 or count_frontend < 1:
        return {
            "error": (
                f"count_backend ({count_backend}) and count_frontend "
                f"({count_frontend}) must each be >= 1"
            )
        }

    used_backend: set[int] = {p for p, _ in RESERVED_RANGES if p < 8080 and p != 5173}
    used_frontend: set[int] = {p for p, _ in RESERVED_RANGES if p == 5173 or p >= 8080}
    sh_backend, sh_frontend = _scan_start_sh_ports()
    used_backend |= sh_backend
    used_frontend |= sh_frontend

    # Backend search starts at the next slot above the highest used backend.
    backend_start = (max(used_backend) + 1) if used_backend else 8000
    backend_first = _find_contiguous_block(used_backend, backend_start, count_backend)
    backend_ports = [backend_first + i for i in range(count_backend)]

    # Frontend search starts at the next 10-aligned slot above the highest
    # used frontend (matches the "+10" stride convention `list_available_ports`
    # uses, so blocks stay visually grouped per-product).
    frontend_high = max(p for p in used_frontend if p >= 8080) if any(p >= 8080 for p in used_frontend) else 8070
    frontend_start = ((frontend_high // 10) + 1) * 10
    frontend_first = _find_contiguous_block(used_frontend, frontend_start, count_frontend)
    frontend_ports = [frontend_first + i for i in range(count_frontend)]

    return {
        "product_slug": product_slug,
        "backend_ports": backend_ports,
        "frontend_ports": frontend_ports,
        "rationale": (
            f"Backend block starts at {backend_first} (first free contiguous "
            f"{count_backend}-port slot after {sorted(used_backend)[-1] if used_backend else 'n/a'}). "
            f"Frontend block starts at {frontend_first} (next 10-aligned after "
            f"{frontend_high})."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_product",
        description="Create a new product from the seed template",
    )
    def _scaffold(
        name: str,
        slug: str,
        schema: str,
        backend_port: int,
        frontend_port: int,
        icon: str = "Box",
    ) -> dict:
        return scaffold_product(name, slug, schema, backend_port, frontend_port, icon)

    @server.tool(
        name="noctus.dev.available_ports",
        description="Find next available backend and frontend ports",
    )
    def _available_ports() -> dict:
        return list_available_ports()

    @server.tool(
        name="noctus.dev.reserve_port_range",
        description=(
            "Reserve a contiguous backend block + frontend block for a new "
            "product. Returns the first free contiguous N-port slot in each "
            "range. Default count=1 mirrors `available_ports`."
        ),
    )
    def _reserve_port_range(
        product_slug: str,
        count_backend: int = 1,
        count_frontend: int = 1,
    ) -> dict:
        return reserve_port_range(
            product_slug=product_slug,
            count_backend=count_backend,
            count_frontend=count_frontend,
        )
