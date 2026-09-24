"""``noctus.dev.drive_census`` — census + contract answer keys over ``drive_pull`` mirrors, extract-once.

Why this exists: roadmap ``project-history/roadmaps/sw-drive-extraction-2026-09.md`` P1/P2 score the
product's extractors against real deal folders. That needs two things per folder: a CENSUS (which
documents exist, which are missing, which are image-only) and an ANSWER KEY (the values the signed
contract carries, the ground truth every extracted value is checked against).

Three actions, all local and all over the private mirror written by ``noctus.dev.drive_pull``:

- ``extract``: turn every mirrored file into text ONCE and cache it by content sha256 under
  ``private_root()/extractions/``. Free rungs only (``.docx`` paragraphs, the PDF text layer via the
  seed ``classify_pdf_text_layer``). A cached file is never re-read. It is retried only when its
  cached entry is an error; a changed file has a new sha256 and so a new entry. Parser changes
  re-parse the cached TEXT, never the file (owner rule 2026-09-24: one extraction per file).
- ``census``: classify every file by name/path + the cached text-layer verdict, and write a per-folder
  census (doc types present, certidão sets per entity, gaps, permuta/empresa signals).
- ``answer_key``: pick the ground-truth contract (D4Sign-signed PDF > "REV FINAL" .docx > latest
  root revision, never ``ANTIGOS``/``MINUTA`` drafts), parse it into the product's own vocabulary
  (``social_wiring`` column names, ``frases.CERTIDOES`` tipo codes), and write the key. When both the
  D4Sign PDF and a .docx exist, their paragraphs are diffed and the D4Sign wins.

The answer key is CONTRACT TEXT ONLY. A value that exists only on an image-only document would be a
machine reading scored against itself; such values enter only from a human-verified file
(``<numero>-empresas-verificado.json``) or with ``verificado: false``.

LGPD: every output holds real personal data, so it lands only under ``private_root()`` (outside
every git tree) with mode 0600. The tool's RESULT carries counts, coverage and flags only, never a
name, CPF, or value (memory ``feedback_sw_document_read_authorization``).
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

from . import drive_pull as _dp

TOOL_VERSION = "2"
PARSER_VERSION = "1"

_SEED_BACKEND = Path(_dp.REPO_ROOT) / "seed" / "lib" / "backend"


# ─── paths + private writes ───────────────────────────────────────────────


def _dir(*parts: str) -> Path:
    path = _dp.private_root().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _write_private(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


def _mirror_dirs() -> list[Path]:
    root = _dp.private_root() / "drive-mirror"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / "manifest.json").is_file())


def _load_manifest(folder_id: str) -> dict[str, Any]:
    path = _dp.private_root() / "drive-mirror" / folder_id / "manifest.json"
    if not path.is_file():
        raise ValueError(f"no drive_pull mirror for {folder_id}; run noctus.dev.drive_pull action=pull first")
    return json.loads(path.read_text(encoding="utf-8"))


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _fold(s: str) -> str:
    """Upper-case, accent-free — for matching names and labels only, never for stored values."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper()


_FOLDER_RE = re.compile(r"^\s*(\d{2,4})\s*-\s*(?:(\d{2}/\d{2}/\d{4})\s*-\s*)?(.*)$")


def folder_identity(folder_name: str) -> dict[str, Any]:
    """``"<nº> - <dd/mm/aaaa> - <imóvel> - (<corretor>)"`` → numero/data/titulo (date optional)."""
    m = _FOLDER_RE.match(_nfc(folder_name))
    if not m:
        return {"numero": None, "data": None, "titulo": folder_name.strip()}
    return {"numero": m.group(1), "data": _br_date(m.group(2)) if m.group(2) else None, "titulo": m.group(3).strip()}


# ─── extract once ─────────────────────────────────────────────────────────


def _cache_path(sha256: str) -> Path:
    return _dir("extractions") / f"{sha256}.json"


def _read_cache(sha256: str) -> Optional[dict[str, Any]]:
    path = _cache_path(sha256)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pdf_producer(path: Path) -> Optional[str]:
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.stdout.splitlines():
        if line.startswith("Producer:") or line.startswith("Creator:"):
            key, _, val = line.partition(":")
            if key == "Producer":
                return val.strip()
    return None


def _extract_docx(path: Path) -> dict[str, Any]:
    import docx  # python-docx, in the MCP venv

    doc = docx.Document(str(path))
    paras = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            paras.append(" | ".join(c.text for c in row.cells))
    return {"text_source": "docx", "text": "\n".join(paras), "pages": None, "producer": None}


def _extract_pdf(path: Path) -> dict[str, Any]:
    if str(_SEED_BACKEND) not in sys.path:
        sys.path.insert(0, str(_SEED_BACKEND))
    from noctusai_lib.integrations.media import classify_pdf_text_layer

    camada = classify_pdf_text_layer(path.read_bytes())
    if not camada.tooling_available:
        raise RuntimeError("PDF text-layer tooling (PyMuPDF) unavailable in this environment")
    return {
        "text_source": "text_layer" if camada.is_substantive else "image_only",
        "text": camada.text if camada.is_substantive else "",
        "pages": camada.pages,
        "scanned_pages": list(camada.scanned_page_numbers or []),
        "producer": _pdf_producer(path),
    }


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_TENTATIVAS = 3  # same cap as social-wiring's extraction sweep (D3)


def _should_retry(cached: dict[str, Any], retry_errors: bool) -> bool:
    """Extract-once: a cached entry is reused unless it FAILED. A failure retries up to
    MAX_TENTATIVAS; an ``unsupported`` verdict from an older tool version retries once, because
    that verdict was the tool's gap, not the file's (free rungs only, so this costs nothing)."""
    if cached.get("error"):
        return retry_errors and cached.get("tentativas", 1) < MAX_TENTATIVAS
    return cached.get("text_source") == "unsupported" and cached.get("tool_version") != TOOL_VERSION


def extract_file(entry: dict[str, Any], *, retry_errors: bool = True) -> tuple[dict[str, Any], str]:
    """Return ``(cache_entry, outcome)``; outcome ∈ cached | extracted | retried | skipped."""
    sha = entry.get("sha256")
    local = entry.get("local_path")
    if not sha or not local:
        return ({"error": "missing sha256/local_path in manifest"}, "skipped")
    cached = _read_cache(sha)
    if cached is not None and not _should_retry(cached, retry_errors):
        return (cached, "cached")
    outcome = "retried" if cached is not None else "extracted"
    path = Path(local)
    name = entry.get("name") or path.name
    lower = name.lower()
    mime = entry.get("mime_type") or ""
    record: dict[str, Any] = {
        "sha256": sha,
        "name": name,
        "mime_type": mime,
        "tool_version": TOOL_VERSION,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "tentativas": (cached or {}).get("tentativas", 0) + 1,
    }
    try:
        # Drive names often lack an extension ("CONTRATO … CASA 16"): the manifest's mime decides.
        if lower.endswith(".docx") or mime == _DOCX_MIME:
            record.update(_extract_docx(path))
        elif lower.endswith(".pdf") or mime == "application/pdf":
            record.update(_extract_pdf(path))
        elif (entry.get("mime_type") or "").startswith("image/"):
            record.update({"text_source": "image_only", "text": "", "pages": 1, "producer": None})
        elif lower.endswith((".txt", ".csv")):
            record.update({"text_source": "plain", "text": path.read_text(encoding="utf-8", errors="replace"),
                           "pages": None, "producer": None})
        else:
            record.update({"text_source": "unsupported", "text": "", "pages": None, "producer": None})
    except Exception as exc:  # noqa: BLE001 — recorded per file, surfaced in the result, retried next run
        record.update({"text_source": "error", "text": "", "error": f"{type(exc).__name__}: {exc}"})
    _write_private(_cache_path(sha), record)
    return (record, outcome)


def extract_folder(folder_id: str) -> dict[str, Any]:
    manifest = _load_manifest(folder_id)
    counts: dict[str, int] = {}
    sources: dict[str, int] = {}
    errors = 0
    for e in manifest["entries"]:
        if e.get("is_folder") or e.get("status") == "failed":
            continue
        rec, outcome = extract_file(e)
        counts[outcome] = counts.get(outcome, 0) + 1
        sources[rec.get("text_source") or "?"] = sources.get(rec.get("text_source") or "?", 0) + 1
        errors += 1 if rec.get("error") else 0
    return {"folder_id": folder_id, "outcomes": counts, "text_sources": sources, "errors": errors}


# ─── classify (census) ────────────────────────────────────────────────────

# Certidão folders are numbered "N - TYPE_NAME". N is the Cláusula Terceira PF item (1..12); a PJ set
# keeps the same numbers and skips 9 (Serasa), so 11 items.
CERTIDAO_TIPOS: tuple[str, ...] = (
    "cnd_federal", "trf3_sp", "trf3", "trt2_digital", "trt2_fisico", "cnd_trabalhista_tst",
    "tjsp_esaj", "tjsp_eproc", "serasa", "cenprot", "cnd_fazenda_sp", "divida_ativa_sp",
)
PF_NUMEROS = frozenset(range(1, 13))
PJ_NUMEROS = PF_NUMEROS - {9}

_CERT_FILE_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*")

# (doc_type, regex over the folded file name). First match wins, so specific before generic.
_DOC_RULES: tuple[tuple[str, str], ...] = (
    ("aditivo", r"ADITIV|ADITAMENTO"),
    ("contrato_d4sign", r"D4SIGN|CERTIFICADO DIGITAL"),
    ("autorizacao_reforma", r"AUTORIZA\w* DE REFORMA"),
    ("contrato", r"CONTRATO DE (PROMESSA DE )?(COMPRA|VENDA)|\bCCV\b|INSTRUMENTO PARTICULAR"),
    ("contrato_financiamento", r"CONTRATO DE FINANCIAMENTO|FINANCIAMENTO"),
    ("cartao_cnpj", r"CARTAO\s*(DO\s*)?CNPJ|COMPROVANTE DE INSCRICAO"),
    ("serasa_crednet", r"SERASA|CREDNET"),
    ("matricula", r"MATRICULA"),
    ("cnd_iptu", r"CND.*IPTU|NEGATIVA.*IPTU|DEBITOS? DE IPTU"),
    ("iptu_espelho", r"IPTU|CARNE"),
    ("itbi_comprovante", r"COMPROVANTE.*ITBI"),
    ("itbi_guia", r"ITBI"),
    ("certidao_casamento", r"CASAMENTO"),
    ("certidao_nascimento", r"NASCIMENTO"),
    ("comprovante_endereco", r"COMPROVANTE DE (RESIDENCIA|ENDERECO)|CONTA DE (LUZ|AGUA)"),
    ("identidade", r"\bCNH\b|\bRG\b|\bCIN\b|IDENTIDADE|\bCPF\b"),
    ("banco_dps", r"\bDPS\b"),
    ("banco_proposta", r"PROPOSTA"),
    ("cnd_condominio", r"CONDOMIN"),
    ("certidoes_consolidado", r"^CERTIDOES\b"),
)


