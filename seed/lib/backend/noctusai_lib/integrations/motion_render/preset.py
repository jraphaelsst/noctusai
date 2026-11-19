"""Preset `papel-explainer` v2: tokens, geometry and font resolution (data only).

Geometry is in px on a 1080x1920 canvas BEFORE the 4 % zoom (already discounted so
the zoomed content stays inside the safe zone). The safe-zone table is a conservative
placeholder, not the platforms' official numbers.
"""
from __future__ import annotations

import functools
import shutil
import subprocess

PRESET = {"id": "papel-explainer", "versao": 2}
PRESETS_SUPORTADOS = {"papel-explainer"}

W, H, FPS = 1080, 1920, 30
CAUDA_S = 2.0
ZOOM = 0.04            # per-scene approach 100 -> 104 %
IL_LARG = 788          # illustration max width (content ~71 % of the canvas)
IL_MIN_PCT = 70
LEG_TOPO = 1396        # caption box top (bottom <= 1498 = 78 % of the height)
AREA = dict(x0=86, x1=934, y0=262, y1=1360)
ZONA = dict(x0=65, x1=950, y0=230, y1=1498)
FOLGA_AAC_DB = 1.0     # AAC raises the true peak ~0.7 dB after loudnorm: normalise with headroom
ALVO_LUFS, PICO_DBTP = -14.0, -1.5

PAPEL, VINHETA = "#F0E6D2", "#C4B394"
INT_BASE, INT_VINH = "#4A5262", "#2B303A"
TINTA, TINTA_INT = "#1E1A16", "#EFE8D8"
TIJOLO, FITA, GRAFITE, CINZA = "#A23A2E", "#F4EEDF", "#3A3733", "#6E6A63"
CAIXA, CAIXA_TXT = "#141210", "#F6F2E8"

# font role -> candidates in preference order (ImageMagick font name or a .ttf path)
FONTES = {
    "titulo": ["Georgia-Bold", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "Liberation-Serif-Bold",
               "DejaVu-Serif-Bold"],
    "texto": ["American-Typewriter", "Liberation-Mono", "DejaVu-Sans-Mono"],
    "anotacao": ["Noteworthy-Bold", "Liberation-Sans-Bold", "DejaVu-Sans-Bold"],
}


@functools.lru_cache(maxsize=1)
def fontes_instaladas() -> frozenset[str]:
    """Names and file paths ImageMagick knows (empty when `magick` is absent)."""
    if not shutil.which("magick"):
        return frozenset()
    out = subprocess.run(["magick", "-list", "font"], capture_output=True, text=True).stdout
    achados: set[str] = set()
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.startswith("Font:"):
            achados.add(ln.split(":", 1)[1].strip())
        elif ln.startswith("glyphs:"):
            achados.add(ln.split(":", 1)[1].strip())
    return frozenset(achados)


def resolver_fontes() -> tuple[dict, dict]:
    """-> (role -> font to pass to magick or None = ImageMagick default, role -> whether a fallback was used)."""
    inst = fontes_instaladas()
    escolha, fallback = {}, {}
    for papel, cands in FONTES.items():
        achada = next((c for c in cands if c in inst), None)
        escolha[papel] = achada
        fallback[papel] = achada != cands[0]
    return escolha, fallback
