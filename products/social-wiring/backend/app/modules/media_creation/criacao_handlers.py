"""Step handlers of the ``reel_narrado`` route (criacao-pipeline-contract.md section 5): ``tts`` -> ``render_motion`` -> ``mux``.

A handler gets a seed ``StepContext`` (its inputs + its dependencies' outputs) and returns a ``StepResult`` carrying the
MEASURED units/cost/measurements of what it did. Failures are coded :class:`StepError` (``falhou(codigo)`` on the card).

* Intermediate files live in STORAGE, not on the worker's disk: a worker that restarts (or another one that claims the
  next step) finds them. Local files are scratch under ``deps.workdir``.
* ``tts`` never calls the vendor without a valid consent row of the marca (the voice is the marca's consented voice).
* Blocking work (vendor HTTP, ffmpeg/ImageMagick, ffprobe, PostgREST) runs in a thread; CPU is measured by the runner
  per step, children included.
* A local step (render, mux) has no vendor charge: its ``custo_usd`` is an explicit ``0`` (a measured fact), a vendor step
  whose price is not configured is ``nao_medido`` -- never an estimate.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from noctusai_lib.domain.media_production import (
    StepContext,
    StepError,
    StepRegistry,
    StepResult,
    vendor_credit_usd,
)
from noctusai_lib.integrations.motion_render import MotionRenderer, MotionRenderError
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.tts import TtsClient, TtsError, TtsNotConfigured, TtsRefused, TtsUpstreamError

from app.modules.media_creation.criacao_ports import SISTEMA_ATOR_ID, VozConsentimento
from app.modules.media_creation.criacao_rotas import PASSO_MUX, PASSO_RENDER, PASSO_TTS
from app.modules.media_creation.midia_storage import MIDIA_BUCKET, chave_upload
from app.modules.media_creation.services.post_assets_service import (
    MidiaProbe,
    PostAssetsService,
    probe_midia,
)

logger = logging.getLogger(__name__)

MODELO_TTS = "eleven_multilingual_v2"
PRESET = "papel-explainer"
VENDOR_TTS = "elevenlabs"
#: Fixed by the preset (``motion_render.preset``): the mix target the final mp4 is measured against.
ALVO_LUFS, PICO_DBTP, TOLERANCIA_LUFS = -14.0, -1.5, 1.0
MAX_CENAS = 14
MIN_PALAVRAS_POR_CENA = 22

#: Coded failures (the card shows them).
SEM_FALA = "roteiro_sem_fala"
CONSENTIMENTO_AUSENTE = "consentimento_ausente"
RENDER_STUB = "render_stub"
MIDIA_AUSENTE = "midia_ausente"
ZONA_SEGURA = "zona_segura_violada"
LOUDNESS_FORA = "loudness_fora_do_alvo"


# ── text -> spec (pure) ─────────────────────────────────────────────────────────────────────────────────────────────

_MARCADOR_SECAO = re.compile(r"^\s*={2,}\s*[A-Z_ ]+\s*={2,}\s*$")
_RODAPE = re.compile(r"^\s*={2,}\s*ESTRUTURAS_USADAS\s*={2,}.*\Z", re.S | re.M)
_RESTO_MD = re.compile(r"[*_`>#]+")
_PONTUACAO_BORDA = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def blocos_de_fala(conteudo: str) -> list[str]:
    """The roteiro's spoken text as blocks (paragraphs), without markdown, headings, section markers or the
    ``ESTRUTURAS_USADAS`` footer. A line wrapped entirely in ``**`` (a label such as ``**Gancho**``) or starting with
    ``#`` is a heading, not speech."""
    texto = _RODAPE.sub("", conteudo or "")
    blocos: list[str] = []
    atual: list[str] = []
    for linha in texto.splitlines():
        s = linha.strip()
        if not s:
            if atual:
                blocos.append(" ".join(atual))
                atual = []
            continue
        if s.startswith("#") or _MARCADOR_SECAO.match(s):
            continue
        if re.fullmatch(r"\*\*[^*]+\*\*:?", s) or re.fullmatch(r"\[[^\]]+\]", s):
            continue
        s = re.sub(r"^\s*(?:[-•]|\d+[.)])\s+", "", s)
        s = " ".join(_RESTO_MD.sub("", s).split())
        if s:
            atual.append(s)
    if atual:
        blocos.append(" ".join(atual))
    return blocos