def classify_entry(rel_path: str) -> dict[str, Any]:
    """Classify one mirrored file from its relative path. Pure — no file content."""
    parts = [_nfc(p) for p in Path(rel_path).parts]
    name = parts[-1]
    # "_" is a word character, so "CNH_Fulano" would defeat every \b rule: fold it to a space.
    folded_parts = [_fold(p).replace("_", " ") for p in parts]
    out: dict[str, Any] = {"doc_type": "outro", "entity": None, "entity_kind": None, "certidao_n": None,
                           "draft": any(re.search(r"ANTIG|MINUTA", p) for p in folded_parts[:-1])}
    if "CERTIDOES" in folded_parts[:-1]:
        idx = folded_parts.index("CERTIDOES")
        inner = parts[idx + 1:-1]
        if inner:
            entity = inner[0]
            out["entity"] = entity
            out["entity_kind"] = "pj" if re.search(r"\bCNPJ\b|\bLTDA\b|\bME\b|\bEIRELI\b|\bS/?A\b", _fold(entity)) else "pf"
            m = _CERT_FILE_RE.match(name)
            if m:
                out["certidao_n"] = int(m.group(1))
                out["doc_type"] = "serasa_crednet" if out["certidao_n"] == 9 else "certidao"
                return out
    folded = folded_parts[-1]
    for doc_type, pattern in _DOC_RULES:
        if re.search(pattern, folded):
            out["doc_type"] = doc_type
            break
    if out["doc_type"] in ("contrato",) and re.search(r"REV\w* FINAL", folded):
        out["rev_final"] = True
    if re.search(r"^VENDEDOR|VENDEDORA", folded):
        out["lado_hint"] = "vendedor"
    return out


_MANDATORY_ROOT = ("matricula", "iptu_espelho", "cnd_iptu")


def _contract_groups(numero: Optional[str]) -> list[dict[str, Any]]:
    """The certidão groups of this folder's answer key, when one exists and parsed ok."""
    path = _dp.private_root() / "answer-keys" / f"{numero}.json"
    if not numero or not path.is_file():
        return []
    key = json.loads(path.read_text(encoding="utf-8"))
    return ((key.get("certidoes") or {}).get("grupos") or []) if key.get("status") == "ok" else []


def _entity_kind(folder: str, folder_kind: Optional[str], grupos: list[dict[str, Any]]) -> tuple[Optional[str], str]:
    """PF/PJ of a CERTIDÕES entity folder. The contract decides (agreed with 3e): the folder's name
    tokens (minus "CNPJ") must all appear in a certidão group's name. When groups of BOTH kinds match
    (the person and their company share the name), the folder's "CNPJ" suffix picks one. No
    matching group → the folder-name heuristic, recorded as such so it never passes for a document."""
    tokens = set(re.findall(r"[A-Z0-9]+", _fold(folder))) - {"CNPJ"}
    kinds = {"pj" if g["consulta_tipo_documento"] == "cnpj" else "pf" for g in grupos
             if tokens and tokens <= set(re.findall(r"[A-Z0-9]+", _fold(g["em_nome_de"])))}
    if len(kinds) == 1:
        return kinds.pop(), "contrato"
    if kinds:
        return folder_kind, "contrato"  # both kinds exist in the contract; the folder suffix tells which
    return folder_kind, "pasta"


def census_folder(folder_id: str) -> dict[str, Any]:
    manifest = _load_manifest(folder_id)
    ident = folder_identity(manifest.get("folder_name") or "")
    files: list[dict[str, Any]] = []
    entities: dict[str, dict[str, Any]] = {}
    by_type: dict[str, int] = {}
    image_only = text_layer = 0
    permuta_signal = False
    for e in manifest["entries"]:
        if e.get("is_folder"):
            continue
        cls = classify_entry(e["rel_path"])
        cached = _read_cache(e["sha256"]) if e.get("sha256") else None
        src = (cached or {}).get("text_source")
        if src == "image_only":
            image_only += 1
        elif src in ("text_layer", "docx"):
            text_layer += 1
        if re.search(r"PERMUTA", _fold(e["rel_path"])):
            permuta_signal = True
        by_type[cls["doc_type"]] = by_type.get(cls["doc_type"], 0) + 1
        if cls["entity"]:
            ent = entities.setdefault(cls["entity"], {"kind": cls["entity_kind"], "numeros": set(),
                                                     "image_only": 0, "text_layer": 0})
            if cls["certidao_n"]:
                ent["numeros"].add(cls["certidao_n"])
            if src == "image_only":
                ent["image_only"] += 1
            elif src == "text_layer":
                ent["text_layer"] += 1
        files.append({"rel_path": e["rel_path"], "sha256": e.get("sha256"), "size_bytes": e.get("size_bytes"),
                      "text_source": src, "producer": (cached or {}).get("producer"),
                      "extract_error": (cached or {}).get("error"), **cls})
    grupos = _contract_groups(folder_identity(manifest.get("folder_name") or "")["numero"])
    entity_rows = []
    for name, ent in sorted(entities.items()):
        kind, fonte = _entity_kind(name, ent["kind"], grupos)
        expected = PJ_NUMEROS if kind == "pj" else PF_NUMEROS
        entity_rows.append({"entity": name, "kind": kind, "kind_fonte": fonte, "presentes": sorted(ent["numeros"]),
                            "faltando": sorted(expected - ent["numeros"]),
                            "completo": expected <= ent["numeros"],
                            "image_only": ent["image_only"], "text_layer": ent["text_layer"]})
    non_draft = [f for f in files if not f["draft"]]
    has = {t for t in (f["doc_type"] for f in non_draft)}
    root_gaps = [t for t in _MANDATORY_ROOT if t not in has]
    closed = "contrato_d4sign" in has
    census = {
        "folder": {**ident, "drive_folder_id": folder_id},
        "files_total": len(files),
        "doc_types": dict(sorted(by_type.items())),
        "text_layer_files": text_layer,
        "image_only_files": image_only,
        "entities": entity_rows,
        "entities_pf": sum(1 for r in entity_rows if r["kind"] == "pf"),
        "entities_pj": sum(1 for r in entity_rows if r["kind"] == "pj"),
        "cartao_cnpj_files": by_type.get("cartao_cnpj", 0),
        "aditivo_files": by_type.get("aditivo", 0),
        "has_contract_d4sign": "contrato_d4sign" in has,
        "has_contract_rev_final": any(f.get("rev_final") for f in non_draft),
        "has_contract_docx": any(f["doc_type"] == "contrato" and _is_docx(f) for f in non_draft),
        "closed": closed,
        "permuta_signal": permuta_signal,
        "root_gaps": root_gaps,
        "files": files,
    }
    return census


def _redacted_census(c: dict[str, Any]) -> dict[str, Any]:
    """The part of a census that may leave private disk: counts and flags, no names."""
    return {
        "numero": c["folder"]["numero"],
        "files": c["files_total"],
        "entities_pf": c["entities_pf"],
        "entities_pj": c["entities_pj"],
        "certidao_sets_complete": sum(1 for r in c["entities"] if r["completo"]),
        "certidao_sets": len(c["entities"]),
        "cartao_cnpj_files": c["cartao_cnpj_files"],
        "aditivo_files": c["aditivo_files"],
        "image_only_files": c["image_only_files"],
        "text_layer_files": c["text_layer_files"],
        "closed_d4sign": c["closed"],
        "rev_final": c["has_contract_rev_final"],
        "contract_docx": c["has_contract_docx"],
        "permuta_signal": c["permuta_signal"],
        "root_gaps": c["root_gaps"],
    }


# ─── contract → paragraphs ────────────────────────────────────────────────


def paragraphs_from_text(text: str, *, source: str) -> list[str]:
    """Normalize a contract's text into logical paragraphs.

    A .docx already has one paragraph per line. A PDF text layer wraps lines, so paragraphs are
    separated by blank lines and inner lines are joined."""
    text = _nfc(text).replace(" ", " ").replace("\t", " ")
    text = re.sub(r"[​‌‍﻿]", "", text)
    if source == "docx":
        paras = text.split("\n")
    else:
        paras = []
        for block in re.split(r"\n\s*\n", _strip_pdf_furniture(text)):
            current: list[str] = []
            for ln in block.splitlines():
                if current and _STRUCTURAL_START.match(ln):
                    paras.append(" ".join(current))
                    current = []
                current.append(ln.strip())
            if current:
                paras.append(" ".join(current))
    return [re.sub(r"\s{2,}", " ", p).strip() for p in paras if p.strip()]


# A PDF text layer keeps list items inside one blank-line block; these line starts open a paragraph.
_STRUCTURAL_START = re.compile(
    r"^\s*(?:CL[ÁA]USULA\b|\d+\.\d+\s*[–\-—]|\d+\s*[–\-—]\s*Em\s|\d+\)\s|Parcela\s*\d+|Par[áa]grafo\b|"
    r"[a-z]\s*-?\)\s|E de outro lado|Pelo presente|Com fundamento|IM[ÓO]VEL\s*:|TESTEMUNHAS|"
    r"(?:VENDEDORA?S?|COMPRADORA?S?)\s*$)")

_D4SIGN_FURNITURE = (
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),                                  # page counter "1/7"
    re.compile(r"^\s*D4Sign\s+[0-9a-f]{8}-[0-9a-f\-]{27}", re.I),           # per-page signature notice
    re.compile(r"^\s*Documento assinado eletronicamente", re.I),
)
# The signature-certificate pages D4Sign appends; three header variants seen across deal folders.
_D4SIGN_CERT_START = re.compile(
    r"^\s*(?:Documento\s+[0-9a-f]{8}-[0-9a-f\-]{27}\s+criado por|\d+\s+p[áa]ginas\s+-\s+Datas e hor[áa]rios|"
    r".*C[óo]digo do documento\s+[0-9a-f]{8}-)", re.I)


