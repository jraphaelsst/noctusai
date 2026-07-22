"""Canonical Leads dimension catalog — sources, brokers, and their alias
maps — derived from actually reading ``CONTROLE LEADS (1).xlsx``
(29 monthly sheets, 12,177 valid data rows after header/blank-row
exclusion; see ``leads-module-PROJECT.md`` §3).

Why this lives here and not as migration-seeded SQL
────────────────────────────────────────────────────
``lead_sources`` / ``lead_corretores`` (and their alias tables) are
``org_id NOT NULL`` — genuinely per-org dimensions. No migration in this
product ever seeds an org-scoped row with a hardcoded ``org_id`` (there is
no "the org" at migration-apply time in a multi-tenant schema), so this
catalog is applied idempotently, per-org, by
``services.dimensions_service.ensure_default_dimensions(org_id)`` instead
— called from the import-commit path (a real write already), never from a
bare GET. See ``migrations/025_leads.sql``'s header comment for the full
rationale.

Provenance of the alias tables below
──────────────────────────────────────
Read via openpyxl locally (never committed — the workbook is gitignored,
holds ~12k real names/phones). ``ORIGEM`` is column index 2 in all 29
sheets (verified). Distinct non-blank raw spellings found: 75 (matches
the brief's count exactly). Distinct broker raw spellings found: ~60,
collapsing to the canonical list below via case/typo/trailing-space
aliases; composite multi-value cells (``"REJANE/MÔNICA"``, ``"ZAP,
IMOVEL WEB"``) are NOT baked in as aliases here — the importer splits on
common separators and resolves the FIRST recognizable token at parse
time (`importer/resolvers.py`), matching the brief's own worked examples.

``needs_review`` is set at import time for any row whose ``origem``
resolves to the ``outro`` bucket (blanket rule — "outro" means "we could
not confidently classify this," which subsumes the explicit
"ONE8137 - JARDIM COLIBRI - KM 26 leaked-código" case: 135 occurrences,
confirmed exactly against the brief's own count).
"""
from __future__ import annotations

import re
from typing import TypedDict

# ─── normalization ──────────────────────────────────────────────────────

def normalize_alias(value: str) -> str:
    """Upper + trim + collapse-whitespace — the ``alias_norm`` convention
    shared by ``lead_source_aliases`` and ``lead_corretor_aliases``."""
    return re.sub(r"\s+", " ", value.strip()).upper()


# ─── canonical sources ──────────────────────────────────────────────────

class SourceSeed(TypedDict):
    slug: str
    label: str
    categoria: str
    cor: str
    ordem: int


# Order matters (chart legend / render order for the top series); colors
# for the top-5-by-volume sources (senseys, zap, tempo-real, imovel-web,
# instagram-josi) are drawn from the Okabe-Ito colorblind-safe palette so
# the donut/stacked-area charts don't rely on hue alone to distinguish
# them. The rest use a distinct-enough qualitative palette.
CANONICAL_SOURCES: list[SourceSeed] = [
    {"slug": "senseys", "label": "Senseys", "categoria": "portal", "cor": "#0072B2", "ordem": 0},
    {"slug": "zap", "label": "ZAP", "categoria": "portal", "cor": "#D55E00", "ordem": 1},
    {"slug": "tempo-real", "label": "Tempo Real", "categoria": "portal", "cor": "#009E73", "ordem": 2},
    {"slug": "imovel-web", "label": "Imóvel Web", "categoria": "portal", "cor": "#E69F00", "ordem": 3},
    {"slug": "instagram-josi", "label": "Instagram (Josi)", "categoria": "social", "cor": "#CC79A7", "ordem": 4},
    {"slug": "instagram", "label": "Instagram", "categoria": "social", "cor": "#F0E442", "ordem": 5},
    {"slug": "viva-real", "label": "Viva Real", "categoria": "portal", "cor": "#E31C79", "ordem": 6},
    {"slug": "site", "label": "Site", "categoria": "direto", "cor": "#56B4E9", "ordem": 7},
    {"slug": "whatsapp", "label": "WhatsApp", "categoria": "direto", "cor": "#25D366", "ordem": 8},
    {"slug": "v4", "label": "V4", "categoria": "portal", "cor": "#A0522D", "ordem": 9},
    {"slug": "olx", "label": "OLX", "categoria": "portal", "cor": "#6E44FF", "ordem": 10},
    {"slug": "facebook", "label": "Facebook", "categoria": "social", "cor": "#3B5998", "ordem": 11},
    {"slug": "loft", "label": "Loft", "categoria": "portal", "cor": "#FF6F61", "ordem": 12},
    {"slug": "casa-mineira", "label": "Casa Mineira", "categoria": "portal", "cor": "#4C4C9D", "ordem": 13},
    {"slug": "indicacao", "label": "Indicação", "categoria": "direto", "cor": "#2CA02C", "ordem": 14},
    {"slug": "ligacao", "label": "Ligação", "categoria": "direto", "cor": "#17BECF", "ordem": 15},
    {"slug": "tiktok", "label": "TikTok", "categoria": "social", "cor": "#111111", "ordem": 16},
    {"slug": "youtube", "label": "YouTube", "categoria": "social", "cor": "#FF0000", "ordem": 17},
    {"slug": "placa", "label": "Placa", "categoria": "offline", "cor": "#8C564B", "ordem": 18},
    {"slug": "follow-up", "label": "Follow-up", "categoria": "direto", "cor": "#BCBD22", "ordem": 19},
    {"slug": "parceria", "label": "Parceria", "categoria": "parceria", "cor": "#9467BD", "ordem": 20},
    {"slug": "proprietario", "label": "Proprietário", "categoria": "direto", "cor": "#7F7F7F", "ordem": 21},
    {"slug": "outro", "label": "Outro", "categoria": "outro", "cor": "#C7C7C7", "ordem": 22},
]