def _agrupar(blocos: list[list[str]]) -> list[list[str]]:
    """Scenes = blocks, merged while shorter than ``MIN_PALAVRAS_POR_CENA`` and capped at ``MAX_CENAS``."""
    cenas: list[list[str]] = []
    for b in blocos:
        if cenas and len(cenas[-1]) < MIN_PALAVRAS_POR_CENA:
            cenas[-1] = cenas[-1] + b
        else:
            cenas.append(list(b))
    while len(cenas) > MAX_CENAS:  # merge the shortest adjacent pair
        i = min(range(len(cenas) - 1), key=lambda k: len(cenas[k]) + len(cenas[k + 1]))
        cenas[i : i + 2] = [cenas[i] + cenas[i + 1]]
    if len(cenas) > 1 and len(cenas[-1]) < MIN_PALAVRAS_POR_CENA // 2:
        cenas[-2:] = [cenas[-2] + cenas[-1]]
    return cenas


def montar_spec(conteudo: str, *, wpm: float = 165.0) -> tuple[str, dict]:
    """``(texto_da_narracao, spec)`` for the ``motion_render`` seam, built from the roteiro's teleprompter text.

    One word token per ``palavras`` entry (ids ``w0..``) -- the narration is synthesized from the SAME tokens, so the
    retime is 1:1 by construction. Scenes are paragraph groups anchored at their first word; each carries one beat whose
    on-screen title is a LITERAL piece of the speech (the engine refuses any label that is not, never invented copy).
    Word times here are even-paced placeholders: ``retime`` replaces them with the narration's measured timings."""
    blocos = [b.split() for b in blocos_de_fala(conteudo)]
    tokens = [t for b in blocos for t in b]
    if not tokens:
        raise StepError(SEM_FALA, "o roteiro não tem texto de fala")
    por_palavra = 60.0 / wpm
    palavras = [
        {"id": f"w{i}", "texto": t, "inicio_s": round(i * por_palavra, 3), "fim_s": round((i + 1) * por_palavra, 3)}
        for i, t in enumerate(tokens)
    ]
    cenas, i = [], 0
    for n, grupo in enumerate(_agrupar(blocos), 1):
        titulo = " ".join(filter(None, (_PONTUACAO_BORDA.sub("", t) for t in grupo[:4])))
        cenas.append({
            "id": f"c{n}", "ancora": {"palavra_id": f"w{i}"}, "fundo": "papel" if n % 2 else "interior",
            "transicao": "corte", "batidas": [{"titulo": titulo, "chave": True}],
        })
        i += len(grupo)
    return " ".join(tokens), {"palavras": palavras, "cenas": cenas, "cauda_s": 2.0}


def montar_entradas(*, marca_id: str, conteudo: str, usd_por_credito: Optional[Decimal]) -> dict[str, dict]:
    """Per-step inputs, persisted in the job payload (a worker restart resumes from them)."""
    texto, spec = montar_spec(conteudo)
    return {
        PASSO_TTS: {
            "texto": texto, "marca_id": marca_id, "modelo": MODELO_TTS,
            "usd_por_credito": None if usd_por_credito is None else str(usd_por_credito),
        },
        PASSO_RENDER: {"spec": spec, "preset": PRESET, "cenas": len(spec["cenas"])},
        PASSO_MUX: {"alvo_lufs": ALVO_LUFS, "pico_dbtp": PICO_DBTP, "tolerancia_lufs": TOLERANCIA_LUFS},
    }


