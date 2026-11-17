# FALLBACK ONLY (owner rule 2026-11-07): transcription runs on the server via noctus.transcription.transcribe /
# .batch (segmentos=true for timestamps). Use this script ONLY when the server FAILS (error status, nao_configurado,
# network errors after retries, service down), never "in parallel to be faster" unless the owner opts in for that run
# (done once, 2026-11-15). KB § PATTERNS/common/instagram-content-analysis.md §2.
# It MIRRORS the production transcriber by reusing the seed's own server code (no re-implementation): the same
# ffmpeg -> 16 kHz s16le decode, the same FasterWhisperEngine settings, the pinned model revision and the pinned
# faster-whisper/ctranslate2 from deploy/services/transcriber/requirements.lock. Output is the server response shape.
# Run from the repo root, through the hardware gate (the -s -P flags matter: `-I` would ignore PYTHONPATH):
#   PYTHONPATH=seed/lib/backend python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job whisper:local -- \
#     uv run --no-project --python 3.12 --with-requirements deploy/services/transcriber/requirements.lock \
#     python -s -P .claude/skills/noc-ig-analysis/py/local_whisper_batch.py <mp3_dir> <out_dir>
# Safe alongside noctus.transcription.batch: walks newest-numbered first and claims each stem with <stem>.local.lock.
"""Local mirror of the production transcriber: walk mp3s in REVERSE, skip any stem already transcribed."""
import asyncio
import json
import sys
import time
from pathlib import Path

MODEL_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
MODEL_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"  # the transcriber Dockerfile pin


def model_dir() -> str:
    """The pinned HF snapshot (cache hit when present, else a pinned download)."""
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL_REPO, revision=MODEL_REVISION)


def main(src: Path, out: Path) -> None:
    from noctusai_lib.integrations.transcription.server.engine import FasterWhisperEngine
    from noctusai_lib.integrations.transcription.server.media import SAMPLE_RATE, decode_to_float32

    out.mkdir(parents=True, exist_ok=True)
    engine = FasterWhisperEngine(model_dir())
    engine.load()
    for f in sorted(src.glob("*.mp3"), reverse=True):
        if (out / f"{f.stem}.txt").exists() or (out / f"{f.stem}.local.lock").exists():
            continue
        (out / f"{f.stem}.local.lock").write_text("")
        audio = asyncio.run(decode_to_float32(f.read_bytes(), max_seconds=None, timeout=300.0))
        dur = len(audio) / SAMPLE_RATE
        t0 = time.time()
        res = engine.transcribe(audio, language="pt")
        wall = time.time() - t0
        payload = {
            "status": "concluida",
            "origem": "local-mirror",
            "modelo": engine.model_name,
            "idioma": "pt",
            "rotulo": f.stem,
            "duracao_s": dur,
            "rtf": round(wall / dur, 3) if dur else None,
            "texto": res.text,
            "segmentos": res.segmentos,  # [{inicio, fim, texto}], same as the server
        }
        (out / f"{f.stem}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (out / f"{f.stem}.txt").write_text(res.text, encoding="utf-8")
        print("done", f.stem, round(wall), "s", flush=True)
    print("ALL-DONE", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
