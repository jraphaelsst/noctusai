"""`noctus.dev.agent_package_build` — build an Agent Package (CONTRACT §B + §C).

Contract: ``products/agents/projects/agent-packages/CONTRACT.md``.

One package authored in git under ``products/agents/packages/<key>/`` becomes TWO generated
surfaces by ONE build (A2/A3):

1. the Studio bundle (``noctus.agent-bundle/v1``, Studio §F + the §C4 keys) -> ``dist/bundle.json``;
2. the Claude Code tree (``.claude/agents/<key>.md`` + ``agents/<key>/...``) -> ``dist/claude/``.

The prompt body is produced by the REAL ``compile_prompt`` of Agent Studio
(``products/agents/backend/app/studio/compiler.py``, A3 — never re-implemented). It is a pure
function over stdlib dataclasses; this module loads it through ``_load_studio`` (see there for the
import seam). The Studio importer's strict pydantic models validate the bundle when importable.

Pure functions live here; ``register`` exposes the MCP tool. ``agent_pull`` reuses
``build_package`` + the LEARNINGS helpers (``merge_learnings`` / ``row_sha``).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("noctus.dev.agent_package_build")

PACKAGE_FORMAT = "noctus.agent-package/v1"
BUNDLE_FORMAT = "noctus.agent-bundle/v1"
KINDS = ("runtime", "dev-advisor")
#: A10 — the only Claude Code tools a dev-advisor may carry.
READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob"})
DEFAULT_ADVISOR_TOOLS = ("Read", "Grep", "Glob")

# Mirrors the Studio patterns (app/schemas/studio.py SLUG_PATTERN / CAMINHO_PATTERN); the real
# importer models re-check them, these give a path-precise error earlier.
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_CAMINHO_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
_SECTION_FILE_RE = re.compile(r"^(\d+)-(.+)\.md$")
DOCUMENT_TYPES = ("fonte", "sintese", "card", "template", "indice", "outro")
MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")

_PACKAGE_KEYS_REQUIRED = {"formato", "key", "nome", "descricao", "kind", "idioma", "versao", "runtime"}
_PACKAGE_KEYS_ALLOWED = _PACKAGE_KEYS_REQUIRED | {"owners", "claude_code", "consumers"}
_RUNTIME_KEYS = {"model", "effort", "max_turns", "tool_policy"}
_TOOL_POLICY_KEYS = {"web_search", "knowledge"}

# Learnings (§H1)
LEARNINGS_HEADER = "| Data | Tipo | Aprendizado | Evidência | Status |"
LEARNINGS_SEPARATOR = "|---|---|---|---|---|"
LEARNING_TIPOS = frozenset({"pitfall", "armadilha", "practice", "prática", "pratica", "decision", "decisão", "decisao"})
LEARNING_STATUSES = frozenset({"new", "novo", "absorbed", "absorvido", "promoted", "promovido"})


class PackageError(Exception):
    """A package the build refuses. ``errors`` is a list of ``path: message`` strings."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


# ── learnings (§H1) — shared with agent_pull ────────────────────────────────


def _split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    cells = re.split(r"(?<!\\)\|", inner)
    return [c.strip() for c in cells]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "") and any(cells)


def _is_header(cells: list[str]) -> bool:
    return bool(cells) and cells[0].strip().lower() in ("data", "date")


