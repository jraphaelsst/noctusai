"""
NF-e (Brazilian e-invoice) XML parser — local to AdConnect.

Phase 4 needs to extract sellout-relevant fields from a distributor-uploaded
NF-e XML: client CNPJ, line items, total, NF-e access key. We use stdlib
`xml.etree.ElementTree` (no external dependency) and tolerate missing
namespaces / partial documents — sellout submissions in the wild are rarely
schema-perfect.

The NF-e access key (`chNFe`) is 44 numeric characters; we extract from the
canonical `<infNFe Id="NFe<44digits>">` attribute or, falling back, from a
`<chNFe>` element. CNPJ + items + total come from `<dest><CNPJ>` + `<det><prod>`
+ `<total><ICMSTot><vNF>` respectively.

**Verify-the-seed-ships-it (2026-05-10):** searched
`seed/lib/backend/noctusai_lib/integrations/` for any `nfe*` module — none
shipped. The recurrence rule fires at N=2 (another product ever needs NF-e
parsing) → file a `noctusai_lib.domain.nfe` follow-up project at that point.
For N=1 (AdConnect only) we ship local per `feedback_verify_seed_ships_it.md`.

**No silent errors:** parser raises `NFeParseError` on malformed XML and
on missing-required-fields when the caller passes `strict=True`. The
default (lenient) mode returns whatever was extractable + None for the
rest, so partial / handwritten XMLs don't kill the upload — the brand
admin reviews and decides.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from xml.etree import ElementTree as ET  # type-only: ParseError reused

from defusedxml.ElementTree import fromstring as _safe_fromstring
from defusedxml.common import DefusedXmlException

logger = logging.getLogger(__name__)

# NF-e access-key shape: 44 numeric digits. We tolerate any namespace
# declaration (or none) and walk by tag local-name to maximize robustness
# to ad-hoc / partial XMLs in the wild.
_CHAVE_RE = re.compile(r"(\d{44})")


class NFeParseError(ValueError):
    """Raised when NF-e XML parsing fails or required fields are absent."""


@dataclass
class ParsedNFe:
    """Result of a successful (or partial) parse."""

    cnpj_cliente_final: Optional[str] = None
    valor_total: Optional[float] = None
    quantidade_itens: Optional[int] = None
    descricao_resumida: Optional[str] = None
    items_json: list[dict[str, Any]] = field(default_factory=list)
    nfe_chave: Optional[str] = None

    def as_payload(self) -> dict[str, Any]:
        """Shape that maps 1:1 onto `relatorios_sellout` columns."""
        return {
            "cnpj_cliente_final": self.cnpj_cliente_final,
            "valor_total": self.valor_total,
            "quantidade_itens": self.quantidade_itens,
            "descricao_resumida": self.descricao_resumida,
            "items_json": self.items_json,
            "nfe_chave": self.nfe_chave,
        }


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_by_local(root: ET.Element, local: str):
    for el in root.iter():
        if _localname(el.tag) == local:
            yield el


def _first_text_local(root: ET.Element, local: str) -> Optional[str]:
    for el in _iter_by_local(root, local):
        if el.text and el.text.strip():
            return el.text.strip()
    return None


def _first_text_under_parent(
    root: ET.Element, parent_local: str, child_local: str
) -> Optional[str]:
    for parent in _iter_by_local(root, parent_local):
        for child in parent:
            if _localname(child.tag) == child_local and child.text and child.text.strip():
                return child.text.strip()
    return None


def _extract_chave(root: ET.Element) -> Optional[str]:
    # Preferred: <infNFe Id="NFe<44digits>">
    for inf in _iter_by_local(root, "infNFe"):
        attr = inf.attrib.get("Id", "")
        m = _CHAVE_RE.search(attr)
        if m:
            return m.group(1)
    # Fallback: <chNFe>
    text = _first_text_local(root, "chNFe")
    if text:
        m = _CHAVE_RE.search(text)
        if m:
            return m.group(1)
    return None


def _extract_items(root: ET.Element) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for det in _iter_by_local(root, "det"):
        prod = next((c for c in det if _localname(c.tag) == "prod"), None)
        if prod is None:
            continue
        item: dict[str, Any] = {}
        for child in prod:
            local = _localname(child.tag)
            if local in {"cProd", "xProd", "NCM", "CFOP", "uCom"} and child.text:
                item[local] = child.text.strip()
            if local in {"qCom", "vUnCom", "vProd"} and child.text:
                try:
                    item[local] = float(child.text.strip())
                except ValueError:
                    item[local] = child.text.strip()
        if item:
            items.append(item)
    return items


def parse_nfe_xml(xml_bytes: bytes | str, *, strict: bool = False) -> ParsedNFe:
    """Parse an NF-e XML document.

    Args:
        xml_bytes: raw XML (bytes or str).
        strict: when True, raise `NFeParseError` if any required field is
            absent (cnpj, valor_total, chave). When False (default), missing
            fields stay None on the result and the caller can decide what
            to do (usually: surface for brand-admin review).

    Returns:
        ParsedNFe with whatever could be extracted.

    Raises:
        NFeParseError on malformed XML, or on missing required fields when
        `strict=True`.
    """
    if isinstance(xml_bytes, bytes):
        try:
            xml_text = xml_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NFeParseError(f"NF-e XML is not valid UTF-8: {exc}") from exc
    else:
        xml_text = xml_bytes

    try:
        # defusedxml's fromstring is a drop-in defense against XML attacks
        # (billion laughs / external entity expansion); raises ET.ParseError
        # on malformed input AND DefusedXmlException (EntitiesForbidden /
        # DTDForbidden / ExternalReferenceForbidden) on hostile XML — wrap
        # both into the parser's surface error type.
        root = _safe_fromstring(xml_text)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise NFeParseError(f"NF-e XML parse failed: {exc}") from exc

    cnpj = _first_text_under_parent(root, "dest", "CNPJ")
    if not cnpj:
        cnpj = _first_text_local(root, "CNPJ")
    valor_text = None
    for tot in _iter_by_local(root, "ICMSTot"):
        for child in tot:
            if _localname(child.tag) == "vNF" and child.text:
                valor_text = child.text.strip()
                break
        if valor_text:
            break
    if not valor_text:
        valor_text = _first_text_local(root, "vNF")
    valor_total: Optional[float] = None
    if valor_text:
        try:
            valor_total = float(valor_text)
        except ValueError:
            valor_total = None

    items = _extract_items(root)
    nfe_chave = _extract_chave(root)
    descricao = None
    if items:
        nomes = [str(it.get("xProd", "")) for it in items if it.get("xProd")]
        descricao = "; ".join(nomes[:3]) if nomes else None

    parsed = ParsedNFe(
        cnpj_cliente_final=cnpj,
        valor_total=valor_total,
        quantidade_itens=len(items) if items else None,
        descricao_resumida=descricao,
        items_json=items,
        nfe_chave=nfe_chave,
    )

    if strict:
        missing = [
            name
            for name, val in (
                ("cnpj_cliente_final", parsed.cnpj_cliente_final),
                ("valor_total", parsed.valor_total),
                ("nfe_chave", parsed.nfe_chave),
            )
            if val is None
        ]
        if missing:
            raise NFeParseError(
                f"NF-e XML missing required fields: {', '.join(missing)}"
            )

    logger.debug(
        "nfe-parser: extracted cnpj=%s items=%d total=%s chave=%s",
        parsed.cnpj_cliente_final,
        len(parsed.items_json),
        parsed.valor_total,
        parsed.nfe_chave,
    )
    return parsed


__all__ = ["NFeParseError", "ParsedNFe", "parse_nfe_xml"]
