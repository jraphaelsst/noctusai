"""Generic illustration library: flat shapes as ImageMagick draw args on a 600x600 canvas.

Deliberately small and subject-neutral (person, book, cup, balloon, pencil, building,
car, card, index card). A product that needs more registers its own in `EXTRAS`
(name -> zero-arg callable returning magick args); nothing client-specific lives here.
Drawn at 2x by the engine (vector, never an upscaled raster).
"""
from __future__ import annotations

from typing import Callable

G, C, M, K = "#3A3733", "#6E6A63", "#9A958C", "#B3AEA4"   # ink / grey tones
L, P, T = "#EDE7DA", "#DCD2BD", "#A23A2E"                   # paper-light / paper / accent


def _fill(c: str) -> list[str]:
    return ["-fill", c]


def _stroke(c: str, w: int = 4) -> list[str]:
    return ["-stroke", c, "-strokewidth", str(w)] if c != "none" else ["-stroke", "none"]


def _draw(*prims: str) -> list[str]:
    out: list[str] = []
    for p in prims:
        out += ["-draw", p]
    return out


def pessoa() -> list[str]:
    cx, r = 300, 70
    hy = 130 + r
    return (_fill(C) + _stroke("none") + _draw(
        f"circle {cx},{hy} {cx},{hy - r}",
        f"roundrectangle {cx - 95},{hy + r + 14} {cx + 95},{hy + r + 400} 30,30"))


def livro() -> list[str]:
    return (_fill(G) + _stroke("none") + _draw("roundrectangle 150,60 470,540 10,10") + _fill(L)
            + _draw("rectangle 160,520 470,540") + _fill(C) + _draw("rectangle 150,60 185,540")
            + _stroke(K, 3) + ["-fill", "none"] + _draw("rectangle 225,140 430,250"))


def xicara() -> list[str]:
    x, y = 150, 250
    out = _fill(L) + _stroke(G, 5)
    out += _draw(f"ellipse {x + 110},{y + 175} 150,24 0,360",
                 f"polygon {x},{y} {x + 220},{y} {x + 190},{y + 150} {x + 30},{y + 150}")
    out += ["-fill", "none"] + _stroke(G, 12) + _draw(f"ellipse {x + 230},{y + 60} 34,44 270,90")
    out += _stroke(C, 5) + _draw(f"bezier {x + 80},{y - 30} {x + 60},{y - 70} {x + 100},{y - 90} {x + 80},{y - 130}",
                                 f"bezier {x + 140},{y - 30} {x + 120},{y - 70} {x + 160},{y - 90} {x + 140},{y - 130}")
    return out


def balao() -> list[str]:
    x, y, w, h = 80, 120, 440, 260
    return (_fill(L) + _stroke(G, 5) + _draw(f"roundrectangle {x},{y} {x + w},{y + h} 40,40",
                                            f"polygon {x + 70},{y + h - 3} {x + 50},{y + h + 60} {x + 130},{y + h - 3}")
            + _stroke("none") + _fill(L) + _draw(f"rectangle {x + 72},{y + h - 8} {x + 128},{y + h - 2}"))


def lapis() -> list[str]:
    def rot(a: int, prim: str) -> str:
        return f"push graphic-context translate 120,420 rotate {a} {prim} pop graphic-context"
    return (_fill(T) + _stroke(G, 3) + _draw(rot(-35, "rectangle 0,-14 330,14")) + _fill("#E8D2A6")
            + _draw(rot(-35, "polygon 330,-14 375,0 330,14")) + _fill(G) + _stroke("none")
            + _draw(rot(-35, "polygon 360,-5 375,0 360,5")))


def predio() -> list[str]:
    x, y = 190, 110
    out = _fill(K) + _stroke(G, 4) + _draw(f"rectangle {x},{y} {x + 200},{y + 380}")
    for r in range(4):
        for c in range(2):
            out += _fill(L) + _draw(f"rectangle {x + 30 + c * 90},{y + 30 + r * 70} {x + 80 + c * 90},{y + 75 + r * 70}")
    return out + _fill(G) + _draw(f"rectangle {x + 70},{y + 310} {x + 130},{y + 380}")


def carro() -> list[str]:
    x, y = 120, 320
    return (_fill(C) + _stroke(G, 4) + _draw(f"roundrectangle {x},{y} {x + 330},{y + 90} 26,26",
                                             f"polygon {x + 60},{y} {x + 110},{y - 70} {x + 240},{y - 70} {x + 290},{y}")
            + _fill(G) + _draw(f"circle {x + 75},{y + 95} {x + 75},{y + 50}", f"circle {x + 255},{y + 95} {x + 255},{y + 50}")
            + _fill(M) + _stroke("none") + _draw(f"circle {x + 75},{y + 95} {x + 75},{y + 75}",
                                                 f"circle {x + 255},{y + 95} {x + 255},{y + 75}"))


def cartao() -> list[str]:
    return _fill(L) + _stroke(G, 4) + _draw("rectangle 70,150 530,450") + _stroke(T, 4) + _draw("line 70,220 530,220")


def ficha() -> list[str]:
    out = _fill(L) + _stroke(G, 4) + _draw("rectangle 60,80 540,520") + _stroke(T, 4) + _draw("line 60,150 540,150")
    out += _stroke(K, 3)
    for i in range(7):
        yy = 200 + i * 45
        if yy < 500:
            out += _draw(f"line 90,{yy} 510,{yy}")
    return out


FORMAS: dict[str, Callable[[], list[str]]] = {
    "pessoa": pessoa, "livro": livro, "xicara": xicara, "balao": balao, "lapis": lapis,
    "predio": predio, "carro": carro, "cartao": cartao, "ficha": ficha,
}
EXTRAS: dict[str, Callable[[], list[str]]] = {}


def formas() -> dict[str, Callable[[], list[str]]]:
    return {**FORMAS, **EXTRAS}