def row_sha(data: str, texto: str) -> str:
    """§H1 row identity: sha256 over (date, learning text), whitespace-normalised."""
    norm = lambda s: " ".join(s.split())  # noqa: E731 — tiny local normaliser
    return hashlib.sha256(f"{norm(data)}\n{norm(texto)}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LearningRow:
    line_index: int
    raw: str
    data: str
    tipo: str
    texto: str
    evidencia: str
    status: str

    @property
    def sha(self) -> str:
        return row_sha(self.data, self.texto)


def parse_learnings(text: str) -> tuple[list[LearningRow], list[str]]:
    """Parse the §H1 table. Returns (rows, errors); header/separator lines are skipped."""
    rows: list[LearningRow] = []
    errors: list[str] = []
    for i, line in enumerate(text.splitlines()):
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if _is_header(cells) or _is_separator(cells):
            continue
        if len(cells) != 5:
            errors.append(f"LEARNINGS.md:{i + 1}: expected 5 columns, got {len(cells)}")
            continue
        data, tipo, texto, evid, status = cells
        if not data or not texto:
            errors.append(f"LEARNINGS.md:{i + 1}: Data and Aprendizado must be non-empty")
            continue
        if tipo.lower() not in LEARNING_TIPOS:
            errors.append(f"LEARNINGS.md:{i + 1}: tipo {tipo!r} not in {sorted(LEARNING_TIPOS)}")
            continue
        if status.lower() not in LEARNING_STATUSES:
            errors.append(f"LEARNINGS.md:{i + 1}: status {status!r} not in {sorted(LEARNING_STATUSES)}")
            continue
        rows.append(LearningRow(i, line, data, tipo, texto, evid, status))
    return rows, errors


def merge_learnings(consumer_text: str | None, upstream_text: str) -> tuple[str, list[LearningRow]]:
    """Merge upstream LEARNINGS rows into the consumer file (§E / §H1).

    Consumer content is kept byte-for-byte (rows never deleted or reordered); upstream rows whose
    row-sha is absent are appended after the consumer's last table row. Idempotent. Returns the
    merged text and the rows that were added.
    """
    up_rows, _ = parse_learnings(upstream_text)
    if consumer_text is None:
        return upstream_text, list(up_rows)
    cons_rows, _ = parse_learnings(consumer_text)
    have = {r.sha for r in cons_rows}
    added = [r for r in up_rows if r.sha not in have]
    if not added:
        return consumer_text, []
    lines = consumer_text.splitlines()
    table_idx = [i for i, ln in enumerate(lines) if ln.strip().startswith("|")]
    new_lines = [r.raw.rstrip() for r in added]
    if table_idx:
        at = table_idx[-1] + 1
        lines[at:at] = new_lines
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([LEARNINGS_HEADER, LEARNINGS_SEPARATOR, *new_lines])
    merged = "\n".join(lines)
    if consumer_text.endswith("\n") or not table_idx:
        merged += "\n"
    return merged, added


# ── reading the package ─────────────────────────────────────────────────────


def _split_frontmatter(text: str, where: str, errors: list[str]) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        errors.append(f"{where}: missing YAML frontmatter")
        return {}, text
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        errors.append(f"{where}: unterminated frontmatter")
        return {}, text
    head = parts[0][3:]
    body = parts[1]
    body = body[body.index("\n") + 1:] if "\n" in body else ""
    try:
        meta = yaml.safe_load(head) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{where}: invalid frontmatter YAML ({exc})")
        return {}, body
    if not isinstance(meta, dict):
        errors.append(f"{where}: frontmatter must be a mapping")
        return {}, body
    return meta, body


def _check_keys(obj: dict[str, Any], required: set[str], allowed: set[str], where: str, errors: list[str]) -> None:
    for k in sorted(required - obj.keys()):
        errors.append(f"{where}: missing required key {k!r}")
    for k in sorted(obj.keys() - allowed):
        errors.append(f"{where}: unknown key {k!r}")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _visible_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts))


@dataclass
class PackageData:
    key: str
    root: Path
    meta: dict[str, Any]
    secoes: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    conhecimento: list[dict[str, Any]] = field(default_factory=list)
    evals: list[dict[str, Any]] = field(default_factory=list)
    learnings: str = ""
    changelog: str = ""
    notas: str = ""
    #: relpath (posix, under the package) -> text, for the generated Claude tree copies.
    skill_files: dict[str, str] = field(default_factory=dict)
    knowledge_files: dict[str, str] = field(default_factory=dict)


def _validate_package_yaml(meta: Any, folder: str, errors: list[str]) -> None:
    if not isinstance(meta, dict):
        errors.append("package.yaml: must be a mapping")
        return
    _check_keys(meta, _PACKAGE_KEYS_REQUIRED, _PACKAGE_KEYS_ALLOWED, "package.yaml", errors)
    if meta.get("formato") != PACKAGE_FORMAT:
        errors.append(f"package.yaml: formato must be {PACKAGE_FORMAT!r}")
    key = meta.get("key")
    if not isinstance(key, str) or not _SLUG_RE.match(key) or len(key) > 64:
        errors.append("package.yaml: key must be kebab-case (<= 64 chars)")
    elif key != folder:
        errors.append(f"package.yaml: key {key!r} must equal the folder name {folder!r}")
    for k in ("nome", "descricao", "idioma"):
        if k in meta and (not isinstance(meta[k], str) or not meta[k].strip()):
            errors.append(f"package.yaml: {k} must be a non-empty string")
    if isinstance(meta.get("descricao"), str) and len(meta["descricao"]) > 600:
        errors.append("package.yaml: descricao must be <= 600 chars")
    if meta.get("kind") not in KINDS:
        errors.append(f"package.yaml: kind must be one of {list(KINDS)}")
    if not isinstance(meta.get("versao"), str) or not _SEMVER_RE.match(meta["versao"]):
        errors.append("package.yaml: versao must be a semver string (quote it)")
    for k in ("owners", "consumers"):
        v = meta.get(k)
        if v is not None and not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
            errors.append(f"package.yaml: {k} must be a list of strings")
    rt = meta.get("runtime")
    if isinstance(rt, dict):
        _check_keys(rt, {"model", "effort"}, _RUNTIME_KEYS, "package.yaml: runtime", errors)
        if rt.get("model") not in MODELS:
            errors.append(f"package.yaml: runtime.model must be one of {list(MODELS)}")
        if rt.get("effort") not in EFFORTS:
            errors.append(f"package.yaml: runtime.effort must be one of {list(EFFORTS)}")
        mt = rt.get("max_turns", 40)
        if not _is_int(mt) or not 1 <= mt <= 200:
            errors.append("package.yaml: runtime.max_turns must be an int in 1..200")
        tp = rt.get("tool_policy", {})
        if not isinstance(tp, dict):
            errors.append("package.yaml: runtime.tool_policy must be a mapping")
        else:
            for k in sorted(tp.keys() - _TOOL_POLICY_KEYS):
                errors.append(f"package.yaml: runtime.tool_policy: unknown key {k!r}")
            for k, v in tp.items():
                if not isinstance(v, bool):
                    errors.append(f"package.yaml: runtime.tool_policy.{k} must be a boolean")
    elif "runtime" in meta:
        errors.append("package.yaml: runtime must be a mapping")
    cc = meta.get("claude_code")
    if cc is not None:
        if not isinstance(cc, dict):
            errors.append("package.yaml: claude_code must be a mapping")
        else:
            for k in sorted(cc.keys() - {"tools"}):
                errors.append(f"package.yaml: claude_code: unknown key {k!r}")
            tools = cc.get("tools")
            if not (isinstance(tools, list) and tools and all(isinstance(t, str) and t for t in tools)):
                errors.append("package.yaml: claude_code.tools must be a non-empty list of strings")
            elif len(set(tools)) != len(tools):
                errors.append("package.yaml: claude_code.tools has duplicates")
    # A10 — dev-advisors are read-only on both surfaces.
    if meta.get("kind") == "dev-advisor":
        tools = (cc or {}).get("tools") if isinstance(cc, dict) else None
        if isinstance(tools, list):
            bad = [t for t in tools if t not in READ_ONLY_TOOLS]
            if bad:
                errors.append(
                    f"package.yaml: A10 — dev-advisor claude_code.tools must be a subset of "
                    f"{sorted(READ_ONLY_TOOLS)}; write-capable/unknown tool(s): {bad}"
                )


