"""CoreStudio rede x formato x assets validity matrix, as DATA (CORESTUDIO-STRUCTURE.md section 1.2).

Adding a network or a placement is a row in ``MATRIZ``, never an ``if``. ``validar_alvo`` is a pure function over
the matrix; the publicacoes service raises 422 with the first coded ``Motivo``; the FE reads ``matriz_publica()``
to grey out invalid targets.

Every row carries ``verificacao``. ``unverified`` means the numbers come from platform knowledge and were NOT
confirmed against the official docs listed in ``fonte`` (no network access in the slice that wrote this); flip a
row to ``verified`` only after reading its ``fonte``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

REDES = ("instagram", "facebook", "youtube")
FORMATOS = ("feed", "carrossel", "reel", "story", "short", "video_longo")
TIPOS_MIDIA = ("imagem", "video")
PROPORCOES = ("1:1", "4:5", "9:16", "16:9", "outra")

#: integration_accounts.provider that can publish to each rede.
PROVIDER_DA_REDE = {"instagram": "meta", "facebook": "meta", "youtube": "youtube"}

_FONTE_IG = "https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing"
_FONTE_FB = "https://developers.facebook.com/docs/pages-api/posts"
_FONTE_YT = "https://support.google.com/youtube/answer/10059070"

# Motivo codes (the 422 `code`).
REDE_DESCONHECIDA = "rede_desconhecida"
FORMATO_DESCONHECIDO = "formato_desconhecido"
FORMATO_INVALIDO_PARA_REDE = "formato_invalido_para_rede"
SEM_ASSETS = "sem_assets"
COMPOSICAO_INVALIDA = "composicao_invalida"
TIPO_MIDIA_INVALIDO = "tipo_midia_invalido"
PROPORCAO_INVALIDA = "proporcao_invalida"
PROPORCOES_MISTAS = "proporcoes_mistas"
DURACAO_EXCEDIDA = "duracao_excedida"
DURACAO_INSUFICIENTE = "duracao_insuficiente"


@dataclass(frozen=True)
class RegraFormato:
    rede: str
    formato: str
    assets_min: int
    assets_max: Optional[int]  # None = sem teto conhecido
    tipos: tuple[str, ...]  # tipos de midia aceitos por asset
    proporcoes: Optional[tuple[str, ...]]  # None = qualquer
    mesma_proporcao: bool = False  # todos os assets com a mesma proporcao
    duracao_min_s: Optional[float] = None  # por asset de video
    duracao_max_s: Optional[float] = None  # por asset de video
    verificacao: str = "unverified"  # verified | unverified
    fonte: str = ""
    nota: str = ""

    @property
    def composicao(self) -> tuple[str, ...]:
        if self.assets_max == 1:
            return ("unica",)
        if self.assets_min >= 2:
            return ("sequencia",)
        return ("unica", "sequencia")


MATRIZ: tuple[RegraFormato, ...] = (
    RegraFormato("instagram", "feed", 1, 1, ("imagem", "video"), ("1:1", "4:5"), fonte=_FONTE_IG),
    RegraFormato(
        "instagram", "carrossel", 2, 10, ("imagem", "video"), ("1:1", "4:5"), mesma_proporcao=True, fonte=_FONTE_IG,
        nota="2..10 itens via API (unverified); today's instagram_carousel (publish_service)",
    ),
    RegraFormato(
        "instagram", "reel", 1, 1, ("video",), ("9:16",), duracao_min_s=3, duracao_max_s=900, fonte=_FONTE_IG,
        nota="duracao 3s..15min (unverified; Meta has raised the cap over time)",
    ),
    RegraFormato("instagram", "story", 1, 1, ("imagem", "video"), ("9:16",), duracao_max_s=60, fonte=_FONTE_IG),
    RegraFormato(
        "facebook", "feed", 1, None, ("imagem", "video"), None, fonte=_FONTE_FB,
        nota="today's facebook_photo covers a single image only",
    ),
    RegraFormato("facebook", "reel", 1, 1, ("video",), ("9:16",), duracao_min_s=3, duracao_max_s=90, fonte=_FONTE_FB),
    RegraFormato("facebook", "story", 1, 1, ("imagem", "video"), ("9:16",), duracao_max_s=60, fonte=_FONTE_FB),
    RegraFormato(
        "youtube", "short", 1, 1, ("video",), ("9:16", "1:1"), duracao_max_s=180, fonte=_FONTE_YT,
        nota="Shorts up to 3 min since Oct 2024 (unverified)",
    ),
    RegraFormato("youtube", "video_longo", 1, 1, ("video",), ("16:9",), fonte=_FONTE_YT, nota="upload: modules/youtube/services/upload.py"),
)

_POR_ALVO = {(r.rede, r.formato): r for r in MATRIZ}


@dataclass(frozen=True)
class AssetFato:
    """What the validity check needs to know about one current asset (all read from the file)."""

    tipo_midia: str
    proporcao: str
    duracao_s: Optional[float] = None


@dataclass(frozen=True)
class Motivo:
    code: str
    detail: str
    extra: Optional[dict[str, Any]] = None

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, **(self.extra or {})}


def regra_para(rede: str, formato: str) -> Optional[RegraFormato]:
    return _POR_ALVO.get((rede, formato))


def composicao_de(assets: Iterable[AssetFato]) -> Optional[str]:
    n = len(list(assets))
    return None if n == 0 else ("unica" if n == 1 else "sequencia")


def validar_alvo(rede: str, formato: str, assets: list[AssetFato]) -> list[Motivo]:
    """Every reason a target is invalid; empty = valid. Order: structural first, then per-asset."""
    if rede not in REDES:
        return [Motivo(REDE_DESCONHECIDA, f"Rede desconhecida: {rede}")]
    if formato not in FORMATOS:
        return [Motivo(FORMATO_DESCONHECIDO, f"Formato desconhecido: {formato}")]
    regra = regra_para(rede, formato)
    if regra is None:
        return [Motivo(FORMATO_INVALIDO_PARA_REDE, f"{rede} não aceita o formato {formato}", {"rede": rede, "formato": formato})]
    if not assets:
        return [Motivo(SEM_ASSETS, "O post não tem mídia")]
    out: list[Motivo] = []
    n = len(assets)
    if n < regra.assets_min or (regra.assets_max is not None and n > regra.assets_max):
        out.append(Motivo(
            COMPOSICAO_INVALIDA, f"{rede}/{formato} aceita {regra.assets_min}..{regra.assets_max or 'N'} mídias; o post tem {n}",
            {"assets": n, "min": regra.assets_min, "max": regra.assets_max},
        ))
    for a in assets:
        if a.tipo_midia not in regra.tipos:
            out.append(Motivo(TIPO_MIDIA_INVALIDO, f"{rede}/{formato} não aceita {a.tipo_midia}", {"tipo_midia": a.tipo_midia, "aceitos": list(regra.tipos)}))
        if regra.proporcoes is not None and a.proporcao not in regra.proporcoes:
            out.append(Motivo(PROPORCAO_INVALIDA, f"{rede}/{formato} exige {', '.join(regra.proporcoes)}; a mídia é {a.proporcao}", {"proporcao": a.proporcao, "aceitas": list(regra.proporcoes)}))
        if a.tipo_midia == "video" and a.duracao_s is not None:
            if regra.duracao_max_s is not None and a.duracao_s > regra.duracao_max_s:
                out.append(Motivo(DURACAO_EXCEDIDA, f"Vídeo de {a.duracao_s:g}s excede {regra.duracao_max_s:g}s", {"duracao_s": a.duracao_s, "max_s": regra.duracao_max_s}))
            if regra.duracao_min_s is not None and a.duracao_s < regra.duracao_min_s:
                out.append(Motivo(DURACAO_INSUFICIENTE, f"Vídeo de {a.duracao_s:g}s é menor que {regra.duracao_min_s:g}s", {"duracao_s": a.duracao_s, "min_s": regra.duracao_min_s}))
    if regra.mesma_proporcao and len({a.proporcao for a in assets}) > 1:
        out.append(Motivo(PROPORCOES_MISTAS, "Todas as mídias do carrossel devem ter a mesma proporção"))
    return out


def classificar_proporcao(largura: int, altura: int) -> str:
    """The aspect-ratio bucket of a pixel size (±3%); anything else is ``outra``."""
    if largura <= 0 or altura <= 0:
        return "outra"
    r = largura / altura
    for nome, alvo in (("1:1", 1.0), ("4:5", 0.8), ("9:16", 9 / 16), ("16:9", 16 / 9)):
        if abs(r - alvo) / alvo <= 0.03:
            return nome
    return "outra"


def matriz_publica() -> list[dict[str, Any]]:
    """The matrix as JSON for the FE (greys out invalid targets) — every row, verification status included."""
    return [
        {
            "rede": r.rede, "formato": r.formato, "composicao": list(r.composicao),
            "assets_min": r.assets_min, "assets_max": r.assets_max, "tipos_midia": list(r.tipos),
            "proporcoes": list(r.proporcoes) if r.proporcoes else None, "mesma_proporcao": r.mesma_proporcao,
            "duracao_min_s": r.duracao_min_s, "duracao_max_s": r.duracao_max_s,
            "verificacao": r.verificacao, "fonte": r.fonte, "nota": r.nota,
            "provider_conta": PROVIDER_DA_REDE[r.rede],
        }
        for r in MATRIZ
    ]
