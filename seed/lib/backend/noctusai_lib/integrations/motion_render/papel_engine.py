"""Preset `papel-explainer` v2 engine: paper background, typography, spoken-word caption,
label / circle / strike marks, per-scene zoom, cuts, two-pass loudness, safe-zone check.

ImageMagick (`magick`) draws every still; ffmpeg assembles, encodes and measures. Everything
here is subject-neutral -- the script, names and illustrations come from the caller's spec.
All measurements are taken on the ENCODED mp4.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from noctusai_lib.integrations.motion_render import preset as P
from noctusai_lib.integrations.motion_render.retime import normaliza
from noctusai_lib.integrations.motion_render.shapes import formas
from noctusai_lib.integrations.motion_render.types import (
    FerramentaAusente,
    LoudnessForaDoAlvo,
    MotionRenderError,
    RenderResult,
    SpecInvalida,
)

PNG = ["-define", "png:compression-level=1"]


def quadro_de(t: float, fps: int = P.FPS) -> int:
    """Frame a scene starts on: ffmpeg's fps filter rounds half UP (Python's round() is half-even and
    lands a frame early on x.5 boundaries)."""
    return int(t * fps + 0.5)


def titulo_grande(b: dict) -> bool:
    """Rule r2: a big title only when the text has a digit or the beat marks `chave`."""
    t = b.get("titulo")
    return bool(t) and (bool(re.search(r"\d", t)) or bool(b.get("chave")))


def agrupar_legenda(palavras: list[dict]) -> list[dict]:
    """Caption groups: <= 5 words, <= 26 chars, never crossing a sentence."""
    grupos: list[list[int]] = []
    g: list[int] = []
    for i, p in enumerate(palavras):
        if g and (len(g) >= 5 or len(" ".join(palavras[j]["texto"] for j in g + [i])) > 26):
            grupos.append(g)
            g = []
        g.append(i)
        if re.search(r"[.?!][\"”]?$", p["texto"]) or (re.search(r"[,:;]$", p["texto"]) and len(g) >= 3):
            grupos.append(g)
            g = []
    if g:
        grupos.append(g)
    return [{"id": f"g{n}", "palavra_ids": [palavras[j]["id"] for j in gr]} for n, gr in enumerate(grupos)]


class PapelEngine:
    def __init__(self, out_dir: str, *, wall=time.monotonic) -> None:
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="papel-", dir=self.out))
        self.cache = self._tmp / "cache"
        self.cache.mkdir()
        self.fontes, self.fontes_fallback = P.resolver_fontes()
        self._il = formas()
        self._espaco: dict[int, int] = {}
        self._wall = wall

    # ── subprocess ───────────────────────────────────────────────────────
    @staticmethod
    def run(args: list, **kw) -> str:
        try:
            r = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kw)
        except FileNotFoundError as exc:
            raise FerramentaAusente(
                f"`{args[0]}` not found on PATH -- build the image FROM noctus-seed-backend-media-base "
                "(it ships ffmpeg + ImageMagick + the preset fonts)") from exc
        if r.returncode != 0:
            raise MotionRenderError(f"`{args[0]}` falhou (rc={r.returncode}): {r.stderr[-600:]}", codigo="render_falhou")
        return r.stdout

    def _font(self, papel: str) -> list[str]:
        f = self.fontes.get(papel)
        return ["-font", f] if f else []

    def _cache(self, nome: str, *partes) -> str:
        h = hashlib.sha1(json.dumps([nome, *partes], ensure_ascii=False, sort_keys=True, default=str).encode(), usedforsecurity=False).hexdigest()[:16]
        return str(self.cache / f"{nome}-{h}.png")

    def dim(self, p: str) -> tuple[int, int]:
        w, h = self.run(["magick", "identify", "-format", "%w %h", p]).split()
        return int(w), int(h)

    # ── stills ───────────────────────────────────────────────────────────
    def fundo(self, tipo: str) -> str:
        o = self._cache("fundo", tipo)
        if Path(o).exists():
            return o
        base, vin = (P.PAPEL, P.VINHETA) if tipo == "papel" else (P.INT_BASE, P.INT_VINH)
        W, H = P.W, P.H
        self.run(["magick", "-seed", "7", "-size", f"{W}x{H}", f"xc:{base}", "-attenuate", "0.18", "+noise", "Gaussian",
                  "-blur", "0x0.6",
                  "(", "-size", f"{W}x{H}", "plasma:fractal", "-colorspace", "gray", "-blur", "0x6", "-level", "30%,70%",
                  "-evaluate", "multiply", "0.08", "-evaluate", "add", "92%", ")", "-compose", "multiply", "-composite",
                  "(", "-size", f"{W * 14 // 10}x{H * 14 // 10}", f"radial-gradient:white-{vin}", "-gravity", "center",
                  "-crop", f"{W}x{H}+0+0", "+repage", ")", "-compose", "multiply", "-composite",
                  "-alpha", "off", "-depth", "8"] + PNG + [o])
        return o

    def _largura_texto(self, papel: str, pt: int, texto: str) -> int:
        return int(self.run(["magick", *self._font(papel), "-pointsize", str(pt), f"label:{texto}", "-format", "%w", "info:"]))

    def titulo(self, texto: str, interior: bool, maxw: int = 800, pt: Optional[int] = None) -> str:
        n = len(texto)
        if pt is None:
            pt = 170 if n <= 10 else 150 if n <= 16 else 125 if n <= 24 else 105 if n <= 34 else 90
        maior = max(texto.split(), key=len)
        while pt > 60 and self._largura_texto("titulo", pt, maior) > maxw - 20:  # never break a word mid-way
            pt -= 6
        o = self._cache("tit", texto, interior, maxw, pt, self.fontes["titulo"])
        if not Path(o).exists():
            self.run(["magick", "-background", "none", "-fill", P.TINTA_INT if interior else P.TINTA, *self._font("titulo"),
                      "-pointsize", str(pt), "-size", f"{maxw}x", "-gravity", "center", "-interline-spacing", "-12",
                      f"caption:{texto}", "-trim", "+repage"] + PNG + [o])
        return o

    def _sombra(self, args_antes: list, o: str, sombra: str = "30x4+3+5") -> None:
        self.run(["magick", *args_antes, "-background", "none", "(", "+clone", "-background", "#000000", "-shadow", sombra, ")",
                  "+swap", "-background", "none", "-layers", "merge", "+repage"] + PNG + [o])

    def fita(self, texto: str, ang: int) -> str:
        o = self._cache("fita", texto, ang, self.fontes["anotacao"])
        if not Path(o).exists():
            self._sombra(["-background", P.FITA, "-fill", P.TIJOLO, *self._font("anotacao"), "-pointsize", "54",
                          f"label:{texto}", "-bordercolor", P.FITA, "-border", "26x12", "-background", "none",
                          "-rotate", str(ang)], o)
        return o

    def tag(self, texto: str, pt: int = 46) -> str:
        o = self._cache("tag", texto, pt, self.fontes["anotacao"])
        if not Path(o).exists():
            self._sombra(["-background", P.TIJOLO, "-fill", P.FITA, *self._font("anotacao"), "-pointsize", str(pt),
                          f"label:{texto}", "-bordercolor", P.TIJOLO, "-border", "18x4", "-background", "none",
                          "-rotate", "-3"], o, "30x3+2+4")
        return o

    def ilustra(self, nome: str, tam: int, alt: int) -> str:
        if nome not in self._il:
            raise SpecInvalida(f"ilustracao desconhecida: {nome!r} (formas: {sorted(self._il)})")
        args = self._il[nome]()
        o = self._cache("il", nome, tam, alt, args)
        if not Path(o).exists():
            bruto = o.replace(".png", "-bruto.png")
            self.run(["magick", "-size", "1200x1200", "xc:none", "-draw", "affine 2,0,0,2,0,0"] + args
                     + ["-trim", "+repage", bruto])
            self.run(["magick", bruto, "-bordercolor", "none", "-border", "24",
                      "(", "+clone", "-alpha", "extract", "-morphology", "Dilate", "Disk:16", "-background", P.FITA,
                      "-alpha", "shape", ")", "+swap", "-background", "none", "-compose", "over", "-flatten",
                      "-resize", f"{tam}x{alt}",
                      "(", "+clone", "-background", "#000000", "-shadow", "35x7+5+9", ")", "+swap", "-background", "none",
                      "-layers", "merge", "+repage"] + PNG + [o])
            Path(bruto).unlink()
        return o

    def ficha_autor(self, texto: str, ang: int = -3) -> str:
        """Ruled index card quoting a source."""
        o = self._cache("fautor", texto, ang, self.fontes["texto"])
        if not Path(o).exists():
            t_ = str(self.cache / "tmp-fautor.png")
            self.run(["magick", "-background", "none", "-fill", P.GRAFITE, *self._font("texto"), "-pointsize", "40",
                      f"label:{texto}"] + PNG + [t_])
            w, hh = self.dim(t_)
            W_, H_ = w + 64, hh + 62
            lin = " ".join(f"line 16,{y} {W_ - 16},{y}" for y in range(30 + hh, H_ - 4, 16))
            self.run(["magick", "-size", f"{W_}x{H_}", f"xc:{P.FITA}", "-stroke", "#B9B2A4", "-strokewidth", "2", "-draw", lin,
                      "-stroke", P.TIJOLO, "-strokewidth", "3", "-draw", f"line 0,18 {W_},18",
                      "-stroke", P.GRAFITE, "-strokewidth", "2", "-fill", "none", "-draw", f"rectangle 0,0 {W_ - 1},{H_ - 1}",
                      t_, "-gravity", "northwest", "-geometry", "+32+24", "-compose", "over", "-composite",
                      "-background", "none", "-rotate", str(ang),
                      "(", "+clone", "-background", "#000000", "-shadow", "30x4+3+5", ")", "+swap", "-background", "none",
                      "-layers", "merge", "+repage"] + PNG + [o])
            Path(t_).unlink()
        return o

    @staticmethod
    def marca(tipo: str, c: dict) -> list:
        """Hand-drawn circle (double ellipse) or strike over box `c`; returns magick draw args."""
        x0, y0, x1, y1 = c["x0"], c["y0"], c["x1"], c["y1"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if tipo == "circulo":
            rx, ry = (x1 - x0) / 2 + 34, (y1 - y0) / 2 + 26
            return ["-fill", "none", "-stroke", P.TIJOLO, "-strokewidth", "6",
                    "-draw", f"push graphic-context translate {cx:.0f},{cy:.0f} rotate -4 ellipse 0,0 {rx:.0f},{ry:.0f} 15,350 pop graphic-context",
                    "-strokewidth", "4",
                    "-draw", f"push graphic-context translate {cx + 5:.0f},{cy - 3:.0f} rotate -1 ellipse 0,0 {rx + 6:.0f},{ry + 4:.0f} 300,400 pop graphic-context"]
        return ["-fill", "none", "-stroke", P.TIJOLO, "-strokewidth", "9", "-draw", f"line {x0 - 14},{cy + 8:.0f} {x1 + 14},{cy - 6:.0f}",
                "-strokewidth", "5", "-draw", f"line {x0 - 6},{cy + 16:.0f} {x1 + 10},{cy + 2:.0f}"]

    def bbox(self, img: str, ref: str) -> Optional[dict]:
        out = self.run(["magick", img, "-alpha", "off", "(", ref, "-alpha", "off", ")", "-compose", "difference", "-composite",
                        "-colorspace", "gray", "-threshold", "6%", "-format", "%@", "info:"]).strip()
        w, hh, x, y = map(int, re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", out).groups())
        return dict(x0=x, y0=y, x1=x + w, y1=y + hh) if w > 1 else None

    def bbox_alpha(self, img: str) -> dict:
        out = self.run(["magick", img, "-alpha", "extract", "-threshold", "10%", "-format", "%@", "info:"]).strip()
        w, hh, x, y = map(int, re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", out).groups())
        return dict(x0=x, y0=y, x1=x + w, y1=y + hh)

    # ── composition (one beat) ───────────────────────────────────────────
    def compor(self, b: dict, fundo_tipo: str, saida: str) -> tuple[str, dict]:
        W = P.W
        A = P.AREA
        interior = fundo_tipo == "interior"
        bg = self.fundo(fundo_tipo)
        camadas: list[tuple[str, int, int]] = []
        caixas: dict[str, dict] = {}
        desenhos: list = []
        med = {"titulo_grande": None, "il_larg_pct": None}

        def poe(p: str, x: float, y: float, chave: Optional[str] = None) -> None:
            w, hh = self.dim(p)
            camadas.append((p, int(x), int(y)))
            if chave:
                caixas[chave] = dict(x0=int(x), y0=int(y), x1=int(x) + w, y1=int(y) + hh)

        y = A["y0"] + 8
        if titulo_grande(b):
            for pt in (None, 120, 108, 96, 84):  # the title yields size before the illustration drops under 70 % width
                p = self.titulo(b["titulo"], interior, maxw=P.IL_LARG, pt=pt)
                w, hh = self.dim(p)
                if not b.get("ilustracao"):
                    break
                pil = self.ilustra(b["ilustracao"], P.IL_LARG, A["y1"] - (y + hh + 34))
                bi = self.bbox_alpha(pil)
                if 100 * (bi["x1"] - bi["x0"]) / W >= P.IL_MIN_PCT:
                    break
            poe(p, (W - w) / 2, y)
            med["titulo_grande"] = True
            y += hh + 34
        if b.get("ilustracao"):
            alt = A["y1"] - y
            p = self.ilustra(b["ilustracao"], P.IL_LARG, alt)
            w, hh = self.dim(p)
            poe(p, (W - w) / 2, y + (alt - hh) // 2, "il")
            bi = self.bbox_alpha(p)
            med["il_larg_pct"] = round(100 * (bi["x1"] - bi["x0"]) / W, 1)
            ilb = caixas["il"]
        else:
            ilb = dict(x0=A["x0"] + 120, y0=y, x1=A["x1"] - 120, y1=min(y + 420, A["y1"]))
            med["il_larg_pct"] = "sem_ilustracao"
        if b.get("ficha"):
            p = self.ficha_autor(b["ficha"])
            w, hh = self.dim(p)
            poe(p, max(A["x0"], ilb["x0"] - 16), max(y - 6, ilb["y0"] - hh // 3), b["ficha"])
        for i, e in enumerate((b.get("etiquetas") or [])[:2]):
            p = self.fita(e, -4 if i == 0 else 3)
            w, hh = self.dim(p)
            folga = 52 if b.get("circulo") == e else 18 if b.get("riscado") == e else 0  # the mark overshoots the label
            x = min(A["x1"] - w - folga, ilb["x1"] - w + 30)
            yy = max(y, ilb["y0"] + 40) if i == 0 else min(A["y1"] - hh, ilb["y1"] - hh - 24)
            poe(p, x, yy, e)
        if b.get("tag"):
            p = self.tag(b["tag"])
            w, hh = self.dim(p)
            poe(p, max(A["x0"], ilb["x0"] - 10), min(A["y1"] - hh, ilb["y1"] - hh - 10), "tag:" + b["tag"])
        for campo, tipo in (("circulo", "circulo"), ("riscado", "riscado")):
            if b.get(campo):
                if b[campo] not in caixas:
                    raise SpecInvalida(f"{tipo}: alvo nao esta na batida (alvos: {[k for k in caixas if k != 'il']})")
                desenhos += self.marca(tipo, caixas[b[campo]])
        args = ["magick", bg]
        for p, x, yy in camadas:
            args += [p, "-gravity", "northwest", "-geometry", f"+{x}+{yy}", "-compose", "over", "-composite"]
        self.run(args + ["-gravity", "northwest"] + desenhos + ["-alpha", "off", "-depth", "8"] + PNG + [saida])
        return bg, med

    # ── caption ──────────────────────────────────────────────────────────
    def legenda_png(self, palavras: list[str], k: int) -> str:
        """One line on a dark box, brick-coloured underline under word k (the one being spoken)."""
        o = self._cache("leg", palavras, k, self.fontes["texto"])
        if Path(o).exists():
            return o
        pt = 48
        while True:
            ws = [self._largura_texto("texto", pt, w) for w in palavras]
            if pt not in self._espaco:
                self._espaco[pt] = self._largura_texto("texto", pt, "x x") - 2 * self._largura_texto("texto", pt, "x")
            if sum(ws) + self._espaco[pt] * (len(ws) - 1) + 48 <= 860 or pt <= 34:
                break
            pt -= 2
        hh = int(self.run(["magick", *self._font("texto"), "-pointsize", str(pt), "label:Ág", "-format", "%h", "info:"]))
        larg = sum(ws) + self._espaco[pt] * (len(ws) - 1) + 48
        alt = 12 + hh + 4 + 6 + 10
        args = ["magick", "-size", f"{larg}x{alt}", f"xc:{P.CAIXA}"]
        x = 24
        for i, (w, lw) in enumerate(zip(palavras, ws)):
            args += ["(", "-background", P.CAIXA, "-fill", P.CAIXA_TXT, *self._font("texto"), "-pointsize", str(pt),
                     f"label:{w}", ")", "-gravity", "northwest", "-geometry", f"+{x}+12", "-compose", "over", "-composite"]
            if i == k:
                args += ["-fill", P.TIJOLO, "-stroke", "none", "-draw", f"rectangle {x},{12 + hh + 4} {x + lw - 1},{12 + hh + 9}"]
            x += lw + self._espaco[pt]
        caixa = o.replace(".png", "-caixa.png")
        self.run(args + PNG + [caixa])
        self.run(["magick", "-size", f"{P.W}x{P.H}", "xc:none", caixa, "-gravity", "north", "-geometry", f"+0+{P.LEG_TOPO}",
                  "-compose", "over", "-composite"] + PNG + [o])
        Path(caixa).unlink()
        return o

    # ── geometry ─────────────────────────────────────────────────────────
    @staticmethod
    def zoom_caixa(bb: dict, f: float = 1 + P.ZOOM) -> dict:
        cx, cy = P.W // 2, P.H // 2
        return dict(x0=int(cx + (bb["x0"] - cx) * f), y0=int(cy + (bb["y0"] - cy) * f),
                    x1=int(round(cx + (bb["x1"] - cx) * f + 0.5)), y1=int(round(cy + (bb["y1"] - cy) * f + 0.5)))

    @staticmethod
    def viola(bb: dict, z: dict) -> list[str]:
        v = []
        if bb["x0"] < z["x0"]:
            v.append(f"esquerda {z['x0'] - bb['x0']} px")
        if bb["x1"] > z["x1"]:
            v.append(f"direita {bb['x1'] - z['x1']} px")
        if bb["y0"] < z["y0"]:
            v.append(f"topo {z['y0'] - bb['y0']} px")
        if bb["y1"] > z["y1"]:
            v.append(f"base {bb['y1'] - z['y1']} px")
        return v

    @staticmethod
    def zoom_expr(ini: list[float], fins: list[float], fps: int = P.FPS) -> dict:
        """perspective() corners for 100 -> 104 % per scene, in FRAMES (same rounding as the fps filter on the concat)."""
        n = "(in-1)"  # measured: `in` is 1 on the first frame
        p = "1"
        for s_, e_ in reversed(list(zip(ini, fins))):
            qs, qe = quadro_de(s_, fps), quadro_de(e_, fps)
            p = f"if(lt({n},{qe}),max(0,({n}-{qs})/{max(qe - qs, 1)}),{p})"
        a = f"((1-1/(1+{P.ZOOM}*({p})))/2)"
        return {"x0": f"W*{a}", "y0": f"H*{a}", "x1": f"W*(1-{a})", "y1": f"H*{a}",
                "x2": f"W*{a}", "y2": f"H*(1-{a})", "x3": f"W*(1-{a})", "y3": f"H*(1-{a})"}

    def transicao(self, a: str, b: str, tipo: str, idx: int) -> list[str]:
        n = {"fade": 8}.get(tipo, 0)  # hard cut by default
        quadros = []
        for k in range(1, n):
            o = str(self._tmp / f"t{idx:03d}-{k:02d}.png")
            self.run(["magick", a, b, "-define", f"compose:args={100 * k / n:.1f}", "-compose", "blend", "-composite",
                      "-alpha", "off"] + PNG + [o])
            quadros.append(o)
        return quadros

    def salto_no_quadro(self, mp4: str, k: int) -> list[float]:
        """RMSE between neighbouring frames of k (area above the caption)."""
        pref = str(self._tmp / f"sinc{k}-")
        self.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", mp4, "-vf",
                  f"select='between(n\\,{max(k - 2, 0)}\\,{k + 1})',crop={P.W}:{P.LEG_TOPO - 16}:0:0",
                  "-fps_mode", "passthrough", pref + "%d.png"])
        fs = sorted(Path(self._tmp).glob(f"sinc{k}-*.png"))
        out = []
        for x, y in zip(fs, fs[1:]):
            r = subprocess.run(["magick", "compare", "-metric", "RMSE", str(x), str(y), "null:"], capture_output=True, text=True).stderr
            out.append(float(re.search(r"\(([\d.e-]+)\)", r).group(1)))
        for f_ in fs:
            f_.unlink()
        return out

    # ── audio ────────────────────────────────────────────────────────────
    def audio_normalizado(self, src: str, alvo: dict, total: float) -> str:
        """Two-pass loudnorm (-14 LUFS / -1.5 dBTP), mono -> stereo BEFORE measuring, padded to the video end."""
        ln = f"loudnorm=I={alvo['alvo_lufs']}:TP={alvo['pico_dbtp'] - P.FOLGA_AAC_DB}:LRA=11"
        est = "aresample=48000,pan=stereo|c0=c0|c1=c0"  # stereo first: duplicating after measuring would add +3 LU
        m = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", f"{est},{ln}:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        try:
            j = json.loads(m[m.rindex("{"):m.rindex("}") + 1])
        except ValueError as exc:
            raise MotionRenderError("loudnorm nao mediu o audio (arquivo ilegivel?)", codigo="audio_ilegivel") from exc
        ln2 = (ln + f":measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
               f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
        out = str(self._tmp / "narracao.wav")
        self.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af",
                  f"{est},{ln2},aresample=48000,apad=whole_dur={total:.3f}", "-t", f"{total:.3f}", out])
        return out

    # ── the render ───────────────────────────────────────────────────────
    def render(self, spec: dict, audio_path: Optional[str]) -> RenderResult:
        try:
            return self._render(spec, audio_path)
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def _render(self, spec: dict, audio_path: Optional[str]) -> RenderResult:
        t0 = self._wall()
        FPS = P.FPS
        pal = {w["id"]: w for w in spec.get("palavras") or []}
        cenas = spec.get("cenas") or []
        if not pal or not cenas:
            raise SpecInvalida("spec precisa de palavras e cenas")
        self._rotulos_literais(spec)
        fala_fim = max(w["fim_s"] for w in pal.values())
        total = round(fala_fim + spec.get("cauda_s", P.CAUDA_S), 3)
        ini = [0.0 if i == 0 else pal[c["ancora"]["palavra_id"]]["inicio_s"] for i, c in enumerate(cenas)]
        fins = ini[1:] + [total]
        batidas = []  # (t, estado, fundo, transicao, cena)
        for i, c in enumerate(cenas):
            estado: dict = {}
            for j, b in enumerate(c["batidas"]):
                if j == 0:
                    t = ini[i]
                elif "palavra_id" in b["ancora"]:
                    t = pal[b["ancora"]["palavra_id"]]["inicio_s"]
                else:
                    t = ini[i] + b["ancora"]["fracao_da_cena"] * (fins[i] - ini[i])
                estado = {**estado, **{k: v for k, v in b.items() if k != "ancora"}}
                for k in ("circulo", "riscado"):  # marks live only on the beat that names them
                    if k not in b:
                        estado.pop(k, None)
                batidas.append((t, dict(estado), c.get("fundo", "papel"), c.get("transicao", "corte") if j == 0 else "corte", c["id"]))
        viol, imgs, regra_il = [], [], []
        for k, (t, est, fb, tr, cid) in enumerate(batidas):
            o = str(self._tmp / f"b{k:03d}.png")
            bg, med = self.compor(est, fb, o)
            bb = self.bbox(o, bg)
            if bb:
                v = self.viola(self.zoom_caixa(bb), P.ZONA)
                if v:
                    viol.append({"elemento": f"batida {k} ({cid})", "violacao": v})
            pct = med["il_larg_pct"]
            regra_il.append({"batida": k, "largura_pct": pct, "ok": not isinstance(pct, (int, float)) or pct >= P.IL_MIN_PCT})
            imgs.append(o)
        linhas = []
        for k, (t, est, fb, tr, cid) in enumerate(batidas):
            fim = batidas[k + 1][0] if k + 1 < len(batidas) else total
            dur = fim - t
            if k > 0 and tr == "fade":
                qs = self.transicao(imgs[k - 1], imgs[k], tr, k)
                for q in qs:
                    linhas += [f"file '{q}'", f"duration {1 / FPS:.6f}"]
                dur -= len(qs) / FPS
            linhas += [f"file '{imgs[k]}'", f"duration {max(dur, 1 / FPS):.6f}"]
        linhas += [f"file '{imgs[-1]}'"]
        (self._tmp / "base.txt").write_text("\n".join(linhas) + "\n")

        grupos = spec.get("grupos") or agrupar_legenda(list(spec["palavras"]))
        gt = []
        for n, g in enumerate(grupos):
            a = 0.0 if n == 0 else pal[g["palavra_ids"][0]]["inicio_s"]  # hook: caption already on frame 0
            b = pal[grupos[n + 1]["palavra_ids"][0]]["inicio_s"] if n + 1 < len(grupos) else total
            gt.append((a, b, g))
        leg, caixas_leg, cur, p = [], [], 0.0, None
        for a, b, g in gt:
            palavras = [pal[w]["texto"] for w in g["palavra_ids"]]
            for k, wid in enumerate(g["palavra_ids"]):
                wa = a if k == 0 else max(cur, pal[wid]["inicio_s"])
                wb = b if k + 1 == len(palavras) else max(wa, pal[g["palavra_ids"][k + 1]]["inicio_s"])
                if wb - wa <= 1e-4:
                    continue
                p = self.legenda_png(palavras, k)
                leg += [f"file '{p}'", f"duration {wb - wa:.6f}"]
                cur = wb
            if p:
                caixas_leg.append(self.bbox_alpha(p))
        leg += [f"file '{p}'"]
        (self._tmp / "leg.txt").write_text("\n".join(leg) + "\n")
        for cb in caixas_leg:
            v = self.viola(cb, P.ZONA)
            if v:
                viol.append({"elemento": "legenda", "violacao": v})

        def ts(x: float) -> str:
            ms = int(round(x * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        srt = [f"{n}\n{ts(a)} --> {ts(b if n < len(gt) else fala_fim + 1.0)}\n"
               + " ".join(pal[w]["texto"] for w in g["palavra_ids"]) + "\n" for n, (a, b, g) in enumerate(gt, 1)]
        srt_path = self.out / "legenda.srt"
        srt_path.write_text("\n".join(srt), encoding="utf-8")

        mp4 = self.out / "final.mp4"
        alvo = {"alvo_lufs": P.ALVO_LUFS, "pico_dbtp": P.PICO_DBTP, **(spec.get("audio", {}).get("loudness") or {})}
        narrado = audio_path is not None
        a_in = ["-i", self.audio_normalizado(audio_path, alvo, total)] if narrado else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        z = self.zoom_expr(ini, fins)
        persp = "perspective=" + ":".join(f"{k}='{v}'" for k, v in z.items()) + ":interpolation=cubic:sense=source:eval=frame"
        fc = (f"[0:v]fps={FPS},format=gbrp,{persp},format=rgb24[b];[1:v]fps={FPS},format=rgba[c];"
              f"[b][c]overlay=0:0:format=auto:shortest=0,format=yuv420p[v]")
        (self._tmp / "fc.txt").write_text(fc)
        self.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", self._tmp / "base.txt",
                  "-f", "concat", "-safe", "0", "-i", self._tmp / "leg.txt", *a_in,
                  "-filter_complex_script", self._tmp / "fc.txt", "-map", "[v]", "-map", "2:a", "-t", f"{total:.3f}",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(FPS), "-c:a", "aac",
                  "-b:a", "192k" if narrado else "128k", "-movflags", "+faststart", mp4])

        lufs = tp = None
        if narrado:
            eb = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"],
                                capture_output=True, text=True).stderr.split("Summary:")[-1]
            lufs = float(re.search(r"I:\s+(\S+) LUFS", eb).group(1))
            tp = float(re.search(r"Peak:\s+(\S+) dBFS", eb).group(1))
            if tp > alvo["pico_dbtp"] or abs(lufs - alvo["alvo_lufs"]) > 1.0:
                raise LoudnessForaDoAlvo(
                    f"loudness fora do alvo no mp4 final: {lufs} LUFS / {tp} dBTP (alvo {alvo['alvo_lufs']} / {alvo['pico_dbtp']})")

        sinc = []
        for i, c in enumerate(cenas[1:], 1):
            k = quadro_de(ini[i], FPS)
            d = self.salto_no_quadro(str(mp4), k)
            ok = len(d) == 3 and d[1] > 3 * d[0] and (c.get("transicao") == "fade" or d[1] > 3 * d[2])
            sinc.append({"cena": c["id"], "quadro": k, "rmse_vizinhos": [round(x, 4) for x in d], "ok": ok})

        qdir = self.out / "quadros-chave"
        shutil.rmtree(qdir, ignore_errors=True)
        qdir.mkdir()
        quadros = [str(qdir / "q00.png")]
        self.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", mp4, "-frames:v", "1", quadros[0]])
        for i, c in enumerate(cenas):
            t = (ini[i] + fins[i]) / 2
            q = str(qdir / f"q{i + 1:02d}-{c['id']}.jpg")
            self.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", mp4, "-frames:v", "1",
                      "-vf", "scale=270:-2", q])
            quadros.append(q)
        pr = json.loads(self.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", mp4]))
        dur = round(float(pr["format"]["duration"]), 3)
        wall = max(self._wall() - t0, 1e-6)
        med = {
            "lufs": lufs, "true_peak_db": tp, "violacoes_zona_segura": viol,
            "velocidade_render_x": round(dur / wall, 2), "duracao_s": dur,
            "sincronia_cortes": {"cenas": len(sinc), "ok": sum(1 for x in sinc if x["ok"]), "detalhe": sinc},
            "ilustracao_dominante_falhas": [x for x in regra_il if not x["ok"]],
            "fontes": dict(self.fontes), "fontes_fallback": dict(self.fontes_fallback),
            "evidencia": "observado no mp4 final (ffprobe/ebur128/rmse entre quadros/bbox por diferenca de pixels)",
        }
        return RenderResult(str(mp4), str(srt_path), quadros, med)

    @staticmethod
    def _rotulos_literais(spec: dict) -> None:
        """Rule r6: etiquetas and tags are a literal piece of the speech or an approved label."""
        falado = " ".join(normaliza(w["texto"]) for w in spec["palavras"])
        aprov = {normaliza(x) for x in spec.get("rotulos_aprovados") or []}
        for c in spec["cenas"]:
            for b in c["batidas"]:
                for txt in [*(b.get("etiquetas") or []), *([b["tag"]] if b.get("tag") else [])]:
                    n = " ".join(normaliza(p) for p in txt.split())
                    if n not in aprov and n not in falado:
                        raise SpecInvalida("rotulo em tela nao e trecho literal da fala nem rotulo aprovado",
                                           codigo="texto_tela_nao_literal")