def _read_sections(root: Path, errors: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sdir = root / "sections"
    if not sdir.is_dir():
        errors.append("sections/: directory missing")
        return out
    for f in sorted(p for p in sdir.iterdir() if p.is_file() and not p.name.startswith(".")):
        where = f"sections/{f.name}"
        m = _SECTION_FILE_RE.match(f.name)
        if not m:
            errors.append(f"{where}: file name must be NN-<chave>.md")
            continue
        meta, body = _split_frontmatter(f.read_text(encoding="utf-8"), where, errors)
        if not meta:
            continue
        _check_keys(meta, {"chave", "titulo", "ordem"}, {"chave", "titulo", "ordem", "ativo"}, where, errors)
        chave = meta.get("chave")
        if not isinstance(chave, str) or not _SLUG_RE.match(chave):
            errors.append(f"{where}: chave must be kebab-case")
            continue
        if chave != m.group(2):
            errors.append(f"{where}: chave {chave!r} must equal the file-name suffix {m.group(2)!r}")
        if not isinstance(meta.get("titulo"), str) or not meta["titulo"].strip():
            errors.append(f"{where}: titulo must be a non-empty string")
            continue
        if not _is_int(meta.get("ordem")):
            errors.append(f"{where}: ordem must be an int")
            continue
        if "ativo" in meta and not isinstance(meta["ativo"], bool):
            errors.append(f"{where}: ativo must be a boolean")
            continue
        out.append({"chave": chave, "titulo": meta["titulo"].strip(), "ordem": meta["ordem"],
                    "conteudo": body.strip(), "ativo": meta.get("ativo", True)})
    seen: set[str] = set()
    for s in out:
        if s["chave"] in seen:
            errors.append(f"sections/: duplicate chave {s['chave']!r}")
        seen.add(s["chave"])
    return out


def _read_skills(root: Path, errors: list[str], skill_files: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    kdir = root / "skills"
    if not kdir.is_dir():
        return out
    for d in sorted(p for p in kdir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        where = f"skills/{d.name}"
        md = d / "SKILL.md"
        if not md.is_file():
            errors.append(f"{where}: SKILL.md missing")
            continue
        text = md.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text, f"{where}/SKILL.md", errors)
        if not meta:
            continue
        _check_keys(meta, {"nome", "descricao", "ordem"}, {"nome", "descricao", "ordem"}, f"{where}/SKILL.md", errors)
        nome = meta.get("nome")
        if not isinstance(nome, str) or not _SLUG_RE.match(nome):
            errors.append(f"{where}/SKILL.md: nome must be kebab-case")
            continue
        if nome != d.name:
            errors.append(f"{where}/SKILL.md: nome {nome!r} must equal the folder name {d.name!r}")
        if not isinstance(meta.get("descricao"), str) or not meta["descricao"].strip():
            errors.append(f"{where}/SKILL.md: descricao must be a non-empty string")
            continue
        if not _is_int(meta.get("ordem")):
            errors.append(f"{where}/SKILL.md: ordem must be an int")
            continue
        arquivos: list[dict[str, Any]] = []
        skill_files[f"skills/{d.name}/SKILL.md"] = text
        for f in _visible_files(d):
            rel = f.relative_to(d).as_posix()
            if rel == "SKILL.md":
                continue
            if not (rel.startswith("references/") and rel.endswith(".md")):
                errors.append(f"{where}/{rel}: only SKILL.md and references/*.md are allowed")
                continue
            if not _CAMINHO_RE.match(rel) or ".." in rel:
                errors.append(f"{where}/{rel}: invalid caminho")
                continue
            ftext = f.read_text(encoding="utf-8")
            skill_files[f"skills/{d.name}/{rel}"] = ftext
            arquivos.append({"caminho": rel, "titulo": _first_heading(ftext), "conteudo": ftext})
        out.append({"nome": nome, "descricao": meta["descricao"].strip(), "corpo": body.strip(),
                    "ordem": meta["ordem"], "ativo": True, "arquivos": arquivos})
    seen: set[str] = set()
    for s in out:
        if s["nome"] in seen:
            errors.append(f"skills/: duplicate nome {s['nome']!r}")
        seen.add(s["nome"])
    return out


def _read_knowledge(root: Path, errors: list[str], knowledge_files: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    kdir = root / "knowledge"
    if not kdir.is_dir():
        return out
    for d in sorted(p for p in kdir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        where = f"knowledge/{d.name}"
        cfile = d / "_collection.yaml"
        if not cfile.is_file():
            errors.append(f"{where}: _collection.yaml missing")
            continue
        ctext = cfile.read_text(encoding="utf-8")
        try:
            cmeta = yaml.safe_load(ctext) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{where}/_collection.yaml: invalid YAML ({exc})")
            continue
        if not isinstance(cmeta, dict):
            errors.append(f"{where}/_collection.yaml: must be a mapping")
            continue
        _check_keys(cmeta, {"nome", "ordem"}, {"nome", "tag", "descricao", "ordem"}, f"{where}/_collection.yaml", errors)
        if not _SLUG_RE.match(d.name):
            errors.append(f"{where}: collection folder must be kebab-case")
            continue
        if not isinstance(cmeta.get("nome"), str) or not cmeta["nome"].strip():
            errors.append(f"{where}/_collection.yaml: nome must be a non-empty string")
            continue
        if not _is_int(cmeta.get("ordem")):
            errors.append(f"{where}/_collection.yaml: ordem must be an int")
            continue
        knowledge_files[f"knowledge/{d.name}/_collection.yaml"] = ctext
        docs: list[dict[str, Any]] = []
        for f in _visible_files(d):
            rel = f.relative_to(d).as_posix()
            if rel == "_collection.yaml":
                continue
            fw = f"{where}/{rel}"
            if "/" in rel or not rel.endswith(".md"):
                errors.append(f"{fw}: knowledge documents must be <slug>.md directly under the collection")
                continue
            slug = rel[:-3]
            if not _SLUG_RE.match(slug):
                errors.append(f"{fw}: slug must be kebab-case")
                continue
            text = f.read_text(encoding="utf-8")
            meta, body = _split_frontmatter(text, fw, errors)
            if not meta:
                continue
            _check_keys(meta, {"titulo", "tipo"}, {"titulo", "tipo", "resumo", "proveniencia"}, fw, errors)
            if not isinstance(meta.get("titulo"), str) or not meta["titulo"].strip():
                errors.append(f"{fw}: titulo must be a non-empty string")
                continue
            if meta.get("tipo") not in DOCUMENT_TYPES:
                errors.append(f"{fw}: tipo must be one of {list(DOCUMENT_TYPES)}")
                continue
            if not body.strip():
                errors.append(f"{fw}: empty body")
                continue
            prov = meta.get("proveniencia", {}) or {}
            if not isinstance(prov, dict):
                errors.append(f"{fw}: proveniencia must be a mapping")
                continue
            knowledge_files[f"knowledge/{d.name}/{rel}"] = text
            docs.append({"slug": slug, "titulo": meta["titulo"].strip(), "tipo": meta["tipo"],
                         "resumo": meta.get("resumo"), "proveniencia": prov, "conteudo": body.strip()})
        out.append({"slug": d.name, "nome": cmeta["nome"].strip(), "tag": cmeta.get("tag"),
                    "descricao": cmeta.get("descricao") or "", "ordem": cmeta["ordem"], "documentos": docs})
    return out


def _validate_evals(root: Path, errors: list[str]) -> list[dict[str, Any]]:
    f = root / "evals.json"
    if not f.is_file():
        errors.append("evals.json: missing")
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"evals.json: invalid JSON ({exc})")
        return []
    if not isinstance(data, list):
        errors.append("evals.json: must be a JSON array of Studio §F eval objects")
        return []
    required = {"slug", "titulo", "entrada", "criterios"}
    allowed = required | {"contexto", "rubrica", "tags"}
    seen: set[str] = set()
    for i, e in enumerate(data):
        w = f"evals.json[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{w}: must be an object")
            continue
        _check_keys(e, required, allowed, w, errors)
        slug = e.get("slug")
        if not isinstance(slug, str) or not _SLUG_RE.match(slug):
            errors.append(f"{w}.slug: must be kebab-case")
        elif slug in seen:
            errors.append(f"{w}.slug: duplicate {slug!r}")
        else:
            seen.add(slug)
        for k in ("titulo", "entrada"):
            if k in e and (not isinstance(e[k], str) or not e[k].strip()):
                errors.append(f"{w}.{k}: must be a non-empty string")
        for k in ("contexto", "rubrica"):
            if e.get(k) is not None and not isinstance(e[k], str):
                errors.append(f"{w}.{k}: must be a string or null")
        tags = e.get("tags", [])
        if not (isinstance(tags, list) and all(isinstance(t, str) and 0 < len(t) <= 64 for t in tags)):
            errors.append(f"{w}.tags: must be a list of 1..64-char strings")
        c = e.get("criterios")
        if isinstance(c, dict):
            _check_keys(c, set(), {"deve", "nao_deve"}, f"{w}.criterios", errors)
            items: list[Any] = []
            shape_ok = True
            for k in ("deve", "nao_deve"):
                v = c.get(k, [])
                if not (isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)):
                    errors.append(f"{w}.criterios.{k}: must be a list of non-blank strings")
                    shape_ok = False
                else:
                    items.extend(v)
            if shape_ok and not items:
                errors.append(f"{w}.criterios: needs at least one item across deve/nao_deve")
        elif "criterios" in e:
            errors.append(f"{w}.criterios: must be an object {{deve, nao_deve}}")
    return data


def _changelog_notes(changelog: str, versao: str, errors: list[str]) -> str:
    """The CHANGELOG section for ``versao`` (heading line containing the version) -> bundle notas."""
    lines = changelog.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#") and re.search(rf"(?<![\w.]){re.escape(versao)}(?![\w.])", ln):
            start = i
            break
    if start is None:
        errors.append(f"CHANGELOG.md: no entry for versao {versao!r} (a heading containing the version is required)")
        return ""
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    body: list[str] = []
    for ln in lines[start + 1:]:
        if ln.startswith("#") and len(ln) - len(ln.lstrip("#")) <= level:
            break
        body.append(ln)
    text = "\n".join(body).strip()
    return text[:5000]


def read_package(root: Path) -> PackageData:
    """Read + strictly validate a package folder. Raises ``PackageError`` with every problem found."""
    errors: list[str] = []
    if not root.is_dir():
        raise PackageError([f"package folder not found: {root}"])
    pyaml = root / "package.yaml"
    if not pyaml.is_file():
        raise PackageError(["package.yaml: missing"])
    try:
        meta = yaml.safe_load(pyaml.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackageError([f"package.yaml: invalid YAML ({exc})"]) from exc
    _validate_package_yaml(meta, root.name, errors)
    pkg = PackageData(key=root.name, root=root, meta=meta if isinstance(meta, dict) else {})
    pkg.secoes = _read_sections(root, errors)
    pkg.skills = _read_skills(root, errors, pkg.skill_files)
    pkg.conhecimento = _read_knowledge(root, errors, pkg.knowledge_files)
    pkg.evals = _validate_evals(root, errors)
    seen_cols: set[str] = set()
    seen_docs: set[str] = set()
    for c in pkg.conhecimento:
        if c["slug"] in seen_cols:
            errors.append(f"knowledge/: duplicate collection {c['slug']!r}")
        seen_cols.add(c["slug"])
        for d in c["documentos"]:
            if d["slug"] in seen_docs:  # unique across collections (Studio knowledge_documents)
                errors.append(f"knowledge/: duplicate document slug {d['slug']!r}")
            seen_docs.add(d["slug"])
    lf = root / "LEARNINGS.md"
    if not lf.is_file():
        errors.append("LEARNINGS.md: missing")
    else:
        pkg.learnings = lf.read_text(encoding="utf-8")
        _rows, lerrs = parse_learnings(pkg.learnings)
        errors.extend(lerrs)
    cf = root / "CHANGELOG.md"
    if not cf.is_file():
        errors.append("CHANGELOG.md: missing")
    elif isinstance(pkg.meta.get("versao"), str):
        pkg.changelog = cf.read_text(encoding="utf-8")
        pkg.notas = _changelog_notes(pkg.changelog, pkg.meta["versao"], errors)
    if not pkg.secoes and not errors:
        errors.append("sections/: at least one section is required")
    if errors:
        raise PackageError(errors)
    return pkg


def package_sha(root: Path) -> str:
    """sha256 over the package tree: sorted posix paths + contents, ``dist/`` and dotfiles excluded (§C3)."""
    h = hashlib.sha256()
    for f in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        rel = f.relative_to(root)
        if not f.is_file() or rel.parts[0] == "dist" or any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        h.update(rel.as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


# ── Studio import seam (compile_prompt + importer models) ───────────────────


class StudioUnavailable(Exception):
    """The agents-backend ``app.studio`` package cannot be loaded here."""


_STUDIO: dict[str, Any] = {}


def _load_studio(backend_dir: Path) -> dict[str, Any]:
    """Load the REAL ``app.studio.compiler`` / ``models`` (and, if importable, ``importer``).

    Import chain: ``app.studio`` -> ``compiler`` -> ``models`` — stdlib only (no pydantic, no
    supabase), so ``sys.path`` insertion of ``products/agents/backend`` is enough. The importer
    pulls pydantic + ``noctusai_lib`` + the agents stores; it is optional (``importer`` is None if
    its chain does not resolve in this interpreter). The modules stay in ``sys.modules`` (pydantic
    resolves forward refs through it); if a DIFFERENT product's ``app`` package is already loaded we
    refuse loudly rather than silently compiling against the wrong code.
    """
    if _STUDIO:
        return _STUDIO
    comp_file = backend_dir / "app" / "studio" / "compiler.py"
    if not comp_file.is_file():
        raise StudioUnavailable(f"compiler not found: {comp_file}")
    existing = sys.modules.get("app")
    if existing is not None:
        loaded_from = Path(getattr(existing, "__file__", "") or "").resolve()
        if backend_dir.resolve() not in loaded_from.parents:
            raise StudioUnavailable(
                f"a different 'app' package is already imported ({loaded_from}); "
                "run the build in a fresh process (python mcp/noctusai/cli.py) — seam: extract compile_prompt "
                "into noctusai_lib if this recurs"
            )
    sys.path.insert(0, str(backend_dir))
    try:
        from app.studio import models as m  # type: ignore[import-not-found]
        from app.studio.compiler import compile_prompt  # type: ignore[import-not-found]
        importer = None
        importer_error = None
        try:
            from app.studio import importer as importer_mod  # type: ignore[import-not-found]
            importer = importer_mod
        except Exception as exc:  # noqa: BLE001 — optional leg; reported, never silent
            importer_error = f"{type(exc).__name__}: {exc}"
            logger.warning("studio importer not importable (%s); bundle validated against §F subset only", importer_error)
    finally:
        try:
            sys.path.remove(str(backend_dir))
        except ValueError:
            pass
    _STUDIO.update(models=m, compile_prompt=compile_prompt, importer=importer, importer_error=importer_error)
    return _STUDIO


def build_bundle(pkg: PackageData, sha: str) -> dict[str, Any]:
    """The Studio import body: Studio §F + the §C4 keys."""
    rt = pkg.meta["runtime"]
    tp = rt.get("tool_policy", {})
    return {
        "formato": BUNDLE_FORMAT,
        "agente": {"key": pkg.meta["key"], "nome": pkg.meta["nome"], "descricao": pkg.meta["descricao"],
                   "kind": pkg.meta["kind"]},
        "versao": {
            "notas": pkg.notas, "model": rt["model"], "effort": rt["effort"],
            "max_turns": rt.get("max_turns", 40), "idioma": pkg.meta["idioma"],
            "tool_policy": {"web_search": tp.get("web_search", False), "knowledge": tp.get("knowledge", True)},
            "versao_semver": pkg.meta["versao"], "package_sha": sha,
        },
        "secoes": [dict(s) for s in sorted(pkg.secoes, key=lambda s: (s["ordem"], s["chave"]))],
        "skills": [dict(s) for s in sorted(pkg.skills, key=lambda s: (s["ordem"], s["nome"]))],
        "conhecimento": [dict(c) for c in sorted(pkg.conhecimento, key=lambda c: (c["ordem"], c["slug"]))],
        "evals": pkg.evals,
        "clientes": [],
    }


_C4_KEYS = (("agente", "kind"), ("versao", "versao_semver"), ("versao", "package_sha"))


def validate_bundle(bundle: dict[str, Any], studio: dict[str, Any]) -> dict[str, Any]:
    """Validate against the real importer models. Strict first; if only the §C4 keys are rejected
    (expected until BE-API wave 2) validate the §F subset and say so."""
    importer = studio.get("importer")
    if importer is None:
        return {"status": "skipped", "reason": studio.get("importer_error") or "importer unavailable", "errors": []}
    Model = importer.AgentBundle
    try:
        Model.model_validate(bundle)
        return {"status": "ok", "errors": []}
    except Exception as full_exc:  # noqa: BLE001 — pydantic ValidationError, any shape reported
        subset = json.loads(json.dumps(bundle))
        for outer, inner in _C4_KEYS:
            subset[outer].pop(inner, None)
        try:
            Model.model_validate(subset)
        except Exception as sub_exc:  # noqa: BLE001
            return {"status": "rejected", "errors": _pydantic_errors(sub_exc)}
        return {"status": "ok_subset_f", "errors": [],
                "note": "importer rejects the §C4 keys (expected until wave 2 / BE-API D2); §F subset valid",
                "c4_errors": _pydantic_errors(full_exc)}


def _pydantic_errors(exc: Exception) -> list[str]:
    errs = getattr(exc, "errors", None)
    if callable(errs):
        try:
            return [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in errs()]
        except Exception:  # noqa: BLE001
            pass
    return [str(exc)]


def compile_bundle(bundle: dict[str, Any], studio: dict[str, Any]) -> Any:
    """Build ``CompileInput`` from the bundle and call the REAL ``compile_prompt`` (A3)."""
    m = studio["models"]
    v = bundle["versao"]
    secoes = tuple(m.SectionData(id=None, chave=s["chave"], titulo=s["titulo"], ordem=s["ordem"],
                                 conteudo=s["conteudo"], ativo=s["ativo"]) for s in bundle["secoes"])
    skills = tuple(
        m.SkillData(
            id=None, nome=s["nome"], descricao=s["descricao"], corpo=s["corpo"], ordem=s["ordem"], ativo=s["ativo"],
            arquivos=tuple(m.SkillFileRef(caminho=a["caminho"], titulo=a["titulo"], chars=len(a["conteudo"]))
                           for a in s["arquivos"]),
        ) for s in bundle["skills"]
    )
    knowledge = tuple(
        m.CollectionSummary(slug=c["slug"], nome=c["nome"], tag=c["tag"], descricao=c["descricao"],
                            doc_count=len(c["documentos"]), ordem=c["ordem"]) for c in bundle["conhecimento"]
    )
    tp = dict(v["tool_policy"])
    inp = m.CompileInput(
        agent_nome=bundle["agente"]["nome"],
        version=m.VersionBundle(model=v["model"], effort=v["effort"], max_turns=v["max_turns"], idioma=v["idioma"],
                                tool_policy=tp, secoes=secoes, skills=skills),
        knowledge=knowledge, client=None, tool_policy=tp,
    )
    return studio["compile_prompt"](inp)


# ── Claude Code surface (§C2/§C3) ───────────────────────────────────────────


def adapter_block(key: str, idioma: str) -> str:
    """The ONLY surface-specific text (C2), rendered in the package language.

    The mapping sentence translates the Studio tool names that the compiled prompt mentions
    (`abrir_skill`, `kb_buscar`, …) into Claude Code actions — without it those names would be
    dangling references on this surface.
    """
    base = f"agents/{key}"
    if idioma.lower().startswith("pt"):
        return (
            "# Superfície: Claude Code\n\n"
            f"- Skills: `{base}/skills/<nome>/SKILL.md`; os arquivos de referência ficam ao lado "
            f"(`{base}/skills/<nome>/references/`).\n"
            f"- Conhecimento: `{base}/knowledge/<colecao>/<slug>.md`.\n"
            f"- Aprendizados: `{base}/LEARNINGS.md` (as linhas mais recentes prevalecem).\n"
            "- Contexto do projeto = o próprio repositório.\n"
            "- Equivalências: onde o prompt diz `abrir_skill` / `ler_arquivo_skill`, leia o arquivo da skill "
            "(ou de referência) com `Read`; onde diz `kb_buscar` / `kb_ler`, procure com `Grep`/`Glob` e leia "
            "o documento com `Read`, citando a tag da coleção."
        )
    return (
        "# Surface: Claude Code\n\n"
        f"- Skills: `{base}/skills/<name>/SKILL.md`; reference files sit beside it "
        f"(`{base}/skills/<name>/references/`).\n"
        f"- Knowledge: `{base}/knowledge/<collection>/<slug>.md`.\n"
        f"- Learnings: `{base}/LEARNINGS.md` (newest rows win).\n"
        "- Project context = the repository itself.\n"
        "- Equivalences: where the prompt says `abrir_skill` / `ler_arquivo_skill`, read the skill (or reference) "
        "file with `Read`; where it says `kb_buscar` / `kb_ler`, search with `Grep`/`Glob` and read the document "
        "with `Read`, citing the collection tag."
    )


def agent_markdown(pkg: PackageData, compiled_text: str, short_sha: str) -> str:
    meta = pkg.meta
    tools = (meta.get("claude_code") or {}).get("tools") or list(DEFAULT_ADVISOR_TOOLS)
    head = (
        "---\n"
        f"name: {meta['key']}\n"
        f"description: {json.dumps(meta['descricao'], ensure_ascii=False)}\n"
        f"tools: {', '.join(tools)}\n"
        "---\n"
        f"<!-- GENERATED by noctus.dev.agent_pull from {meta['key']}@{meta['versao']} (sha {short_sha}) — do not edit -->\n"
    )
    return head + compiled_text.rstrip("\n") + "\n\n" + adapter_block(meta["key"], meta["idioma"]) + "\n"


def _package_json(pkg: PackageData, sha: str, compiled_hash: str, built_at: str) -> str:
    return json.dumps({"key": pkg.key, "versao": pkg.meta["versao"], "sha": sha, "compiled_hash": compiled_hash,
                       "built_at": built_at}, indent=2, ensure_ascii=False) + "\n"


@dataclass
class BuildResult:
    key: str
    versao: str
    sha: str
    compiled_hash: str
    bundle: dict[str, Any]
    #: relpath (posix, relative to the consumer repo root) -> text
    claude_files: dict[str, str]
    importer_validation: dict[str, Any]
    warnings: list[dict[str, Any]]
    tokens_estimados: int


def build_package(root: Path, backend_dir: Path, *, now: datetime | None = None) -> BuildResult:
    """Validate + build in memory. Raises ``PackageError`` / ``StudioUnavailable``."""
    pkg = read_package(root)
    sha = package_sha(root)
    bundle = build_bundle(pkg, sha)
    studio = _load_studio(backend_dir)
    validation = validate_bundle(bundle, studio)
    if validation["status"] == "rejected":
        raise PackageError([f"importer: {e}" for e in validation["errors"]])
    compiled = compile_bundle(bundle, studio)
    blocking = [w for w in compiled.avisos if w.bloqueante]
    if blocking:
        raise PackageError([f"compile: {w.codigo}: {w.mensagem}" for w in blocking])
    key = pkg.key
    built_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    files: dict[str, str] = {
        f".claude/agents/{key}.md": agent_markdown(pkg, compiled.texto, sha[:12]),
        f"agents/{key}/PACKAGE.json": _package_json(pkg, sha, compiled.hash, built_at),
        f"agents/{key}/LEARNINGS.md": pkg.learnings,
    }
    for rel, text in pkg.skill_files.items():
        files[f"agents/{key}/{rel}"] = text
    for rel, text in pkg.knowledge_files.items():
        files[f"agents/{key}/{rel}"] = text
    return BuildResult(
        key=key, versao=pkg.meta["versao"], sha=sha, compiled_hash=compiled.hash, bundle=bundle,
        claude_files=files, importer_validation=validation,
        warnings=[w.to_dict() for w in compiled.avisos], tokens_estimados=compiled.tokens_estimados,
    )


# ── dist + check ────────────────────────────────────────────────────────────


def write_dist(root: Path, result: BuildResult) -> list[str]:
    dist = root / "dist"
    claude = dist / "claude"
    if claude.exists():
        import shutil
        shutil.rmtree(claude)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "bundle.json").write_text(json.dumps(result.bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written = ["bundle.json"]
    for rel, text in sorted(result.claude_files.items()):
        p = claude / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        written.append(f"claude/{rel}")
    return written


def normalize_for_compare(rel: str, text: str) -> str:
    """PACKAGE.json carries ``built_at`` (non-deterministic) — drop it before comparing."""
    if rel.endswith("/PACKAGE.json"):
        try:
            d = json.loads(text)
            d.pop("built_at", None)
            return json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False)
        except json.JSONDecodeError:
            return text
    return text


#: Consumer-owned (merged by pull, never overwritten) — excluded from check (C5).
def _is_consumer_owned(rel: str) -> bool:
    return rel.endswith("/LEARNINGS.md")


def check_against_repo(result: BuildResult, repo: Path) -> dict[str, Any]:
    """§C5 — compare the build with the materialised files in a consumer repo."""
    missing: list[str] = []
    changed: list[dict[str, str]] = []
    for rel, text in sorted(result.claude_files.items()):
        if _is_consumer_owned(rel):
            continue
        p = repo / rel
        if not p.is_file():
            missing.append(rel)
            continue
        have = p.read_text(encoding="utf-8")
        a, b = normalize_for_compare(rel, have), normalize_for_compare(rel, text)
        if a != b:
            diff = "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                                fromfile=f"consumer/{rel}", tofile=f"build/{rel}", n=2))
            changed.append({"path": rel, "diff": diff})
    extra: list[str] = []
    gen_root = repo / "agents" / result.key
    expected = set(result.claude_files)
    for sub in ("skills", "knowledge"):
        d = gen_root / sub
        if d.is_dir():
            for f in _visible_files(d):
                rel = f.relative_to(repo).as_posix()
                if rel not in expected:
                    extra.append(rel)
    return {"ok": not (missing or changed or extra), "missing": missing, "changed": changed, "extra": extra,
            "skipped_consumer_owned": [r for r in sorted(result.claude_files) if _is_consumer_owned(r)]}


# ── tool entry point ────────────────────────────────────────────────────────


def _roots(worktree_path: str | None, packages_dir: str | None, repo_root: str | None) -> tuple[Path, Path]:
    """-> (packages_dir, backend_dir)."""
    if repo_root is not None:
        rr = Path(repo_root)
    elif worktree_path is not None:
        from workspace import resolve_caller_root
        rr = resolve_caller_root(worktree_path)
    else:
        from settings import REPO_ROOT
        rr = REPO_ROOT
    pk = Path(packages_dir) if packages_dir else rr / "products" / "agents" / "packages"
    return pk, rr / "products" / "agents" / "backend"


def agent_package_build(
    key: str,
    check: str | None = None,
    write: bool = True,
    worktree_path: str | None = None,
    packages_dir: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Build package ``key``; optionally ``check`` a consumer repo's materialised files (§C5)."""
    if not _SLUG_RE.match(key or ""):
        return {"ok": False, "status": "invalid", "errors": [f"key {key!r} must be kebab-case"]}
    pk_dir, backend = _roots(worktree_path, packages_dir, repo_root)
    root = pk_dir / key
    try:
        result = build_package(root, backend)
    except PackageError as exc:
        return {"ok": False, "status": "invalid", "key": key, "errors": exc.errors}
    except StudioUnavailable as exc:
        return {"ok": False, "status": "studio_unavailable", "key": key, "errors": [str(exc)]}
    out: dict[str, Any] = {
        "ok": True, "status": "built", "key": key, "versao": result.versao, "sha": result.sha,
        "compiled_hash": result.compiled_hash, "tokens_estimados": result.tokens_estimados,
        "importer_validation": result.importer_validation, "warnings": result.warnings,
        "files": sorted(result.claude_files),
    }
    if write:
        out["dist"] = str(root / "dist")
        out["written"] = write_dist(root, result)
    if check is not None:
        repo = Path(check)
        if not repo.is_dir():
            return {**out, "ok": False, "status": "invalid", "errors": [f"check repo not found: {repo}"]}
        chk = check_against_repo(result, repo)
        out["check"] = chk
        out["ok"] = chk["ok"]
        out["status"] = "check_ok" if chk["ok"] else "check_failed"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_package_build` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_package_build",
        description=(
            "Build an Agent Package (products/agents/packages/<key>/, CONTRACT agent-packages §B/§C): strict-validate "
            "package.yaml/sections/skills/knowledge/evals/LEARNINGS (A10: dev-advisor tools ⊆ Read/Grep/Glob), build the "
            "Studio bundle (noctus.agent-bundle/v1 + §C4 keys), compile the prompt with Studio's REAL compile_prompt, "
            "write dist/bundle.json + dist/claude/ (.claude/agents/<key>.md + agents/<key>/...). check=<consumer repo "
            "path> (§C5) additionally diffs the build against that repo's materialised files (ok=false on drift). "
            "Local only, no network. KB § PATTERNS/architect/mcp-first-scripts.md."
        ),
    )
    def _agent_package_build(
        key: str,
        check: str | None = None,
        write: bool = True,
        worktree_path: str | None = None,
    ) -> dict[str, Any]:
        return agent_package_build(key=key, check=check, write=write, worktree_path=worktree_path)
