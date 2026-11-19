"""motion_render seam: value objects, errors and the renderer Protocol.

Spec contract (a plain dict, the product builds it from its own script/plan):

    {
      "formato": {"largura": 1080, "altura": 1920, "fps": 30},     # optional, these are the defaults
      "cauda_s": 2.0,                                              # silence kept after the last word
      "palavras": [{"id": "w0", "texto": "Oi", "inicio_s": 0.0, "fim_s": 0.3}, ...],   # the script, 1 token each
      "grupos":   [{"id": "g0", "palavra_ids": ["w0", "w1"]}],     # caption groups; omitted => derived
      "cenas": [{"id": "c1", "ancora": {"palavra_id": "w0"}, "fundo": "papel" | "interior",
                 "transicao": "corte" | "fade",
                 "batidas": [{"ancora": {"palavra_id": "w3"} | {"fracao_da_cena": 0.5},   # first batida: scene start
                              "titulo": "10 anos", "chave": true,
                              "ilustracao": "livro", "etiquetas": ["x"], "circulo": "x", "riscado": "y",
                              "ficha": "Autora, 2020", "tag": "salve"}]}],
      "rotulos_aprovados": ["salve"],     # on-screen labels allowed besides literal pieces of the speech
      "audio": {"loudness": {"alvo_lufs": -14, "pico_dbtp": -1.5}}
    }

`medicoes` of a RenderResult is measured on the ENCODED mp4, never on the inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


class MotionRenderError(Exception):
    """Coded failure. `codigo` is stable; the message never carries script text."""

    codigo = "render_erro"

    def __init__(self, message: str, *, codigo: Optional[str] = None):
        super().__init__(message)
        if codigo:
            self.codigo = codigo


class RetimeRecusado(MotionRenderError):
    """The narration's words do not match the script 1:1 -- never invent speech."""

    codigo = "retime_palavras_divergem"


class FerramentaAusente(MotionRenderError):
    """ffmpeg / ImageMagick missing on this host (build the image FROM the seed media base)."""

    codigo = "ferramenta_ausente"


class LoudnessForaDoAlvo(MotionRenderError):
    codigo = "loudness_fora_do_alvo"


class SpecInvalida(MotionRenderError):
    codigo = "spec_invalida"


@dataclass(frozen=True)
class RenderResult:
    mp4_path: str
    srt_path: str
    quadros_chave: list[str]
    medicoes: dict = field(default_factory=dict)
    stub: bool = False  # True: placeholder file (no ffmpeg on this host), not a playable video


@runtime_checkable
class MotionRenderer(Protocol):
    def render(self, preset: str, spec: dict, audio_path: Optional[str], out_dir: str) -> RenderResult: ...

    def retime(self, spec: dict, timings: list) -> dict: ...