# ── dependencies + handlers ─────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class CriacaoDeps:
    db: Any
    storage: StorageBackend
    consent: VozConsentimento
    #: ``(org_id, marca_id, out_dir) -> TtsClient`` bound to the marca's consent checker.
    make_tts: Callable[[str, str, Path], TtsClient]
    renderer: MotionRenderer
    workdir: Path
    probe: MidiaProbe = probe_midia
    #: tests run the Fake renderer on a host without ffmpeg: its stub file is then accepted (never in production).
    permitir_stub: bool = False
    bucket: str = MIDIA_BUCKET
    ator_id: str = SISTEMA_ATOR_ID
    extra: dict = field(default_factory=dict)


def _scratch(deps: CriacaoDeps, ctx: StepContext) -> Path:
    d = deps.workdir / ctx.post_id / f"r{ctx.rodada}-{ctx.passo}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _limpar(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


async def _baixar(deps: CriacaoDeps, key: str, destino: Path) -> Path:
    blob = await deps.storage.get(bucket=deps.bucket, key=key)
    if blob is None:
        raise StepError(MIDIA_AUSENTE, f"arquivo intermediário ausente do storage: {key}")
    destino.write_bytes(blob.data)
    return destino


def build_handlers(deps: CriacaoDeps) -> StepRegistry:
    reg = StepRegistry()

    async def tts(ctx: StepContext) -> StepResult:
        e = ctx.entradas
        voz = await asyncio.to_thread(deps.consent.voz_da_marca, ctx.org_id, e["marca_id"])
        if voz is None:  # refused BEFORE any vendor call
            raise StepError(CONSENTIMENTO_AUSENTE, "a marca não tem consentimento de voz vigente")
        voice_id, consent_id = voz
        out = _scratch(deps, ctx)
        try:
            client = deps.make_tts(ctx.org_id, e["marca_id"], out)
            res = await asyncio.to_thread(
                client.synthesize, e["texto"], voice_id, e["modelo"], consent_ref=f"cs_consentimento:{consent_id}"
            )
            audio = Path(res.audio_path)
            dados = audio.read_bytes()
        except TtsNotConfigured as exc:
            raise StepError("tts_nao_configurado", str(exc)) from exc
        except TtsRefused as exc:
            raise StepError(exc.codigo, str(exc)) from exc
        except TtsUpstreamError as exc:
            raise StepError("tts_upstream", str(exc), retryable=True) from exc
        except TtsError as exc:
            raise StepError(exc.codigo, str(exc)) from exc
        finally:
            _limpar(out)
        ext = audio.suffix.lstrip(".") or "mp3"
        key = chave_upload(ctx.org_id, ctx.post_id, "insumos", f"criacao-r{ctx.rodada}-narracao.{ext}")
        await deps.storage.put(
            bucket=deps.bucket, key=key, data=dados,
            content_type="audio/mpeg" if ext == "mp3" else f"audio/{ext}",
        )
        preco = e.get("usd_por_credito")
        custo: Optional[Decimal] = None
        if res.creditos_cobrados is not None and preco is not None:
            custo = vendor_credit_usd(res.creditos_cobrados, Decimal(str(preco)))
        return StepResult(
            saida={
                "audio_key": key, "audio_s": res.audio_s, "voice_id": voice_id, "consent_id": consent_id,
                "timings": [{"texto": t.texto, "inicio_s": t.inicio_s, "fim_s": t.fim_s} for t in res.timings],
            },
            vendor=VENDOR_TTS, modelo=e["modelo"], request_id=res.request_id,
            unidades={
                "caracteres": res.caracteres, "audio_s": res.audio_s, "creditos_cobrados": res.creditos_cobrados,
                "creditos_fonte": res.creditos_fonte, "audio_s_fonte": res.audio_s_fonte,
            },
            custo_usd=custo,  # None (named nao_medido by the runner) when the plan's price is not configured
        )

    async def render_motion(ctx: StepContext) -> StepResult:
        e, narr = ctx.entradas, ctx.entradas[PASSO_TTS]
        if not narr:
            raise StepError("passo_anterior_sem_saida", "a narração não foi produzida")
        out = _scratch(deps, ctx)
        try:
            audio = await _baixar(deps, narr["audio_key"], out / "narracao.mp3")
            try:
                spec = deps.renderer.retime(e["spec"], narr["timings"])  # refuses unless the words match 1:1
                res = await asyncio.to_thread(deps.renderer.render, e["preset"], spec, str(audio), str(out / "saida"))
            except MotionRenderError as exc:
                raise StepError(exc.codigo, str(exc)) from exc
            if res.stub and not deps.permitir_stub:
                raise StepError(RENDER_STUB, "o render devolveu um arquivo de teste (sem ffmpeg neste host)")
            mp4_key = chave_upload(ctx.org_id, ctx.post_id, "saidas", f"criacao-r{ctx.rodada}-reel.mp4")
            await deps.storage.put(
                bucket=deps.bucket, key=mp4_key, data=Path(res.mp4_path).read_bytes(), content_type="video/mp4"
            )
            srt_key = chave_upload(ctx.org_id, ctx.post_id, "preview", f"criacao-r{ctx.rodada}-legenda.srt")
            await deps.storage.put(
                bucket=deps.bucket, key=srt_key, data=Path(res.srt_path).read_bytes(), content_type="application/x-subrip"
            )
        finally:
            _limpar(out)
        return StepResult(
            saida={
                "mp4_key": mp4_key, "srt_key": srt_key, "stub": res.stub, "cenas": e.get("cenas"),
                "medicoes": dict(res.medicoes),
            },
            medicoes=dict(res.medicoes),
            custo_usd=Decimal("0"),  # local compute: no vendor charge (a fact, not an estimate)
        )

    async def mux(ctx: StepContext) -> StepResult:
        e, ren = ctx.entradas, ctx.entradas[PASSO_RENDER]
        if not ren:
            raise StepError("passo_anterior_sem_saida", "o vídeo não foi renderizado")
        # the measurements the engine took on the ENCODED mp4 (never on its inputs), carried in render_motion's output
        med = ren.get("medicoes") or {}
        blob = await deps.storage.get(bucket=deps.bucket, key=ren["mp4_key"])
        if blob is None:
            raise StepError(MIDIA_AUSENTE, "o vídeo final não está no storage")
        lufs, pico = med.get("lufs"), med.get("true_peak_db")
        if lufs is None or abs(float(lufs) - e["alvo_lufs"]) > e["tolerancia_lufs"] or (
            pico is not None and float(pico) > e["pico_dbtp"]
        ):
            raise StepError(LOUDNESS_FORA, f"loudness {lufs} LUFS / {pico} dBTP fora do alvo")
        if med.get("violacoes_zona_segura"):
            raise StepError(ZONA_SEGURA, "texto fora da zona segura do reel")

        def registrar() -> dict:
            fato = deps.probe(blob.data, "reel.mp4")
            svc = PostAssetsService(deps.db, ctx.org_id, deps.ator_id)
            return svc.registrar(
                ctx.post_id, storage_path=ren["mp4_key"], ordem=1, fato=fato,
                mime_type="video/mp4", tamanho_bytes=len(blob.data),
            )

        asset = await asyncio.to_thread(registrar)
        return StepResult(
            saida={"asset_id": asset["id"], "mp4_key": ren["mp4_key"], "srt_key": ren.get("srt_key"),
                   "duracao_s": asset.get("duracao_s")},
            medicoes={"lufs": lufs, "true_peak_db": pico, "violacoes_zona_segura": [],
                      "velocidade_render_x": med.get("velocidade_render_x"), "duracao_s": med.get("duracao_s")},
            custo_usd=Decimal("0"),
        )

    reg.register_step(PASSO_TTS, tts)
    reg.register_step(PASSO_RENDER, render_motion)
    reg.register_step(PASSO_MUX, mux)
    return reg


__all__ = ["CriacaoDeps", "build_handlers", "montar_entradas", "montar_spec", "blocos_de_fala"]