def _strip_pdf_furniture(text: str) -> str:
    """Drop D4Sign page furniture (counter, running title, signature notice) and the trailing
    signature-certificate pages, which would otherwise glue onto the next paragraph."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if _D4SIGN_CERT_START.match(ln):
            lines = lines[:i]
            break
    counts: dict[str, int] = {}
    for ln in lines:
        s = ln.strip()
        if len(s) > 30:
            counts[s] = counts.get(s, 0) + 1
    running = {s for s, n in counts.items() if n >= 3}  # a running page title repeats on every page
    kept = [ln for ln in lines if ln.strip() not in running and not any(r.match(ln) for r in _D4SIGN_FURNITURE)]
    return "\n".join(kept)


def _is_docx(f: dict[str, Any]) -> bool:
    return f["rel_path"].lower().endswith(".docx") or f.get("text_source") == "docx"


def select_contract(files: Iterable[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], str, list[dict[str, Any]]]:
    """Ground-truth rule (agreed with noctusai-3e, 2026-09-24):
    d4sign > rev_final > latest revision .docx at root (never ANTIGOS/MINUTA) > none.
    Returns (chosen_file, fonte, other_contract_docx)."""
    cands = [f for f in files if not f["draft"] and f["doc_type"] in ("contrato", "contrato_d4sign")]
    d4 = [f for f in cands if f["doc_type"] == "contrato_d4sign" and f.get("text_source") == "text_layer"]
    docx_files = [f for f in cands if f["doc_type"] == "contrato" and _is_docx(f)
                  and len(Path(f["rel_path"]).parts) == 1]
    if d4:
        return (d4[0], "d4sign", docx_files)
    rev = [f for f in docx_files if f.get("rev_final")]
    if rev:
        return (rev[0], "rev_final", [f for f in docx_files if f is not rev[0]])
    if docx_files:
        latest = max(docx_files, key=lambda f: (_revision_date(f["rel_path"]) or date.min, f["rel_path"]))
        return (latest, "revisao", [f for f in docx_files if f is not latest])
    return (None, "none", [])


def _revision_date(name: str) -> Optional[date]:
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", Path(name).stem)
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), m.group(3)
    year = int(y) + (2000 if y and len(y) == 2 else 0) if y else date.today().year
    try:
        return date(year, mth, d)
    except ValueError:
        return None


_SIGNING_DATE_RE = re.compile(r"^[A-ZÀ-Ý][A-Za-zÀ-ÿ' ]+?(?:\s*[/\-–]\s*[A-Z]{2})?,\s*\d{1,2}\s+de\s+[A-Za-zçÇ]+\s+de\s+\d{4}\.?$")


def _until_signing_date(paras: list[str]) -> list[str]:
    for i, p in enumerate(paras):
        if _SIGNING_DATE_RE.match(p):
            return paras[: i + 1]
    return paras


def diff_paragraphs(a: list[str], b: list[str], *, limit: int = 40) -> list[dict[str, Any]]:
    """WORD-level divergences between the .docx (a) and the signed D4Sign text (b).

    Paragraph boundaries are not content: a .docx may put "Parcela 01 —" and its value in two
    paragraphs, and a PDF page break splits one. So both sides are flattened to words and diffed,
    and each divergence is reported with a few words of context. Both sides stop at the signing-date
    line (the signature block is layout), and .docx auto-numbering ("1) ", PDF only) is dropped."""
    def words(paras: list[str]) -> tuple[list[str], list[str]]:
        joined = " ".join(re.sub(r"^\d+\)\s*", "", p) for p in _until_signing_date(paras))
        joined = re.sub(r"(\w)-\s+(\w)", r"\1-\2", joined)  # a PDF line break inside "06706-165"
        raw = [w for w in joined.split()
               if not re.fullmatch(r"[a-z0-9]{1,2}\)", w)]  # auto-list markers "a)" "1)" (PDF-only)
        return raw, [_fold(w).strip(".,;:–—-\"“”'") for w in raw]

    ra, na = words(a)
    rb, nb = words(b)
    out: list[dict[str, Any]] = []
    ctx = 6
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=na, b=nb, autojunk=False).get_opcodes():
        if tag == "equal" or (not "".join(na[i1:i2]) and not "".join(nb[j1:j2])):
            continue
        out.append({"docx": " ".join(ra[i1:i2]) or None, "d4sign": " ".join(rb[j1:j2]) or None,
                    "contexto": " ".join(ra[max(0, i1 - ctx):i1]) + " … " + " ".join(ra[i2:i2 + ctx])})
        if len(out) >= limit:
            break
    return out


# ─── contract parsing ─────────────────────────────────────────────────────

_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
          "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def _br_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def _money(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        return str(Decimal(s.replace(".", "").replace(",", ".")))
    except InvalidOperation:
        return None


def _digits(s: Optional[str]) -> Optional[str]:
    return re.sub(r"\D", "", s) if s else None


_CLAUSE_RE = re.compile(r"^CL[ÁA]USULA\s+([A-ZÀ-Ý ]+?)\s*[–\-—]\s*(.+)$")


def split_clauses(paras: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    preamble: list[str] = []
    clauses: list[dict[str, Any]] = []
    for p in paras:
        m = _CLAUSE_RE.match(p)
        if m:
            clauses.append({"ordinal": m.group(1).strip(), "titulo": m.group(2).strip(), "paras": []})
        elif clauses:
            clauses[-1]["paras"].append(p)
        else:
            preamble.append(p)
    return preamble, clauses


def _clause(clauses: list[dict[str, Any]], *keywords: str) -> Optional[dict[str, Any]]:
    for c in clauses:
        t = _fold(c["titulo"])
        if any(k in t for k in keywords):
            return c
    return None


# Persons: an upper-case name followed by ", <nacionalidade>," — the qualification opener.
_PERSON_RE = re.compile(r"([A-ZÀ-Ý][A-ZÀ-Ý'’´`.\- ]{3,}[A-ZÀ-Ý]),\s+(brasileir[oa]s?|[a-zà-ÿ]+(?:ian[oa]|[eê]s[a]?|n[oa]))\s*,")
_ESTADO_RE = re.compile(r"\b(solteir[oa]s?|casad[oa]s?|divorciad[oa]s?|vi[úu]v[oa]s?|separad[oa]s? judicialmente|"
                        r"conviventes? em uni[ãa]o est[áa]vel|em uni[ãa]o est[áa]vel)\b", re.I)
_REGIME_RE = re.compile(r"regime d[ae]\s+(comunh[ãa]o parcial|comunh[ãa]o universal|separa[çc][ãa]o total|"
                        r"separa[çc][ãa]o obrigat[óo]ria|separa[çc][ãa]o (?:convencional )?de bens|participa[çc][ãa]o final)", re.I)
_RG_RE = re.compile(r"\bRG\s*:?\s*(?:n[º°o.]?\s*)?:?\s*([0-9Xx](?:[0-9Xx.]|-\s?(?=[0-9Xx]))*[0-9Xx])\s*"
                    r"(?:[\-–/ ]+\s*([A-Z]{2,}(?:\s?[\-/]\s?[A-Z]{2})?))?(?=[\s,;.]|$)")
_CPF_RE = re.compile(r"CPF(?:/MF)?\s*(?:sob\s+(?:o\s+)?)?(?:n[º°o.]?\s*)?[:\s]*(\d{3}\.?\d{3}\.?\d{3}\s*-?\s*\d{2})")
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_CEP_RE = re.compile(r"CEP[:\s]*(?:n[º°o.]?\s*)?(\d{2}\.?\d{3}\s*-?\s*\d{3})", re.I)
_ENDERECO_RE = re.compile(r"residentes?\s+e\s+domiciliad[oa]s?\s+(?:na|no|à|a|em)\s+(.+?)(?:;|$)", re.I)
_DATA_CASAMENTO_RE = re.compile(r"casad[oa]s?.{0,120}?(?:em|desde)\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)


def _regime_code(s: str) -> Optional[str]:
    f = _fold(s)
    if "PARCIAL" in f:
        return "comunhao_parcial"
    if "UNIVERSAL" in f:
        return "comunhao_universal"
    if "OBRIGATORIA" in f:
        return "separacao_obrigatoria"
    if "SEPARACAO" in f:
        return "separacao_total"
    if "PARTICIPACAO" in f:
        return "participacao_final_aquestos"
    return None


def _estado_code(s: str) -> str:
    f = _fold(s)
    if "UNIAO" in f:
        return "uniao_estavel"
    if f.startswith("CASAD"):
        return "casado"
    if f.startswith("SOLTEIR"):
        return "solteiro"
    if f.startswith("DIVORCIAD"):
        return "divorciado"
    if f.startswith("VIUV"):
        return "viuvo"
    return "separado_judicialmente"


def _split_endereco(texto: str) -> dict[str, Optional[str]]:
    out: dict[str, Optional[str]] = {k: None for k in ("endereco_logradouro", "endereco_numero",
                                                       "endereco_complemento", "endereco_bairro",
                                                       "endereco_cidade", "endereco_uf", "endereco_cep")}
    cep = _CEP_RE.search(texto)
    if cep:
        out["endereco_cep"] = _digits(cep.group(1))
    cidade_uf = re.search(r"(?:,|–|-)\s*([A-Za-zÀ-ÿ' ]{3,}?)\s*[/\-–]\s*(SP|RJ|MG|PR|SC|RS|BA|GO|DF|ES|MS|MT|PE|CE|PA|AM|MA|PB|RN|AL|SE|PI|TO|RO|AC|AP|RR)\b", texto)
    if cidade_uf:
        out["endereco_cidade"] = cidade_uf.group(1).strip()
        out["endereco_uf"] = cidade_uf.group(2)
    num = re.match(r"(.+?),?\s*(?:n[º°o.]\s*)?(\d+[A-Za-z]?|s/n)\b(.*)$", texto)
    if num:
        out["endereco_logradouro"] = num.group(1).strip(" ,")
        out["endereco_numero"] = num.group(2)
    return out


def parse_person(chunk: str) -> dict[str, Any]:
    m = _PERSON_RE.match(chunk)
    nome = m.group(1).strip() if m else None
    nac = m.group(2) if m else None
    genero = None
    if nac:
        genero = "Feminino" if re.search(r"a(s)?$", nac) else "Masculino"
    estado = _ESTADO_RE.search(chunk)
    regime = _REGIME_RE.search(chunk)
    rg = _RG_RE.search(chunk)
    cpf = _CPF_RE.search(chunk)
    email = _EMAIL_RE.search(chunk)
    endereco = _ENDERECO_RE.search(chunk)
    casamento = _DATA_CASAMENTO_RE.search(chunk)
    profissao = None
    if estado:
        after = chunk[estado.end():]
        pm = re.match(r"\s*,\s*([a-zà-ÿ][a-zà-ÿ ()/\-]{2,40}?)\s*,\s*(?:portador|inscrit|residente|com endere)", after)
        if pm and not _REGIME_RE.search(pm.group(1)):
            profissao = pm.group(1).strip()
    clientes = {
        "nome_oficial": nome,
        "nacionalidade": nac.lower() if nac else None,
        "genero": genero,
        "estado_civil": _estado_code(estado.group(1)) if estado else None,
        "regime_bens": _regime_code(regime.group(0)) if regime else None,
        "data_casamento": _br_date(casamento.group(1)) if casamento else None,
        "profissao": profissao,
        "rg": re.sub(r"\s", "", rg.group(1)) if rg else None,
        "rg_orgao_expedidor": rg.group(2) if rg and rg.group(2) else None,
        "cpf": _digits(cpf.group(1)) if cpf else None,
        "email": email.group(0).lower() if email else None,
    }
    if endereco:
        clientes.update(_split_endereco(endereco.group(1)))
    return {"clientes": clientes, "texto_qualificacao": chunk}


def split_persons(paragraph: str) -> list[str]:
    starts = [m.start() for m in _PERSON_RE.finditer(paragraph)]
    return [paragraph[s:e].strip(" ,;") for s, e in zip(starts, starts[1:] + [len(paragraph)])]


def parse_partes(preamble: list[str]) -> list[dict[str, Any]]:
    partes: list[dict[str, Any]] = []
    lado = None
    for p in preamble:
        f = _fold(p)
        if "DE UM LADO" in f:
            lado = "vendedor"
        elif "DE OUTRO LADO" in f:
            lado = "comprador"
        elif not lado:
            continue
        body = re.split(r"de um lado,|de outro lado,", p, flags=re.I)[-1]
        chunks = split_persons(body)
        first_idx = len(partes)
        for chunk in chunks:
            person = parse_person(chunk)
            papel = "proprietario" if lado == "vendedor" else "comprador"
            partes.append({"lado": lado, "papel": papel, "conjuge_de": None, **person,
                           "verificado": True, "verificado_por": "contrato"})
        # Spouses: two casados on the same side declared "casados entre si" (or sharing one regime
        # sentence) are linked; the product keeps both as signatories, so papel stays per side.
        # "residentes e domiciliados na …" after the LAST person is the shared address of the side.
        if len(partes) > first_idx and re.search(r"residentes\s+e\s+domiciliad[oa]s", p, re.I):
            shared = {k: v for k, v in partes[-1]["clientes"].items() if k.startswith("endereco_")}
            for i in range(first_idx, len(partes)):
                for k, v in shared.items():
                    partes[i]["clientes"].setdefault(k, v)
        _link_couples(partes, first_idx)
    return partes


# How a contract joins two spouses: "X …, casado … com Y …" or "X …, e sua esposa Y …, casados …".
_COUPLE_JOIN_RE = re.compile(r"(?:\bcom|\be\s+(?:sua|seu)\s+(?:esposa|marido|mulher|esposo|c[ôo]njuge)|\be)\s*$", re.I)


def _link_couples(partes: list[dict[str, Any]], first_idx: int) -> None:
    """Spouses are qualified as a PAIR, and the marital status and regime are printed once for both:
    after the first ("casado … com Y") or after the second ("X …, e Y …, casados no regime …").

    Consecutive persons a, b on one side are a couple when a's chunk ends with a join ("com",
    "e sua esposa", a bare "e") AND one of the two reads casado/união estável. Both then get that
    estado civil + regime and are linked through ``conjuge_de``. A pair where neither says casado
    stays unlinked (two co-buyers are not assumed to be married)."""
    i = first_idx
    while i + 1 < len(partes):
        a, b = partes[i], partes[i + 1]
        ca, cb = a["clientes"], b["clientes"]
        estados = {ca["estado_civil"], cb["estado_civil"]} & {"casado", "uniao_estavel"}
        joined = _COUPLE_JOIN_RE.search(a["texto_qualificacao"]) is not None
        if joined and estados and not ({ca["estado_civil"], cb["estado_civil"]} - estados - {None}):
            estado = estados.pop()
            regime = ca["regime_bens"] or cb["regime_bens"]
            casamento = ca["data_casamento"] or cb["data_casamento"]
            for c in (ca, cb):
                c["estado_civil"] = c["estado_civil"] or estado
                c["regime_bens"] = c["regime_bens"] or regime
                c["data_casamento"] = c["data_casamento"] or casamento
            a["conjuge_de"], b["conjuge_de"] = i + 1, i
            i += 2
        else:
            i += 1


def parse_imovel(clause: Optional[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"imovel_dados": {"numero_matricula": None, "numero_registro_imoveis": None,
                                            "prefeitura_cadastro_imobiliario": None,
                                            "titulo_aquisitivo_texto": None},
                           "descricao_matricula_texto": None, "verificado": True, "verificado_por": "contrato"}
    if not clause:
        return out
    text = " ".join(clause["paras"])
    for p in clause["paras"]:
        if re.match(r"^IM[ÓO]VEL\s*:", p, re.I):
            out["descricao_matricula_texto"] = p
        if re.search(r"propriet[áa]ri[oa]s?", p, re.I) and re.search(r"escritura|formal de partilha|registr", p, re.I) \
                and not out["imovel_dados"]["titulo_aquisitivo_texto"]:
            out["imovel_dados"]["titulo_aquisitivo_texto"] = p
    mat = re.search(r"matr[íi]cula\s*(?:sob\s*o\s*)?(?:n[º°o.]?\s*)?[:\s]*([\d.]{2,})", text, re.I)
    if mat:
        out["imovel_dados"]["numero_matricula"] = _digits(mat.group(1))
    cart = re.search(r"(\d+\s*[º°ª]?\s*(?:Oficial|Cart[óo]rio)?\s*(?:de\s+)?Registro de Im[óo]veis[^,.;]*|"
                     r"(?:Oficial|Cart[óo]rio) de Registro de Im[óo]veis[^,.;]*)", text, re.I)
    if cart:
        out["imovel_dados"]["numero_registro_imoveis"] = re.sub(r"\s+", " ", cart.group(1)).strip()
    insc = re.search(r"(?:inscri[çc][ãa]o|cadastr(?:o|ado))\s+(?:imobili[áa]ri[oa]|municipal|na prefeitura)"
                     r"[^0-9]{0,40}([0-9][0-9.\-/ ]{4,}[0-9])", text, re.I)
    insc = insc or re.search(r"cadastrad[oa]\s+(?:pela|na)\s+Prefeitura[^;]{0,60}?sob\s*(?:o\s*)?(?:n[º°o.]?\s*)?([0-9][0-9.\-/]{4,}[0-9])", text, re.I) \
        or re.search(r"(?:contribuinte|inscri[çc][ãa]o\s+municipal)\s*(?:n[º°o.]?\s*)?[:\s]*([0-9][0-9.\-/]{4,}[0-9])", text, re.I)
    if insc:
        out["imovel_dados"]["prefeitura_cadastro_imobiliario"] = insc.group(1).strip()
    return out


_PARCELA_RE = re.compile(r"^(?:[a-z]\)\s*)?Parcela\s*(\d+)\s*[:\-–—]\s*(.+)$", re.I)
_BRL_RE = re.compile(r"R\$\s*([\d.]+,\d{2})")


def _parcela_tipo(texto: str) -> str:
    f = _fold(texto)
    if "PERMUTA" in f:
        return "permuta"
    if "FGTS" in f:
        return "fgts"
    if "SINAL" in f:
        return "sinal"
    if re.search(r"(RECURSOS|POR MEIO) DE FINANCIAMENTO|FINANCIAMENTO (BANCARIO|IMOBILIARIO) (A SER|QUE SERA)", f):
        return "financiamento"
    if "SALDO" in f:
        return "saldo"
    return "intermediaria"


def parse_negociacao(clause: Optional[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"valor_negociado": None, "ad_corpus": None, "tem_permuta": False,
                           "parcelas": [], "favorecidos": [], "verificado": True, "verificado_por": "contrato"}
    if not clause:
        return out
    text = " ".join(clause["paras"])
    preco = re.search(r"pre[çc]o.{0,80}?R\$\s*([\d.]+,\d{2})", text, re.I)
    if preco:
        out["valor_negociado"] = _money(preco.group(1))
    out["ad_corpus"] = bool(re.search(r"ad\s+corpus", text, re.I))
    out["tem_permuta"] = bool(re.search(r"permuta", text, re.I))
    for p in clause["paras"]:
        m = _PARCELA_RE.match(p)
        if not m:
            continue
        valor = _BRL_RE.search(m.group(2))
        out["parcelas"].append({"ordem": int(m.group(1)), "tipo": _parcela_tipo(m.group(2)),
                                "valor": _money(valor.group(1)) if valor else None, "texto": p})
        fav = re.search(r"em favor d[aoe]s?\s+(?:[A-Z]+\s*:\s*)?([A-ZÀ-Ý][A-ZÀ-Ý .'\-]{3,}?)\s*,\s*(CPF|CNPJ)[:\s]*(?:n[º°o.]?\s*)?([\d./\-]+)"
                        r"(?:.*?Banco\s+([^,(]+?)\s*(?:\((\d{3,4})\))?\s*,\s*Ag[êe]ncia\s*(?:n[º°o.]?\s*)?([\d\-]+)\s*,\s*Conta(?:\s+Corrente)?\s*(?:n[º°o.]?\s*)?([\dXx.\-]*[\dXx]))?", p)
        if fav:
            doc = _digits(fav.group(3))
            if not any(x["cpf_cnpj"] == doc for x in out["favorecidos"]):
                out["favorecidos"].append({"nome": fav.group(1).strip(), "cpf_cnpj": doc,
                                           "banco": (fav.group(4) or "").strip() or None,
                                           "agencia": fav.group(6), "conta": fav.group(7), "pix": None})
    return out


# Cláusula Terceira item → frases.CERTIDOES tipo (checked in this order; specific first).
_ITEM_TIPO_RULES: tuple[tuple[str, str], ...] = (
    ("E-SAJ", "tjsp_esaj"), ("ESAJ", "tjsp_esaj"), ("E-PROC", "tjsp_eproc"), ("EPROC", "tjsp_eproc"),
    ("TRIBUTOS FEDERAIS", "cnd_federal"), ("1A INSTANCIA", "trf3_sp"), ("2A INSTANCIA", "trf3"),
    ("PROCESSOS DIGITAIS", "trt2_digital"), ("PROCESSOS FISICOS", "trt2_fisico"),
    ("DEBITOS TRABALHISTAS", "cnd_trabalhista_tst"), ("SERASA", "serasa"), ("CENPROT", "cenprot"),
    ("NAO INSCRITOS", "cnd_fazenda_sp"), ("DIVIDA ATIVA DO ESTADO", "divida_ativa_sp"),
    # older template: the TJSP distribuidor without E-SAJ/E-PROC is the registry's generic `tjsp`
    ("DISTRIBUIDOR CIVEL", "tjsp"),
)


def _item_tipo(texto: str) -> Optional[str]:
    f = _fold(texto).replace("ª", "A").replace("º", "O")
    f = re.sub(r"(\d)\s*[ªA]\s*INST", r"\1A INST", f)
    for needle, tipo in _ITEM_TIPO_RULES:
        if needle in f:
            return tipo
    return None


def _item_resultado(texto: str) -> Optional[str]:
    f = _fold(texto)
    if "PENDENTE" in f:
        return "nao_emitida"
    if "POSITIVA COM EFEITO" in f:
        return "positiva_com_efeito_de_negativa"
    if "HOMONIMO" in f:
        return "negativa_com_homonimos"
    if re.search(r"\bPOSITIVA\b", f):
        return "positiva"
    if re.search(r"\bNEGATIVA\b|NADA CONSTA", f):
        return "negativa"
    return None


_GROUP_RE = re.compile(r"^(\d+)\s*[–\-—]\s*Em nome d[eao]\s+(.+)$", re.I)
_IMOVEL_GROUP_RE = re.compile(r"^(\d+)\s*[–\-—]\s*Em rela[çc][ãa]o ao im[óo]vel", re.I)
_ITEM_RE = re.compile(r"^(\d+)\.(\d+)\s*[–\-—]?\s*(.+)$")
_NUMERO_RE = re.compile(r"(?:protocolo\s+)?n[º°o]\.?\s*[:.]?\s*(.+?)\s*[–\-—,]*\s*(?:emitid[ao]|expedid[ao])", re.I)
_EMITIDA_RE = re.compile(r"(?:emitid[ao]|expedid[ao])\s+em\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)
_CNPJ_DIGITS_RE = re.compile(r"\b(\d{2}\.\d{3}\.\d{3}(?:/\d{4}-\d{2})?)\b")


def parse_certidoes(clause: Optional[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"grupos": [], "grupos_imovel": [], "pendencias": [], "outros_itens": [],
                           "verificado": True, "verificado_por": "contrato"}
    if not clause:
        return out
    current: Optional[dict[str, Any]] = None
    in_imovel = False
    for p in clause["paras"]:
        g = _GROUP_RE.match(p)
        if g:
            header = g.group(2).strip()
            parts = re.split(r"\s+[–\-—]\s+", header, maxsplit=1)
            nome, sufixo = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else None)
            doc = _CNPJ_DIGITS_RE.search(nome)
            is_pj = bool(doc) or bool(sufixo and re.search(r"EMPRESA|BAIXAD|LTDA|ATIVA", _fold(sufixo)))
            current = {"ordem": int(g.group(1)), "em_nome_de": nome, "sufixo": sufixo,
                       "consulta_tipo_documento": "cnpj" if is_pj else "cpf",
                       "documento": _digits(doc.group(1)) if doc else None, "itens": []}
            out["grupos"].append(current)
            in_imovel = False
            continue
        if _IMOVEL_GROUP_RE.match(p):
            current, in_imovel = None, True
            continue
        item = _ITEM_RE.match(p)
        if item:
            texto = item.group(3)
            numero = _NUMERO_RE.search(texto)
            emitida = _EMITIDA_RE.search(texto)
            if in_imovel:
                f = _fold(texto)
                tipo = "matricula" if "MATRICULA" in f else "cnd_iptu" if "IPTU" in f else \
                    "cnd_condominio" if "CONDOMIN" in f else None
                row = {"item": f"{item.group(1)}.{item.group(2)}", "tipo": tipo,
                       "numero": numero.group(1).strip() if numero else None,
                       "emitida_em": _br_date(emitida.group(1)) if emitida else None, "texto": p}
                (out["grupos_imovel"] if tipo else out["outros_itens"]).append(row)
                continue
            if current is None:
                out["outros_itens"].append({"item": f"{item.group(1)}.{item.group(2)}", "texto": p})
                continue
            tipo = _item_tipo(texto)
            sistema = "E-SAJ" if tipo == "tjsp_esaj" else "E-PROC" if tipo == "tjsp_eproc" else None
            row: dict[str, Any] = {
                "item": f"{item.group(1)}.{item.group(2)}",
                "pasta_n": CERTIDAO_TIPOS.index(tipo) + 1 if tipo in CERTIDAO_TIPOS else 7 if tipo == "tjsp" else None,
                "tipo": tipo,
                "resultado": _item_resultado(texto),
                "numero": numero.group(1).strip(" –-") if numero else None,
                "emitida_em": _br_date(emitida.group(1)) if emitida else None,
                "sistema": sistema,
                "texto": p,
            }
            f = _fold(texto)
            if "BAIXA DO CNPJ" in f:
                # Owner ruling 2026-09-24: not a product type; the Cartão CNPJ covers it.
                row.update({"tipo": None, "pasta_n": None, "resultado": None, "ignorado": "baixa_cnpj_coberta_pelo_cartao"})
            elif tipo == "tjsp":
                # Owner ruling 2026-09-24: never the generic code. Resolved to tjsp_esaj / tjsp_eproc from
                # the folder's numbered certidão files in answer_key_folder (_resolve_tjsp); until then
                # (and when undecidable) it is ambiguous and out of scoring.
                row.update({"tipo": None, "pasta_n": None, "sistema": None, "ambiguo": "tjsp_sem_sistema"})
            elif "CRIMINAL" in f:
                # Owner ruling 2026-09-24: added by the client's lawyer; not ours, never scored.
                row.update({"tipo": None, "pasta_n": None, "resultado": None, "ignorado": "criminal_advogado_cliente"})
            elif "RELATORIO FISCAL" in f:
                # Owner ruling 2026-09-24: required when the entity's RF certidão is not clean; it takes
                # the RF slot (item/pasta 1). rf_resultado is filled per group below, to validate the rule.
                row.update({"tipo": "relatorio_fiscal", "pasta_n": 1, "resultado": None,
                            "condicao": "rf_resultado_diferente_de_negativa"})
            current["itens"].append(row)
            continue
        pend = re.match(r"^([a-z])\s*-?\)\s*(.+)$", p)
        if pend:
            out["pendencias"].append(pend.group(2).strip())
    for grp in out["grupos"]:
        scored = [i for i in grp["itens"] if not i.get("ignorado")]
        tipos = {i["tipo"] for i in scored}
        # A PJ set never carries Serasa (E5): 11 scored items and no serasa is the PJ signature.
        if grp["consulta_tipo_documento"] == "cpf" and (
                re.search(r"\b(LTDA|EIRELI|S/?A|ME|EPP|MEI)\b\.?$", _fold(grp["em_nome_de"]))
                or (scored and "serasa" not in tipos and len(scored) == 11)):
            grp["consulta_tipo_documento"] = "cnpj"
        # Owner ruling (2026-09-24, final): a Relatório Fiscal is due whenever the entity's RF
        # certidão is anything but negativa (PCEN included). It is not a clause of its own: just an
        # item delivered or still to deliver in this section. An RF slot taken by the relatório
        # itself (no RF item printed) means the RF was not clean.
        rf = next((i for i in scored if i["tipo"] == "cnd_federal"), None)
        rel = [i for i in scored if i["tipo"] == "relatorio_fiscal"]
        for i in rel:
            i["rf_presente"] = rf is not None
            i["rf_resultado"] = rf["resultado"] if rf else None
        exigido = (rf is None and bool(rel)) or (rf is not None and rf["resultado"] in (
            "positiva", "positiva_com_efeito_de_negativa", "negativa_com_homonimos"))
        grp["relatorio_fiscal"] = {
            "exigido": exigido,
            "entregue": bool(rel),
            "rf_resultado": rf["resultado"] if rf else None,
            "situacao": "entregue" if rel else ("a_entregar" if exigido else "nao_exigido"),
            # Owner ruling: always required when RF ≠ negativa, but by default NOT written into the
            # contract (888's were the client's lawyer). A historical contract without it is no error.
            "pontuavel": False,
        }
    return out


def parse_intermediacao(clause: Optional[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"corretagem_total": None, "corretagem_contratantes": None,
                           "corretagem_num_parcelas": None, "intermediarios": [],
                           "verificado": True, "verificado_por": "contrato"}
    if not clause:
        return out
    text = " ".join(clause["paras"])
    total = re.search(r"corretagem\s+em\s+R\$\s*([\d.]+,\d{2})", text, re.I)
    if total:
        out["corretagem_total"] = _money(total.group(1))
    n = re.search(r"pag[oa]\s+em\s+(\d+)\s+parcelas|em\s+(\d+)\s+parcelas", text, re.I)
    if n:
        out["corretagem_num_parcelas"] = int(n.group(1) or n.group(2))
    first = _fold(clause["paras"][0]) if clause["paras"] else ""
    if re.search(r"\bVENDEDOR", first) and re.search(r"\bCOMPRADOR", first):
        out["corretagem_contratantes"] = "partes"
    elif re.search(r"\bVENDEDOR", first):
        out["corretagem_contratantes"] = "vendedores"
    elif re.search(r"\bCOMPRADOR", first):
        out["corretagem_contratantes"] = "compradores"
    for p in clause["paras"]:
        m = re.search(r"R\$\s*([\d.]+,\d{2}).*?em favor de\s+([A-ZÀ-Ýa-z][^,]{2,}?)\s*,\s*"
                      r"(?:inscrit[oa] no\s+)?(CPF|CNPJ)[^\d]{0,20}([\d./\-]{11,})", p)
        if m:
            parcela = _money(m.group(1))
            num = out["corretagem_num_parcelas"] or 1
            out["intermediarios"].append({"nome": m.group(2).strip(), "documento": _digits(m.group(4)),
                                          "valor_parcela": parcela,
                                          "valor": str(Decimal(parcela) * num) if parcela else None})
    return out


def parse_assinatura(paras: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"assinatura_data": None, "assinatura_local": None, "foro_comarca": None,
                           "modalidade_assinatura": None}
    text = " ".join(paras)
    foro = re.search(r"foro da Comarca de\s+([A-Za-zÀ-ÿ' ]+?)(?:\s*[/\-–]\s*[A-Z]{2})?\s*[,.;]", text)
    if foro:
        out["foro_comarca"] = foro.group(1).strip()
    for p in paras:
        m = re.match(r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ' ]+?)(?:\s*[/\-–]\s*[A-Z]{2})?,\s*(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})\.?$", p)
        if m and _fold(m.group(3)).lower() in _MESES:
            try:
                out["assinatura_data"] = date(int(m.group(4)), _MESES[_fold(m.group(3)).lower()], int(m.group(2))).isoformat()
                out["assinatura_local"] = m.group(1).strip()
            except ValueError:
                pass
    if re.search(r"D4sign|forma digital|assinatura digital|assinam .{0,40}digital", text, re.I):
        out["modalidade_assinatura"] = "digital"
    elif re.search(r"\bvias\b", text, re.I):
        out["modalidade_assinatura"] = "fisica"
    return out


def parse_testemunhas(paras: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        start = next(i for i, p in enumerate(paras) if _fold(p).startswith("TESTEMUNHAS"))
    except StopIteration:
        return out
    # A .docx has one line per name / RG; a PDF text layer joins them ("NOME e-mail RG 1.2 NOME2 …").
    blob = " ".join(p for p in paras[start + 1:start + 12] if not _fold(p).startswith(("CPF", "D4SIGN")))
    word = r"(?!(?:RG|CPF)\b)[A-ZÀ-Ý][A-ZÀ-Ý.'’\-]+"
    for m in re.finditer(rf"({word}(?:\s+{word}){{1,8}})(?:\s+[\w.+\-]+@[\w.\-]+)?"
                         r"(?:\s+RG[:\s]*(?:n[º°o.]?\s*)?([\dXx][\dXx.\-]*[\dXx]))?", blob):
        nome = m.group(1).strip()
        if len(nome) >= 6 and not re.fullmatch(r"(?:RG|CPF|TESTEMUNHAS?)", nome):
            out.append({"nome": nome, "rg": m.group(2)})
    return out


def parse_contract(paras: list[str]) -> dict[str, Any]:
    preamble, clauses = split_clauses(paras)
    tail = clauses[-1]["paras"] if clauses else []
    return {
        "contrato": {"titulo": preamble[0] if preamble else None, **parse_assinatura(tail + preamble)},
        "partes": parse_partes(preamble),
        "imovel": parse_imovel(_clause(clauses, "OBJETO")),
        "negociacao": parse_negociacao(_clause(clauses, "PRECO", "PAGAMENTO")),
        "certidoes": parse_certidoes(_clause(clauses, "CERTIDO")),
        "intermediacao": parse_intermediacao(_clause(clauses, "INTERMEDIA", "CORRETAGEM")),
        "testemunhas": parse_testemunhas(tail),
        "clausulas": [c["titulo"] for c in clauses],
    }


# ─── answer key ───────────────────────────────────────────────────────────


def _coverage(key: dict[str, Any]) -> dict[str, Any]:
    """Redacted field-fill ratios, so a parser regression is visible without reading the key."""
    partes = key.get("partes") or []
    fields = ("nome_oficial", "cpf", "rg", "estado_civil", "email", "nacionalidade")
    filled = {f: sum(1 for p in partes if p["clientes"].get(f)) for f in fields}
    grupos = (key.get("certidoes") or {}).get("grupos") or []
    itens = [i for g in grupos for i in g["itens"] if not i.get("ignorado") and not i.get("ambiguo")]
    return {
        "partes": len(partes),
        "vendedores": sum(1 for p in partes if p["lado"] == "vendedor"),
        "compradores": sum(1 for p in partes if p["lado"] == "comprador"),
        "partes_campos": filled,
        "certidao_grupos": len(grupos),
        "certidao_grupos_pj": sum(1 for g in grupos if g["consulta_tipo_documento"] == "cnpj"),
        "certidao_itens": len(itens),
        "certidao_itens_sem_tipo": sum(1 for i in itens if not i["tipo"]),
        "certidao_itens_sem_numero": sum(1 for i in itens if not i["numero"] and i["resultado"] != "nao_emitida"
                                         and i["tipo"] != "relatorio_fiscal"),  # printed without a nº
        "certidao_itens_sem_data": sum(1 for i in itens if not i["emitida_em"] and i["resultado"] != "nao_emitida"),
        "certidao_itens_ignorados": sum(1 for g in grupos for i in g["itens"] if i.get("ignorado")),
        "certidao_itens_ambiguos": sum(1 for g in grupos for i in g["itens"] if i.get("ambiguo")),
        "tjsp_resolvidos": sum(1 for g in grupos for i in g["itens"] if i.get("tjsp_resolvido_por")),
        "relatorios_fiscais": sum(1 for i in itens if i["tipo"] == "relatorio_fiscal"),
        "relatorios_fiscais_a_entregar": sum(1 for g in grupos if (g.get("relatorio_fiscal") or {}).get("situacao") == "a_entregar"),
        "imovel_campos": sum(1 for v in ((key.get("imovel") or {}).get("imovel_dados") or {}).values() if v),
        "parcelas": len((key.get("negociacao") or {}).get("parcelas") or []),
        "valor_negociado": bool((key.get("negociacao") or {}).get("valor_negociado")),
        "tem_permuta": bool((key.get("negociacao") or {}).get("tem_permuta")),
        "intermediarios": len((key.get("intermediacao") or {}).get("intermediarios") or []),
        "testemunhas": len(key.get("testemunhas") or []),
        "empresas": len(key.get("empresas") or []),
        "empresas_exigidas": sum(1 for e in key.get("empresas") or [] if e.get("exigida")),
        "empresas_contrato_diverge": sum(1 for e in key.get("empresas") or [] if e.get("contrato_confere") is False),
    }


def _text_for(file_row: dict[str, Any]) -> Optional[dict[str, Any]]:
    return _read_cache(file_row["sha256"]) if file_row.get("sha256") else None


_ORDINAIS = {"PRIMEIRO": 1, "SEGUNDO": 2, "TERCEIRO": 3, "QUARTO": 4, "QUINTO": 5, "SEXTO": 6,
             "SETIMO": 7, "OITAVO": 8, "NONO": 9, "DECIMO": 10}
_ISO_TS_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}")


def d4sign_assinado_em(raw_text: str) -> Optional[str]:
    """The last signature timestamp on D4Sign's certificate pages (ISO ``…T…`` stamps): the date
    the document was fully signed. None for anything that is not a D4Sign certificate."""
    stamps = _ISO_TS_RE.findall(raw_text or "")
    return max(stamps) if stamps else None


# What an aditivo section changes, from its title + body (first match per category; a section may hit several).
_ALTERACAO_CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("parcelas", r"PARCELA"),
    ("preco", r"\bPRECO\b|VALOR TOTAL DA (COMPRA|VENDA)"),
    ("partes", r"QUALIFICA|CESSAO|INCLUSAO D[OA]S? (COMPRADOR|VENDEDOR)|EXCLUSAO D[OA]S?|SUBSTITUICAO D[OA]S? PARTE"),
    ("prazo", r"PRAZO|POSSE|PRORROGA|\bDATA\b"),
    ("certidoes", r"CERTID|DOCUMENTA"),
    ("intermediacao", r"INTERMEDIA|CORRETAGEM|COMISSAO"),
)
_SECAO_RE = re.compile(r"^(\d+)\.\s+((?:[A-ZÀ-Ý0-9ºª°–\-,/]+\s+){1,20}?[A-ZÀ-Ý0-9ºª°]+)(?=\s+[A-ZÀ-Ý]?[a-zà-ÿ]|\s*$)")


_NAO_ALTERACAO_RE = re.compile(r"RATIFICA|DEMAIS|DISPOSI|OBJETO|FORO|ASSINATURA")
_CLAUSULA_REF_RE = re.compile(r"CLAUSULA\s+((?:DECIMA\s+)?(?:PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA|QUINTA|SEXTA|SETIMA|OITAVA|NONA|DECIMA)|\d+\s*[AO]?)")


def _aditivo_secoes(paras: list[str]) -> list[dict[str, Any]]:
    """Both aditivo shapes seen in deal folders: CLÁUSULA-headed sections (the aditivo's own
    clauses) and numbered sections ("1. DA ALTERAÇÃO DA PARCELA 02 DA CLÁUSULA SEGUNDA …")."""
    _, clauses = split_clauses(paras)
    if clauses:
        return [{"secao": i + 1, "titulo": c["titulo"], "texto": "\n".join(c["paras"]), "estilo": "clausula"}
                for i, c in enumerate(clauses)]
    secoes: list[dict[str, Any]] = []
    for p in paras[1:]:
        m = _SECAO_RE.match(p)
        if m:
            secoes.append({"secao": int(m.group(1)), "titulo": m.group(2).strip(), "texto": p, "estilo": "numerada"})
        elif secoes and not re.match(r"^(VENDEDORA?S?|COMPRADORA?S?|ANUENTE|TESTEMUNHAS)\b", _fold(p)):
            secoes[-1]["texto"] += "\n" + p
    return secoes


def _date_extenso(m: Optional[re.Match]) -> Optional[str]:
    if not m or _fold(m.group(2)).lower() not in _MESES:
        return None
    try:
        return date(int(m.group(3)), _MESES[_fold(m.group(2)).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def is_contract_aditivo(titulo: str) -> bool:
    """Only an aditivo to the deal's promessa de compra e venda belongs in the key; deal folders
    also hold aditivos to unrelated instruments (a debt settlement, a services contract)."""
    return bool(re.search(r"(PROMESSA DE )?(VENDA E COMPRA|COMPRA E VENDA)", _fold(titulo)))


def parse_aditivo(paras: list[str], *, raw_text: str, arquivo: str, fonte: str) -> dict[str, Any]:
    """An aditivo: ordinal, the contract it amends (date), when it was signed, and per section what
    it changes: categories (from the section TITLE; the body only when the title says nothing),
    the ORIGINAL contract clause it names, and the section's own text."""
    titulo = next((p for p in paras if re.search(r"ADITIVO|ADITAMENTO", _fold(p))), paras[0] if paras else "")
    ordm = re.match(r"^\s*(\w+)\s+(?:TERMO\s+)?(?:ADITIVO|ADITAMENTO)", _fold(titulo))
    text = " ".join(paras)
    original = re.search(r"(?:firmad[oa]|assinad[oa](?:\s+entre\s+as\s+Partes)?|celebrad[oa])\s+em\s+"
                         r"(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})", text, re.I)
    alteracoes = []
    for s in _aditivo_secoes(paras):
        ft = _fold(s["titulo"])
        if _NAO_ALTERACAO_RE.search(ft):
            continue  # "the rest stays as is", the aditivo's own object/foro: not a change
        body = _fold(s["texto"][:600])
        cats = [c for c, rx in _ALTERACAO_CATEGORIAS if re.search(rx, ft)] \
            or [c for c, rx in _ALTERACAO_CATEGORIAS if re.search(rx, body)] or ["outro"]
        # numbered style names the original clause in its title; clause style in its body
        ref = _CLAUSULA_REF_RE.search(ft if s["estilo"] == "numerada" else body)
        alteracoes.append({**s, "categorias": cats, "clausula_original": ref.group(1).title() if ref else None})
    return {
        "numero_ordinal": _ORDINAIS.get(ordm.group(1)) if ordm else None,
        "titulo": titulo,
        "contrato_original_data": _date_extenso(original),
        "data": parse_assinatura(paras)["assinatura_data"],
        "assinado_em": d4sign_assinado_em(raw_text) if fonte == "d4sign" else None,
        "arquivo": arquivo,
        "fonte": fonte,
        "confianca": "alta" if fonte == "d4sign" else "media",
        "alteracoes": alteracoes,
        "verificado": True,
        "verificado_por": "contrato",
    }


