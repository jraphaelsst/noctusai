"""Keeper: a seed ``card_hub`` table is service-only -- no ``authenticated``/``anon`` privilege survives the chain.

The card hub (notes, tags, members, reminders, checklists, documents + access log, operator checklist lines) is
reached ONLY through the backend's service-role client, which scopes every query by ``org_id``. A browser role
holding a privilege on one of these tables is a direct path around the backend (security triage 2026-11-07; igig
044 is the model shape). The seed generator (``noctusai_lib.domain.card_hub.card_hub_migration``) emits the
service-only shape; this keeper is the backstop for hand-written / legacy migrations.

Replay model (textual, per product, files in number order, statements in file order): a table is *card-hub shaped*
when a schema holds ``<p>_notas`` + ``<p>_documentos`` + ``<p>_documento_acessos`` for one prefix ``<p>`` (the
generator's signature); its hub is ``<p>_`` + the generator's table suffixes. A hub table is EXPOSED at the end of
the chain unless a ``REVOKE ... FROM ... authenticated`` (explicit, ``ALL TABLES IN SCHEMA``, or igig 044's dynamic
``REVOKE ALL ON schema.%I`` loop) reached it after its last browser ``GRANT`` -- or ``ALTER DEFAULT PRIVILEGES ...
REVOKE`` was in force when it was created (a new table is then born private). Policies do not matter: a table with
no privilege for the role is unreachable whatever its policy says.

``paths`` (repo-relative, the staged delta) limits the REPORT to tables those files touch, so a commit is judged on
what it changes; omitted = every hub table in every active product.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

#: Suffixes of the generator's tables (``CardHubTables`` fields) -- the hub is ``<prefix>_<suffix>``.
HUB_SUFFIXES: tuple[str, ...] = (
    "notas", "tags", "tag_links", "membros", "lembretes", "checklists", "checklist_itens", "checklist_extras",
    "documentos", "documento_tipos", "documento_acessos",
)
#: The signature: a schema holding all three for one prefix is a card hub.
_SIGNATURE: tuple[str, ...] = ("notas", "documentos", "documento_acessos")

_BROWSER = frozenset({"authenticated", "anon", "public"})
_ID = r'"?[\w-]+"?'
_QNAME = rf"{_ID}\.{_ID}"

_EVENT_RE = re.compile(
    rf"""
    (?P<create>CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<c_s>{_ID})\.(?P<c_t>{_ID}))
  | (?P<dyn>REVOKE\s+ALL\s+(?:PRIVILEGES\s+)?ON\s+(?P<d_s>{_ID})\.%I\s+FROM\s+(?P<d_roles>[^;']+))
  | (?P<revoke_all>REVOKE\s+[^;]*?\bON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+(?P<ra_s>{_ID})\s+FROM\s+(?P<ra_roles>[^;]+))
  | (?P<revoke>REVOKE\s+(?P<r_privs>[^;]*?)\s+ON\s+(?:TABLE\s+)?(?P<r_tabs>{_QNAME}(?:\s*,\s*{_QNAME})*)\s+FROM\s+(?P<r_roles>[^;]+))
  | (?P<grant_all>GRANT\s+[^;]*?\bON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+(?P<ga_s>{_ID})\s+TO\s+(?P<ga_roles>[^;]+))
  | (?P<grant>GRANT\s+(?P<g_privs>[^;]*?)\s+ON\s+(?:TABLE\s+)?(?P<g_tabs>{_QNAME}(?:\s*,\s*{_QNAME})*)\s+TO\s+(?P<g_roles>[^;]+))
  | (?P<defpriv>ALTER\s+DEFAULT\s+PRIVILEGES\s+(?:FOR\s+(?:ROLE|USER)\s+\w+\s+)?IN\s+SCHEMA\s+(?P<dp_s>{_ID})\s+(?P<dp_verb>REVOKE|GRANT)\s+[^;]*?\bON\s+TABLES\s+(?:FROM|TO)\s+(?P<dp_roles>[^;]+))
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def _roles(raw: str) -> set[str]:
    return {r.strip().strip('"').lower() for r in raw.replace("\n", " ").split(",") if r.strip()}


def _id(raw: str) -> str:
    return raw.strip().strip('"').lower()


def _tables(raw: str) -> list[tuple[str, str]]:
    out = []
    for q in raw.split(","):
        s, _, t = q.strip().partition(".")
        out.append((_id(s), _id(t)))
    return out


def _covers_browser(roles: set[str]) -> bool:
    """A REVOKE closes the browser path when it names authenticated AND (anon or PUBLIC)."""
    return "authenticated" in roles and bool(roles & {"anon", "public"})


def _strip(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", text)


def _hub_tables(created: set[tuple[str, str]]) -> set[tuple[str, str]]:
    hubs: set[tuple[str, str]] = set()
    by_schema: dict[str, set[str]] = {}
    for s, t in created:
        by_schema.setdefault(s, set()).add(t)
    for s, names in by_schema.items():
        for n in names:
            if not n.endswith("_notas"):
                continue
            prefix = n[: -len("_notas")]
            if all(f"{prefix}_{sig}" in names for sig in _SIGNATURE):
                hubs |= {(s, f"{prefix}_{suf}") for suf in HUB_SUFFIXES if f"{prefix}_{suf}" in names}
    return hubs


def exposed_hub_tables(product_dir: Path, paths: set[str] | None = None, root: Path | None = None) -> dict[tuple[str, str], str]:
    """``{(schema, table): file-that-left-it-exposed}`` for the hub tables of ONE product still browser-reachable."""
    mig_dir = product_dir / "backend" / "migrations"
    if not mig_dir.is_dir():
        return {}
    exposed: dict[tuple[str, str], str] = {}
    created: set[tuple[str, str]] = set()
    default_private: dict[str, bool] = {}
    touched: set[tuple[str, str]] = set()
    schema_tables: dict[str, set[tuple[str, str]]] = {}
    for f in sorted(mig_dir.glob("*.sql")):
        rel = str(f.relative_to(root)) if root else f.name
        in_delta = paths is None or rel in paths
        try:
            text = _strip(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("card_hub_service_only: cannot read %s (%s)", f, exc)
            continue
        for m in _EVENT_RE.finditer(text):
            kind = m.lastgroup
            if m.group("create"):
                key = (_id(m.group("c_s")), _id(m.group("c_t")))
                if key not in created:
                    created.add(key)
                    schema_tables.setdefault(key[0], set()).add(key)
                    if not default_private.get(key[0], False):
                        exposed[key] = rel
                if in_delta:
                    touched.add(key)
            elif m.group("dyn"):
                if _covers_browser(_roles(m.group("d_roles"))):
                    for key in schema_tables.get(_id(m.group("d_s")), ()):
                        exposed.pop(key, None)
            elif m.group("revoke_all"):
                if _covers_browser(_roles(m.group("ra_roles"))):
                    for key in schema_tables.get(_id(m.group("ra_s")), ()):
                        exposed.pop(key, None)
            elif m.group("revoke"):
                if _covers_browser(_roles(m.group("r_roles"))):
                    for key in _tables(m.group("r_tabs")):
                        exposed.pop(key, None)
                        if in_delta:
                            touched.add(key)
            elif m.group("grant_all"):
                if _roles(m.group("ga_roles")) & _BROWSER:
                    for key in schema_tables.get(_id(m.group("ga_s")), ()):
                        exposed[key] = rel
            elif m.group("grant"):
                if _roles(m.group("g_roles")) & _BROWSER:
                    for key in _tables(m.group("g_tabs")):
                        if key in created:
                            exposed[key] = rel
                        if in_delta:
                            touched.add(key)
            elif kind == "defpriv" or m.group("defpriv"):
                roles = _roles(m.group("dp_roles"))
                if m.group("dp_verb").upper() == "REVOKE":
                    if _covers_browser(roles):
                        default_private[_id(m.group("dp_s"))] = True
                elif roles & _BROWSER:
                    default_private[_id(m.group("dp_s"))] = False
    hubs = _hub_tables(created)
    out = {k: v for k, v in exposed.items() if k in hubs}
    if paths is not None:
        out = {k: v for k, v in out.items() if k in touched}
    return out


def check_card_hub_service_only(
    repo_root: Path, paths: list[str] | None = None, product_dirs: list[Path] | None = None,
) -> list[dict]:
    """A seed card-hub table still holding an authenticated/anon privilege at the end of its product's migration chain."""
    products = product_dirs if product_dirs is not None else _active_dirs(repo_root)
    wanted = {str(Path(p)) for p in paths} if paths else None
    issues: list[dict] = []
    for pdir in products:
        for (schema, table), rel in sorted(exposed_hub_tables(pdir, wanted, repo_root).items()):
            issues.append({
                "file": rel,
                "issue": (
                    f"card-hub table `{schema}.{table}` is still reachable by anon/authenticated at the end of "
                    f"`{pdir.name}`'s migration chain. The card hub is service-only by construction (the backend "
                    f"scopes by org_id through the service-role client): `REVOKE ALL ON TABLE {schema}.{table} FROM "
                    f"PUBLIC, anon, authenticated` + `COMMENT ON TABLE ... IS 'tier:org'` (generate it with "
                    f"`noctusai_lib.domain.card_hub.card_hub_migration`, igig 044 is the model). "
                    f"KB § PATTERNS/security/access-tiers.md."
                ),
                "severity": "critical",
            })
    return issues


def _active_dirs(root: Path) -> list[Path]:
    from .compliance import _active_product_dirs

    return _active_product_dirs(root / "products")