# raw ORIGEM spelling (already normalize_alias'd below at import time) ->
# canonical slug. 75 distinct non-blank raw spellings found in the real
# workbook; a truly blank origem cell is handled specially by the
# importer (needs_review=true, origem_id=NULL) rather than as an alias
# row here.
SOURCE_ALIAS_RAW: dict[str, str] = {
    "SENSEYS": "senseys",
    "ZAP": "zap",
    "TEMPO REAL": "tempo-real",
    "IMOVEL WEB": "imovel-web",
    "INSTAGRAM JOSI": "instagram-josi",
    "SITE": "site",
    "WHATSAPP": "whatsapp",
    "ZAP/LAIS": "zap",
    "WHATSAPP/LAIS": "whatsapp",
    "IMOVELWEB/LAIS": "imovel-web",
    "INSTAGRAM": "instagram",
    "WEB": "site",
    "VIVA REAL": "viva-real",
    "ONE8137 - JARDIM COLIBRI - KM 26": "outro",  # código leaked into origem, 135x — needs_review
    "FOLLOW-UP": "follow-up",
    "V4": "v4",
    "LIGAÇÃO": "ligacao",
    "SITE/LAIS": "site",
    "FACEBOOK": "facebook",
    "INDICAÇÃO": "indicacao",
    "VIVAREAL": "viva-real",
    "LOFT": "loft",
    "OLX": "olx",
    "CASA MINEIRA": "casa-mineira",
    "GRUPO ZAP": "zap",
    "HP": "outro",
    "TIKTOK": "tiktok",
    "PLACA": "placa",
    "YOUTUBE": "youtube",
    "INSTAGRAN": "instagram",
    "PARCERIA": "parceria",
    "GOOGLE/ WHATS": "whatsapp",
    "LAIS": "outro",
    "ZAP, IMOVEL WEB": "zap",
    "RETORNO": "outro",
    "INSTAGRAM, SENSEYS": "instagram",
    "CLIENTE ONE": "outro",
    "IMÓVEL WEB": "imovel-web",
    "CAPTAÇÃO": "outro",
    "JÁ CLIENTE": "outro",
    "VIVA  REAL": "viva-real",
    "ZAP, INSTAGRAM": "zap",
    "LIGAÇÃO, ZAP": "ligacao",
    "LEAD 123I": "outro",
    "CASA MINEIRA, VIVA REAL": "casa-mineira",
    "VIVA REAL, ZAP": "viva-real",
    "☆☆☆☆☆": "outro",
    "CLIENTE INATIVO": "outro",
    "LIGOU": "ligacao",
    "IMOVELWEB": "imovel-web",
    "INSTAGRAM CORRETOR": "instagram",
    "ZAP/LIGAÇÃO": "zap",
    "LIGAÇÃO /ZAP": "ligacao",
    "JÁ  CLIENTE": "outro",
    "VILA REAL": "viva-real",
    "IMOBILIÁRIA": "outro",
    "E-MAIL": "outro",
    "META V4": "v4",
    "INSTAGRAM LIVE": "instagram",
    "INNTAGRAM": "instagram",
    "HP (CLIENTE RETORNOU)": "outro",
    "VIA TELEFONE- JÁ CADASTRO": "outro",
    "VIVAVREAL": "viva-real",
    "RETORNO/INSTAGRAM": "instagram",
    "RETORNO- WEB": "site",
    "RETORNO ZAP": "zap",
    "INDICAÇÃO CLIENTE GILSON": "indicacao",
    "CONHECE A IMOB.": "outro",
    "VIVAVERAL": "viva-real",
    "LIGAÇÃO IMOBILIÁRIA": "ligacao",
    "ISNTAGRAM": "instagram",
    "CONTATO ONE": "outro",
    "GRUPO OLX": "olx",
    "VR": "viva-real",
    "VIAREAL": "viva-real",
}