def _is_aditivo_text(rec: Optional[dict[str, Any]]) -> bool:
    return bool(rec) and bool(re.search(r"ADITIVO|ADITAMENTO", _fold((rec.get("text") or "")[:400])))


def _is_sale_contract(rec: Optional[dict[str, Any]]) -> bool:
    """True unless the file's opening text shows another instrument (a confissão de dívida, a
    services contract…). A file with no text (image-only) cannot be judged and is kept."""
    head = _fold(((rec or {}).get("text") or "")[:600])
    return not head.strip() or bool(re.search(r"VENDA E COMPRA|COMPRA E VENDA|COMPROMISSO DE COMPRA", head))


def _collect_aditivos(files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split contract-shaped files into (aditivos, the rest). An aditivo is known by its NAME
    (classified ``aditivo``) or by its opening text, whatever the file is called."""
    aditivos, rest = [], []
    for f in files:
        if f["draft"] or f["doc_type"] not in ("aditivo", "contrato", "contrato_d4sign"):
            rest.append(f)
            continue
        rec = _text_for(f)
        is_aditivo = _is_aditivo_text(rec) or (f["doc_type"] == "aditivo" and not (rec or {}).get("text"))
        (aditivos if is_aditivo else rest).append(f)
    return aditivos, rest


def _parse_aditivos(files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(aditivos, descartados)``: aditivos to the deal's contract, deduped, and the
    aditivo-shaped files that amend something else (listed with the reason, never silently dropped)."""
    out: list[dict[str, Any]] = []
    descartados: list[dict[str, Any]] = []
    for f in files:
        rec = _text_for(f) or {}
        signed = f["doc_type"] == "contrato_d4sign" or re.search(r"D4SIGN|CERTIFICADO DIGITAL", _fold(f["rel_path"]))
        fonte = "d4sign" if signed else "docx" if rec.get("text_source") == "docx" else "pdf"
        if not rec.get("text"):
            out.append({"arquivo": f["rel_path"], "fonte": fonte, "status": "so_imagem", "alteracoes": [],
                        "verificado": False, "verificado_por": None})
            continue
        paras = paragraphs_from_text(rec["text"], source="docx" if rec.get("text_source") == "docx" else "pdf")
        ad = parse_aditivo(paras, raw_text=rec["text"], arquivo=f["rel_path"], fonte=fonte)
        if not is_contract_aditivo(ad["titulo"]):
            descartados.append({"arquivo": f["rel_path"], "titulo": ad["titulo"],
                                "motivo": "nao_e_aditivo_do_contrato_de_compra_e_venda"})
            continue
        out.append({**ad, "status": "ok"})
    # One aditivo, several files (docx revisions, the signed PDF): keep the signed one, else the
    # latest revision. Key = ordinal, or the normalized title when the aditivo is not numbered.
    def rank(a: dict[str, Any]) -> tuple:
        return (a["fonte"] == "d4sign", _revision_date(a["arquivo"]) or date.min, a["arquivo"])

    best: dict[Any, dict[str, Any]] = {}
    for a in out:
        k = a.get("numero_ordinal") or re.sub(r"[^A-Z0-9]", "", _fold(a.get("titulo") or a["arquivo"]))
        if k not in best or rank(a) > rank(best[k]):
            if k in best:
                a.setdefault("versoes_descartadas", []).append(best[k]["arquivo"])
            best[k] = a
        else:
            best[k].setdefault("versoes_descartadas", []).append(a["arquivo"])
    return sorted(best.values(), key=lambda a: (a.get("numero_ordinal") or 99, a["arquivo"])), descartados


def _tjsp_sistema_do_arquivo(f: dict[str, Any]) -> Optional[str]:
    """E-SAJ or E-PROC from a numbered certidão file: its name ("7 - TJSP e-saj"), else its text layer,
    else the folder convention (7 = e-SAJ, 8 = e-Proc)."""
    for text in (_fold(f["rel_path"]), _fold(((_text_for(f) or {}).get("text") or "")[:3000])):
        esaj, eproc = bool(re.search(r"E-?\s?SAJ", text)), bool(re.search(r"E-?\s?PROC", text))
        if esaj != eproc:
            return "tjsp_esaj" if esaj else "tjsp_eproc"
    return {7: "tjsp_esaj", 8: "tjsp_eproc"}.get(f.get("certidao_n"))


def _resolve_tjsp(key: dict[str, Any], census: dict[str, Any]) -> None:
    """Split an old generic TJSP item into tjsp_esaj / tjsp_eproc (owner ruling 2026-09-24).
    0. the group already lists the other system explicitly → this item is the missing one;
    1. its nº appears in exactly one TJSP certidão file's text → that file's system;
    2. else the group's entity folder holds files of ONE system only → that system;
    3. else it stays ambiguo=tjsp_sem_sistema (out of scoring). Never the generic code."""
    tj_files = [f for f in census["files"] if f["doc_type"] == "certidao" and f.get("certidao_n") in (7, 8)]
    for g in (key.get("certidoes") or {}).get("grupos") or []:
        nome = set(re.findall(r"[A-Z]+", _fold(g["em_nome_de"])))
        ent = [f for f in tj_files if f.get("entity")
               and (set(re.findall(r"[A-Z]+", _fold(f["entity"]))) - {"CNPJ"}) <= nome
               and (f.get("entity_kind") == "pj") == (g["consulta_tipo_documento"] == "cnpj")]
        for i in g["itens"]:
            if i.get("ambiguo") != "tjsp_sem_sistema":
                continue
            tipo, por = None, None
            # 0. the contract itself: a group that already lists one system explicitly → this is the other
            presentes = {x["tipo"] for x in g["itens"] if x["tipo"] in ("tjsp_esaj", "tjsp_eproc")}
            genericos = [x for x in g["itens"] if x.get("ambiguo") == "tjsp_sem_sistema"]
            if len(presentes) == 1 and len(genericos) == 1:
                tipo, por = ({"tjsp_esaj", "tjsp_eproc"} - presentes).pop(), "outro_sistema_ja_listado"
            num = re.sub(r"\D", "", i.get("numero") or "")
            if tipo is None and len(num) >= 5:
                hits = {_tjsp_sistema_do_arquivo(f) for f in tj_files
                        if num in re.sub(r"\D", "", (_text_for(f) or {}).get("text") or "")} - {None}
                if len(hits) == 1:
                    tipo, por = hits.pop(), "numero_no_arquivo"
            if tipo is None:
                sistemas = {_tjsp_sistema_do_arquivo(f) for f in ent} - {None}
                if len(sistemas) == 1:
                    tipo, por = sistemas.pop(), "unico_sistema_da_entidade"
            if tipo:
                i.update({"tipo": tipo, "pasta_n": CERTIDAO_TIPOS.index(tipo) + 1,
                          "sistema": "E-SAJ" if tipo == "tjsp_esaj" else "E-PROC", "tjsp_resolvido_por": por})
                i.pop("ambiguo", None)


def _check_empresas_vs_contract(key: dict[str, Any]) -> None:
    """E1 cross-check: an empresa is ``exigida`` iff the signed contract carries its certidão group.

    The contract prints a PJ group by CNPJ base (8 digits) or full CNPJ; both are compared by prefix.
    Sets ``contrato_confere`` per empresa; a False is a finding to report, never auto-corrected."""
    grupos = ((key.get("certidoes") or {}).get("grupos")) or []
    docs = [g["documento"] for g in grupos if g.get("consulta_tipo_documento") == "cnpj" and g.get("documento")]
    for e in key["empresas"]:
        cnpj = _digits(e.get("cnpj")) or ""
        no_contrato = any(cnpj.startswith(d) or d.startswith(cnpj) for d in docs) if cnpj else None
        e["no_contrato"] = no_contrato
        e["contrato_confere"] = None if no_contrato is None else (bool(e.get("exigida")) == no_contrato)


def answer_key_folder(folder_id: str) -> dict[str, Any]:
    census = census_folder(folder_id)
    # An ADITIVO (amendment) is signed like the contract, but it is not the contract: it never
    # competes for ground truth, and it is parsed into its own structured list (owner, 2026-09-24).
    aditivo_files, pool = _collect_aditivos(census["files"])
    outros = [f for f in pool if f["doc_type"] in ("contrato", "contrato_d4sign") and not _is_sale_contract(_text_for(f))]
    pool = [f for f in pool if f not in outros]
    chosen, fonte, others = select_contract(pool)
    aditivos, aditivos_descartados = _parse_aditivos(aditivo_files)
    numero = census["folder"]["numero"] or folder_id
    key: dict[str, Any] = {
        "folder": census["folder"],
        "fonte": {"tipo": fonte, "arquivo": chosen["rel_path"] if chosen else None,
                  "confianca": {"d4sign": "alta", "rev_final": "alta", "revisao": "media", "none": "baixa"}[fonte],
                  "divergencias_docx": [], "assinado_em": None},
        "aditivos": aditivos,
        "aditivos_descartados": aditivos_descartados,
        "outros_documentos_assinados": [{"arquivo": f["rel_path"], "titulo": ((_text_for(f) or {}).get("text") or "")[:120].strip()}
                                        for f in outros],
        "tool_version": TOOL_VERSION, "parser_version": PARSER_VERSION,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }
    # An image-only signed PDF cannot be ground truth (reading it back would be OCR scored against
    # itself). But when its NAME embeds the chosen docx's name (D4Sign's "<docx name> docx pdf-D4Sign"),
    # the signed PDF was generated from that exact docx, so the docx is as good as the signature.
    signed_images = [f for f in census["files"] if f["doc_type"] == "contrato_d4sign" and not f["draft"]
                     and f.get("text_source") == "image_only"]
    if chosen is not None and fonte in ("revisao", "rev_final"):
        stem = re.sub(r"[^A-Z0-9]", "", _fold(Path(chosen["rel_path"]).stem.replace("_", " ")))
        if stem and any(stem in re.sub(r"[^A-Z0-9]", "", _fold(f["rel_path"].replace("_", " "))) for f in signed_images):
            key["fonte"]["confianca"] = "alta"
            key["fonte"]["nota"] = "d4sign_imagem_gerado_deste_docx"
    if chosen is None:
        key["status"] = "contrato_so_imagem" if signed_images else "sem_contrato"
        key["fonte"]["assinado_imagem"] = [f["rel_path"] for f in signed_images]
    else:
        cached = _text_for(chosen)
        if not cached or cached.get("error") or not cached.get("text"):
            key["status"] = "contrato_sem_texto"
        else:
            source = "docx" if cached.get("text_source") == "docx" else "pdf"
            paras = paragraphs_from_text(cached["text"], source=source)
            key.update(parse_contract(paras))
            _resolve_tjsp(key, census)
            if fonte == "d4sign":
                key["fonte"]["assinado_em"] = d4sign_assinado_em(cached["text"])
            key["status"] = "ok"
            if fonte == "d4sign":
                docx_rows = [f for f in others if f.get("rev_final")] or others
                if docx_rows:
                    latest = max(docx_rows, key=lambda f: (_revision_date(f["rel_path"]) or date.min, f["rel_path"]))
                    dc = _text_for(latest)
                    if dc and dc.get("text"):
                        key["fonte"]["divergencias_docx"] = diff_paragraphs(
                            paragraphs_from_text(dc["text"], source="docx"), paras)
                        key["fonte"]["docx_comparado"] = latest["rel_path"]
    # Empresas: never machine-read (circular). Only a human-verified file enters the key.
    verified = _dp.private_root() / "answer-keys" / f"{numero}-empresas-verificado.json"
    key["empresas"], key["crednet"], key["empresas_fonte"] = [], None, None
    if verified.is_file():
        v = json.loads(verified.read_text(encoding="utf-8"))
        marca = {"verificado": True, "verificado_por": v.get("verificado_por")}
        key["empresas"] = [{**e, **marca} for e in v.get("empresas") or []]
        key["crednet"] = {**v["crednet"], **marca} if v.get("crednet") else None
        key["empresas_fonte"] = verified.name
        _check_empresas_vs_contract(key)
    _write_private(_dir("answer-keys") / f"{numero}.json", key)
    return {"numero": numero, "status": key["status"], "fonte": fonte,
            "divergencias_docx": len(key["fonte"]["divergencias_docx"]), "aditivos": len(aditivos),
            "aditivos_categorias": sorted({c for a in aditivos for s in a["alteracoes"] for c in s["categorias"]}),
            "aditivos_descartados": len(aditivos_descartados),
            "cobertura": _coverage(key) if key["status"] == "ok" else None}


# ─── folder → imóvel ref candidates ───────────────────────────────────────
#
# Owner rule (2026-09-24, via noctusai-3e): match each deal to its in-house / Vista imóvel by address
# + condomínio + m² + endereço interno. CANDIDATES ONLY — the owner confirms every match; nothing
# here writes to any database or links anything.

SW_ORG_ID = "6dd73140-74a4-41c6-aeff-bc94b5312b53"  # where the owner's SW data lives (per 3e)
SNAPSHOT_MAX_AGE_S = 24 * 3600
SNAPSHOT_SCHEMA = 2  # bump when _SNAPSHOT_SQL gains columns: an older snapshot is re-read once
_SNAPSHOT_SQL = """SELECT i.codigo, i.empreendimento, i.logradouro, i.numero, i.complemento, i.bairro, i.cidade, i.uf,
       i.area_total, i.area_privativa, i.area_construida, i.area_terreno, i.matricula_vista, i.inscricao_municipal,
       i.status, i.categoria, i.valor_venda,
       d.numero_matricula, d.numero_registro_imoveis, d.prefeitura_cadastro_imobiliario, d.empreendimento_manual,
       d.endereco_manual_logradouro, d.endereco_manual_numero, d.endereco_manual_complemento, d.endereco_manual_cidade,
       d.endereco_registro_texto
  FROM social_wiring.imoveis i
  LEFT JOIN social_wiring.imovel_dados d ON d.org_id = i.org_id AND d.codigo = i.codigo
 WHERE i.org_id = '{org}'"""


def _sql_executor():
    """The Management-API SQL seam migrate_product already ships (same endpoint and auth as the
    supabase MCP's db.query). Only SELECTs are ever sent through it from here."""
    from .migrate_product import make_sql_executor

    return make_sql_executor()


def ref_snapshot(*, executor=None, refresh: bool = False) -> dict[str, Any]:
    """SW's imóveis (the Vista-synced catalog) + imovel_dados, read ONCE into a private 0600 snapshot
    and reused for SNAPSHOT_MAX_AGE_S (extract-once: the catalog is not re-read per folder)."""
    path = _dir("ref-candidates") / "_sw_imoveis.json"
    if path.is_file() and not refresh and (datetime.now().timestamp() - path.stat().st_mtime) < SNAPSHOT_MAX_AGE_S:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("schema") == SNAPSHOT_SCHEMA:
            return cached
    sql = _SNAPSHOT_SQL.format(org=SW_ORG_ID)
    if not re.match(r"^\s*SELECT\b", sql, re.I):  # read-only by construction; never send anything else
        raise RuntimeError("ref_snapshot only runs SELECT statements")
    executor = executor or _sql_executor()
    if executor is None:
        raise RuntimeError("no Supabase Management-API token (SUPABASE_ACCESS_TOKEN) — cannot read SW imóveis")
    res = executor.execute(sql)
    if not res.get("ok"):
        raise RuntimeError(f"SW snapshot query failed: {res.get('error')}")
    snap = {"org_id": SW_ORG_ID, "schema": SNAPSHOT_SCHEMA, "lido_em": datetime.now(timezone.utc).isoformat(),
            "imoveis": res["rows"] or []}
    _write_private(path, snap)
    return snap


_CONDO_STOP = frozenset({"RESIDENCIAL", "CONDOMINIO", "COND", "LOTEAMENTO", "EDIFICIO", "ED", "DA", "DE", "DO",
                         "DAS", "DOS", "E", "O", "A", "I", "II", "III", "IV", "CASA", "APTO", "APARTAMENTO",
                         "LOTE", "RUA", "AL", "ALAMEDA", "AV", "AVENIDA", "ESTRADA", "VIA", "TRAVESSA", "SP"})
_AREA_RE = re.compile(r"([\d.]+,\d{1,2}|\d+)\s*m(?:²|2|ts)", re.I)
_UNIDADE_RE = re.compile(r"\b(CASA|APTO|APARTAMENTO|UNIDADE|LOTE)\s*(?:N[ºO°.]?\s*)?(\d+[A-Z]?)\b")


def _tokens(s: Optional[str]) -> set[str]:
    return {t for t in re.findall(r"[A-Z0-9]+", _fold(s or "")) if t not in _CONDO_STOP and not t.isdigit() and len(t) > 1}


def _num(s: Any) -> Optional[str]:
    d = re.sub(r"\D", "", str(s or "")).lstrip("0")
    return d or None


def _areas(text: str) -> list[float]:
    out = []
    for m in _AREA_RE.finditer(text or ""):
        try:
            out.append(float(m.group(1).replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return [a for a in out if a >= 15]  # below that it is a frente/fundos measure, not an area


def deal_features(key: dict[str, Any]) -> dict[str, Any]:
    """What a deal's answer key says about its imóvel, normalized for matching."""
    folder = key.get("folder") or {}
    imovel = key.get("imovel") or {}
    dados = imovel.get("imovel_dados") or {}
    titulo_contrato = (key.get("contrato") or {}).get("titulo") or ""
    descricao = imovel.get("descricao_matricula_texto") or ""
    bag = " ".join([folder.get("titulo") or "", titulo_contrato])
    unidades = {(m.group(1)[:4], m.group(2)) for m in _UNIDADE_RE.finditer(_fold(bag + " " + descricao[:300]))}
    cidade = None
    m = re.search(r"[–\-]\s*([A-ZÀ-Ý][A-ZÀ-Ý ]+?)\s*[/\-–]\s*SP\.?\s*$", titulo_contrato.strip())
    if m:
        cidade = _fold(m.group(1)).strip()
    return {
        "matricula": _num(dados.get("numero_matricula")),
        "inscricao": _num(dados.get("prefeitura_cadastro_imobiliario")),
        "cartorio": _fold(dados.get("numero_registro_imoveis") or ""),
        "tokens": _tokens(bag),
        "unidades": unidades,
        "areas": _areas(descricao),
        "valor": float(((key.get("negociacao") or {}).get("valor_negociado")) or 0) or None,
        "cidade": cidade,
        "texto": _fold(bag + " " + descricao),
    }


def _area_evidence(deal_areas: list[float], row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """GRADED area distance, best pair of (matrícula area, Vista area field). The KB's worked case
    (ONE7515) is 1.050,24 m² on the matrícula vs AreaTotal 1052 — 0.17%, i.e. measurement noise."""
    best = None
    for campo in ("area_total", "area_terreno", "area_privativa", "area_construida"):
        b = row.get(campo)
        if not b:
            continue
        for a in deal_areas:
            d = abs(a - float(b)) / max(a, float(b))
            if best is None or d < best["diff_pct"] / 100:
                best = {"negocio_m2": a, "vista_m2": float(b), "campo": campo, "diff_pct": round(d * 100, 2)}
    if not best:
        return None
    d = best["diff_pct"]
    pontos = 25 if d <= 0.5 else 18 if d <= 2 else 10 if d <= 5 else 4 if d <= 10 else 0
    return {**best, "pontos": pontos} if pontos else None


def _preco_evidence(contrato: Optional[float], venda: Any) -> Optional[dict[str, Any]]:
    """GRADED price fit: the contract's valor_negociado vs the listing's asking price (ValorVenda —
    the only price the sync carries; there is no historical price). A negotiated price usually sits
    BELOW asking, so 85–100% of asking is the closest band; above asking is penalized (owner, via 3e)."""
    try:
        venda_f = float(venda or 0)
    except (TypeError, ValueError):
        return None
    if not contrato or venda_f <= 0:
        return None
    r = contrato / venda_f
    pontos = 20 if 0.95 <= r <= 1.0 else 15 if 0.85 <= r < 0.95 else 8 if (0.75 <= r < 0.85 or 1.0 < r <= 1.05) else 0
    if not pontos:
        return None
    return {"contrato": contrato, "vista_valor_venda": venda_f, "razao": round(r, 3), "pontos": pontos}


def _registro_confere(registro: str, deal_text: str) -> bool:
    """The operator-confirmed registry address (street + número) appears in the deal's contract text."""
    rua = _tokens(re.split(r",|\bn[º°o.]", registro, maxsplit=1)[0])
    num = re.search(r"\b(\d{1,5})\b", registro)
    words = set(re.findall(r"[A-Z0-9]+", deal_text))
    return bool(rua) and rua <= words and (num is None or re.search(rf"\b{num.group(1)}\b", deal_text) is not None)


def score_candidate(f: dict[str, Any], row: dict[str, Any]) -> tuple[int, list[str], dict[str, Any]]:
    """(points, evidence, graded details) for one SW/Vista imóvel against one deal. Documentary
    identifiers (matrícula, inscrição, the operator-confirmed registry address) are strong;
    condomínio/unidade/área/preço are medium; street/city are weak (Vista's PUBLIC endereço is the
    gatehouse by office policy, and this tenant's API has no internal-address field — KB vista.md)."""
    pts, ev = 0, []
    det: dict[str, Any] = {}
    mats = {_num(row.get("matricula_vista")), _num(row.get("numero_matricula"))} - {None}
    if f["matricula"] and f["matricula"] in mats:
        pts += 60
        ev.append("matricula")
    inscs = {_num(row.get("inscricao_municipal")), _num(row.get("prefeitura_cadastro_imobiliario"))} - {None}
    if f["inscricao"] and f["inscricao"] in inscs:
        pts += 60
        ev.append("inscricao_municipal")
    condo = _tokens(row.get("empreendimento_manual") or row.get("empreendimento"))
    if condo and len(condo & f["tokens"]) / len(condo) >= 0.6:
        pts += 25
        ev.append("condominio")
        comp = _fold(" ".join(str(row.get(k) or "") for k in ("complemento", "endereco_manual_complemento", "numero")))
        if any(re.search(rf"\b{re.escape(n)}\b", comp) for _, n in f["unidades"]):
            pts += 15
            ev.append("unidade")
    area = _area_evidence(f["areas"], row)
    if area:
        pts += area["pontos"]
        ev.append("area_m2")
        det["area_m2"] = area
    preco = _preco_evidence(f.get("valor"), row.get("valor_venda"))
    if preco:
        pts += preco["pontos"]
        ev.append("preco")
        det["preco"] = preco
    reg = row.get("endereco_registro_texto")
    if reg and _registro_confere(reg, f["texto"]):
        pts += 60
        ev.append("endereco_registro")
        det["endereco_registro"] = {"fonte": "imovel_dados.endereco_registro_texto (confirmado pelo operador)"}
    rua = _tokens(row.get("endereco_manual_logradouro") or row.get("logradouro"))
    if rua and rua <= set(re.findall(r"[A-Z0-9]+", f["texto"])):
        pts += 10
        ev.append("logradouro")
        num = _num(row.get("endereco_manual_numero") or row.get("numero"))
        if num and re.search(rf"\b{num}\b", f["texto"]):
            pts += 5
            ev.append("numero_publico")
    cid = _fold(row.get("endereco_manual_cidade") or row.get("cidade") or "")
    if f["cidade"] and cid and cid == f["cidade"]:
        pts += 5
        ev.append("cidade")
    return pts, ev, det


_DOCUMENTAIS = frozenset({"matricula", "inscricao_municipal", "endereco_registro"})
_PROPRIEDADE = _DOCUMENTAIS | {"condominio", "area_m2", "logradouro"}


def ref_candidates_folder(folder_id: str, snapshot: dict[str, Any], *, top: int = 3) -> dict[str, Any]:
    census = census_folder(folder_id)
    numero = census["folder"]["numero"] or folder_id
    key_path = _dp.private_root() / "answer-keys" / f"{numero}.json"
    if not key_path.is_file():
        return {"numero": numero, "status": "sem_answer_key"}
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if key.get("status") != "ok":
        return {"numero": numero, "status": f"answer_key_{key.get('status')}"}
    f = deal_features(key)
    scored = []
    for row in snapshot["imoveis"]:
        pts, ev, det = score_candidate(f, row)
        # price, city and the public número only CORROBORATE: a candidate needs a property signal
        if pts >= 25 and _PROPRIEDADE & set(ev):
            scored.append((pts, ev, row, det))
    # A documentary identifier (matrícula / inscrição / confirmed registry address) outranks any sum of soft signals.
    scored.sort(key=lambda t: (not (_DOCUMENTAIS & set(t[1])), -t[0]))
    cands = [{"codigo": row["codigo"], "pontos": pts, "evidencias": ev,
              "forca": "forte" if _DOCUMENTAIS & set(ev) else "media" if pts >= 40 else "fraca",
              "evidencias_detalhe": det,
              "empreendimento": row.get("empreendimento"), "logradouro": row.get("logradouro"),
              "numero": row.get("numero"), "complemento": row.get("complemento"), "cidade": row.get("cidade"),
              "status_vista": row.get("status")} for pts, ev, row, det in scored[:top]]
    out = {"folder": census["folder"], "gerado_em": datetime.now(timezone.utc).isoformat(),
           "confirmado_por": None, "confirmado_em": None,  # the OWNER fills these; never the tool
           "sinais_do_negocio": {"matricula": bool(f["matricula"]), "inscricao": bool(f["inscricao"]),
                                 "unidades": sorted("".join(u) for u in f["unidades"]), "areas": f["areas"],
                                 "cidade": f["cidade"]},
           "candidatos": cands}
    _write_private(_dir("ref-candidates") / f"{numero}.json", out)
    top1 = cands[0] if cands else None
    empate = len(cands) > 1 and cands[0]["pontos"] == cands[1]["pontos"]
    return {"numero": numero, "status": "ok", "candidatos": len(cands),
            "melhor_forca": top1["forca"] if top1 else None, "melhor_evidencias": top1["evidencias"] if top1 else [],
            "empate_no_topo": empate}


# ─── tool entry ───────────────────────────────────────────────────────────


def _resolve_folders(folder_id: Optional[str]) -> list[str]:
    if folder_id and folder_id != "all":
        return [folder_id]
    return [p.name for p in _mirror_dirs()]


_ACTIONS = ("extract", "census", "answer_key", "ref_candidates")


def drive_census(action: str, folder_id: Optional[str] = None, *, refresh: bool = False,
                 executor=None) -> dict[str, Any]:
    """``extract`` | ``census`` | ``answer_key`` | ``ref_candidates`` over one mirrored folder, or ``all``."""
    if action not in _ACTIONS:
        raise ValueError(f"action must be {' | '.join(_ACTIONS)}, got {action!r}")
    folders = _resolve_folders(folder_id)
    results: list[dict[str, Any]] = []
    snapshot = ref_snapshot(executor=executor, refresh=refresh) if action == "ref_candidates" else None
    for fid in folders:
        try:
            if action == "extract":
                results.append(extract_folder(fid))
            elif action == "census":
                extract_folder(fid)  # cached files cost nothing; new ones are read once
                c = census_folder(fid)
                numero = c["folder"]["numero"] or fid
                _write_private(_dir("census") / f"{numero}.json", c)
                results.append(_redacted_census(c))
            elif action == "answer_key":
                extract_folder(fid)
                results.append(answer_key_folder(fid))
            else:
                results.append(ref_candidates_folder(fid, snapshot))
        except Exception as exc:  # noqa: BLE001 — one bad folder never hides the rest; surfaced per folder
            results.append({"folder_id": fid, "error": f"{type(exc).__name__}: {exc}"})
    if action == "census" and results:
        _write_private(_dir("census") / "_summary.json", results)
    return {"action": action, "folders": len(folders), "results": results,
            "errors": sum(1 for r in results if r.get("error") or r.get("errors")),
            "private_dir": str(_dp.private_root())}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.drive_census",
        description=(
            "Census + contract answer keys over noctus.dev.drive_pull mirrors (private disk), "
            "extract-once. action='extract' folder_id=<id>|'all' → text for every file, cached by "
            "sha256 under ~/.noctusai/private/extractions (free rungs only: docx, PDF text layer; a "
            "cached file is never re-read, only retried on a cached error). action='census' → per-"
            "folder doc-type coverage, certidão sets per entity (PF 1-12 / PJ 11), gaps, "
            "image-only vs text-layer, permuta/empresa signals. action='answer_key' → ground-truth "
            "contract (D4Sign > REV FINAL > latest revision; drafts excluded), parsed into social_wiring "
            "vocabulary; empresas only from a human-verified file. Outputs are 0600 under the private "
            "dir; the result carries counts and flags only, never personal data. "
            "action='ref_candidates' [refresh] → per deal, the top-3 SW/Vista imóvel candidates "
            "(matrícula / inscrição exact = forte; condomínio + unidade + m² = media) from a cached "
            "read-only SW snapshot. Candidates only: the owner confirms every match; nothing is linked."
        ),
    )
    def _drive_census(action: str, folder_id: str | None = None, refresh: bool = False) -> dict:
        return drive_census(action=action, folder_id=folder_id, refresh=refresh)


__all__ = ["drive_census", "classify_entry", "parse_contract", "paragraphs_from_text", "select_contract",
           "register"]
