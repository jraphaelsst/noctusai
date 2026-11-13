---
name: edicao-video-preparo-de-midia
description: Use before ANY video edit, to probe and normalize source media — triggers "preparar o vídeo", "o render ficou com cor estranha", "vídeo do iPhone", "HDR", "variable frame rate", "arquivo muito grande para transcrever", "dividir áudio para transcrição", "ffprobe". Probes with ffprobe, converts HDR to SDR, VFR to constant frame rate, fixes rotation/codec, extracts audio, and chunks media above the transcription limits (600 s, 150 MB per file). Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-preparo-de-midia — never edit what you have not normalized

The class-wide hard failure was iPhone HDR breaking the render; fix it at ingest, once, with one line of explanation to the user.

## Workflow
1. **Probe** (never assume): `ffprobe -v error -show_streams -show_format -of json <src>`. Record codec, `r_frame_rate` vs `avg_frame_rate` (differ ⇒ VFR), `color_transfer`, `color_primaries`, `pix_fmt`, rotation (side data), duration, audio channels/rate. `sha256` of the original into the spec `fontes[]`.
2. **Never touch the original.** Output to `<job>/work/normalizado.mp4`.
3. **HDR → SDR** when `color_transfer` is `smpte2084` or `arib-std-b67`: `zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p`. If `zscale` is missing in this ffmpeg build, stop and say so (do not render with HDR as-is); report `nao_verificavel` for colour fidelity. Spot-check one frame afterwards (mean luma not crushed/blown).
4. **VFR → CFR:** `-fps_mode cfr -r 30` (30 unless the preset says otherwise; keep 25/24 if the source is a clean 25/24).
5. **Normalize container/codec:** H.264 `yuv420p`, AAC 48 kHz, `+faststart`, rotation applied (autorotate) and the rotation tag cleared, even dimensions.
6. **Audio for transcription:** `-vn -ac 1 -ar 16000 -c:a libmp3lame -b:a 64k`.
7. **Chunk when needed.** The transcription service takes one file ≤ 600 s and ≤ 150 MB per call. Over that: split the extracted audio, e.g. `-f segment -segment_time 540 -c copy`, keep the list of chunk start offsets, transcribe each (`noctus.transcription.batch`, `segmentos=true`), then add each chunk's offset to its segment times. Cut on the nearest silence when possible so no word is split.
8. **Report one line:** what was converted and why, in pt-BR ("converti o HDR do iPhone para cor padrão e fixei a taxa de quadros").

## Guardrails
- Probe output and measured values are `observado`; any colour judgement without a viewed frame is `inferido`.
- Tell the user, at capture time, that HDR off (or "nós corrigimos") avoids the issue.
- No installs or network. Missing filter ⇒ report, never silently degrade.

Spec: `KB § PATTERNS/media/video-edit-spec.md` (`fontes[].normalizacao`).
