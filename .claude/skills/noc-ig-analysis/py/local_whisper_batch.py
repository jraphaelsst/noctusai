# NOC-REMEDIATE[mcp-first]: skill-bundled local batch until knowledge-extractor exposes a batch MCP tool.
# Run: nice -n 10 <knowledge-extractor>/backend/.venv/bin/python -I local_whisper_batch.py <mp3_dir> <out_dir>
# Safe alongside noctus.transcription.batch: walks newest-numbered first and claims each stem with <stem>.local.lock.
"""Local faster-whisper, newest-numbered last: walk mp3s in REVERSE, skip any stem already transcribed."""
import json, sys, time
from pathlib import Path
from faster_whisper import WhisperModel
src, out = Path(sys.argv[1]), Path(sys.argv[2])
m = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo", device="cpu", compute_type="int8", cpu_threads=4)
for f in sorted(src.glob("*.mp3"), reverse=True):
    if (out / f"{f.stem}.txt").exists() or (out / f"{f.stem}.local.lock").exists(): continue
    (out / f"{f.stem}.local.lock").write_text("")
    t = time.time()
    segs, info = m.transcribe(str(f), language="pt", vad_filter=True)
    segs = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()} for s in segs]
    text = " ".join(s["text"] for s in segs)
    (out / f"{f.stem}.txt").write_text(text)
    (out / f"{f.stem}.json").write_text(json.dumps({"source": "local-faster-whisper-large-v3-turbo", "duracao_s": info.duration, "segmentos": segs}, ensure_ascii=False))
    print("done", f.stem, round(time.time() - t), "s", flush=True)
print("ALL-DONE", flush=True)