SOURCE_ALIASES: dict[str, str] = {
    normalize_alias(raw): slug for raw, slug in SOURCE_ALIAS_RAW.items()
}


# ─── canonical brokers (corretores) ─────────────────────────────────────

class CorretorSeed(TypedDict):
    nome: str
    cor: str


# A d3-category20-ish qualitative palette, cycled (28 canonical brokers
# found in the real data — more than the "~15" ballpark in the brief;
# the workbook is the source of truth per `KB § 01-PHILOSOPHY.md`).
_CORRETOR_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]

CANONICAL_CORRETORES: list[CorretorSeed] = [
    {"nome": name, "cor": _CORRETOR_PALETTE[i % len(_CORRETOR_PALETTE)]}
    for i, name in enumerate(
        [
            "Cindy", "Renata", "Rejane", "Fabiana", "Ana Maria", "Larissa",
            "Elisa", "Victor", "Wilson", "Alessander", "Marco", "Fernanda",
            "Douglas", "Gilson", "Priscila", "Mônica", "Jose Neves",
            "Vanessa", "João Raphael", "Andre", "Alcina", "Felipe",
            "Jhonatan", "Cyntia", "Silvia", "Lucileia", "Rita", "Jose Alves",
        ]
    )
]

# raw CORRETOR/CONSULTOR spelling -> canonical nome. Composite multi-broker
# cells ("REJANE/MÔNICA", "CINDY, RENATA", ...) are resolved by the
# importer (first-recognizable-token), not enumerated here. Ambiguous /
# non-name values ("?", "REGIÃO NÃO INTERESSA", "LUD") are deliberately
# left unmapped — corretor_id stays NULL, corretor_raw keeps the verbatim
# value (no needs_review dimension for corretor per the contract).
CORRETOR_ALIAS_RAW: dict[str, str] = {
    "CINDY": "Cindy",
    "CIDY": "Cindy",
    "RENATA": "Renata",
    "REJANE": "Rejane",
    "FABIANA": "Fabiana",
    "FABI": "Fabiana",
    "FABY": "Fabiana",
    "ANA MARIA": "Ana Maria",
    "LARISSA": "Larissa",
    "LARI": "Larissa",
    "ELISA": "Elisa",
    "VICTOR": "Victor",
    "WILSON": "Wilson",
    "ALESSANDER": "Alessander",
    "ALE": "Alessander",
    "MARCO": "Marco",
    "MARCO AURELIO": "Marco",
    "FERNANDA": "Fernanda",
    "DOUGLAS": "Douglas",
    "GILSON": "Gilson",
    "PRISCILA": "Priscila",
    "PRSCILA": "Priscila",
    "MÔNICA": "Mônica",
    "MONICA": "Mônica",
    "MÕNICA": "Mônica",
    "MÔNCA": "Mônica",
    "NEVES": "Jose Neves",
    "JOSE NEVES": "Jose Neves",
    "JOSÉ NEVES": "Jose Neves",
    "VANESSA": "Vanessa",
    "JOÃO RAPHAEL": "João Raphael",
    "ANDRE": "Andre",
    "ANDRÉ": "Andre",
    "ANDRE KOGUTTI": "Andre",
    "ALCINA": "Alcina",
    "FELIPE": "Felipe",
    "JHONATAN": "Jhonatan",
    "JHONATHAN": "Jhonatan",
    "CYNTIA": "Cyntia",
    "SILVIA": "Silvia",
    "LUCILÉIA": "Lucileia",
    "RITA": "Rita",
    "JOSE ALVES": "Jose Alves",
}

CORRETOR_ALIASES: dict[str, str] = {
    normalize_alias(raw): nome for raw, nome in CORRETOR_ALIAS_RAW.items()
}

# Composite-cell separators the importer splits on before resolving the
# first recognizable token (per the brief's own worked examples:
# "ZAP, IMOVEL WEB" / "GOOGLE/ WHATS" / "RETORNO/INSTAGRAM").
COMPOSITE_SEPARATORS = re.compile(r"[,/]")


__all__ = [
    "normalize_alias",
    "CANONICAL_SOURCES",
    "SOURCE_ALIAS_RAW",
    "SOURCE_ALIASES",
    "CANONICAL_CORRETORES",
    "CORRETOR_ALIAS_RAW",
    "CORRETOR_ALIASES",
    "COMPOSITE_SEPARATORS",
]
