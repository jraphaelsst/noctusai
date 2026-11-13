---
name: edicao-video-corte-e-legenda
description: Use for the FIRST WIN of a video edit — cleanup cut plus captions — triggers "tira os silêncios", "corta as pausas e repetições", "remove os erros", "limpar o vídeo", "deixa só a última tomada", "coloca legenda", "legendar", "edição simples", "cleanup cut". Transcribes, finds silences, retakes and mis-speaks, proposes an approvable cut list with reasons, applies it with natural-rhythm pauses and click-free joins, and burns captions. Part of the Diretor de Edição set; default for a user's first job.
version: 0.1.0
---

# edicao-video-corte-e-legenda — clean it, caption it, show what you removed

Goal: a first approved result in minutes. Output = cut list (approvable) + cleaned video + burned captions + SRT.

## Workflow
1. **Preflight done?** (`edicao-video-preparo-de-midia`). Use the normalized copy.
2. **Transcribe** with `noctus.transcription.transcribe` (`idioma=pt`, `segmentos=true`; chunk per preflight). Cache by source `sha256`; never re-transcribe the same file. Proper nouns from the roteiro/brief go into `legendas.glossario`.
3. **Find candidates** (a model decides, a compiler executes):
   - silences: `silencedetect=noise=-35dB:d=0.35` (tune by measured noise floor);
   - fillers/hesitations and mis-speaks from the transcript;
   - retakes: consecutive segments with near-identical text; **keep the last take** unless the roteiro text matches an earlier one better. Align takes to the approved roteiro when it exists.
4. **Pause rule (data, by `ritmo`):** pauses longer than the cap are compressed to a short breath, not deleted; caps `natural 0.6 s · enxuto 0.4 s · acelerado 0.25 s` (preset can override). Default `ritmo` = `natural` (owner, 2026-11-13). Minimum kept segment 0.2 s. Never cut inside a word: snap cut points to the silence between words (segment gaps; use word times if available).
5. **Cut list for approval (pt-BR):** table `de → até · motivo · trecho removido (texto) · evidência`, with before→after duration and total removed. Wait for approval (or the user's "aprovar limpezas automaticamente"). Revisions are in plain words anchored to speech ("remove a parte em que eu falo X"), resolved against the transcript.
6. **Render:** per kept range `trim/atrim` + `setpts/asetpts`, 30 ms audio fades at each join to avoid clicks, concat; captions burned LAST. Keep a `cortes[]` map source→output times.
7. **Captions (this skill = line-level):** meaning-unit lines, 1–2 lines, ≤ ~32 chars per line, centred, ASS via libass (box or outline, keyword colour). Position from the preset; above the platform's bottom UI and clear of the face (`edicao-video-zona-segura`). Write `.srt` on the OUTPUT timeline. Uncertain words go to `legendas.incertas[]` and into the report.
8. **Verify:** `ffprobe` output duration ≈ sum of kept ranges (±1 frame × joins), audio present, frame count, no black/frozen run (`blackdetect`, `freezedetect`); caption text vs transcript diff on the glossary.
9. Hand the cut list + report back to the Diretor; offer styles only after this first approval.

## Guardrails
- Honesty: you did not listen; say "silêncios medidos, fala não ouvida".
- Never speed up speech unless asked (playback speed 1.0–1.2× is a separate, user-chosen option).
- Word-by-word highlight/pop → `edicao-video-legenda-por-palavra`.

Spec fields: `cortes[]`, `legendas`, `job.ritmo` in `KB § PATTERNS/media/video-edit-spec.md`.
