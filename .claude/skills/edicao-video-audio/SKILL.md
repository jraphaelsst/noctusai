---
name: edicao-video-audio
description: Use for the sound of a video edit — triggers "normalizar o áudio", "volume", "loudness", "LUFS", "música de fundo", "abaixar a música quando eu falo", "efeito sonoro", "SFX", "áudio baixo", "limpar o áudio". Measures and normalizes loudness (two-pass, social target), ducks a music bed under speech, places SFX on events, and enforces forced-silence beats. Voice-only is the default; music/SFX only when authorized. Part of the Diretor de Edição set.
version: 0.1.0
---

# edicao-video-audio — measure, normalize, duck, never overdo

## Workflow
1. **Measure first:** `ffmpeg -i in -af ebur128=peak=true -f null -` (or `loudnorm=print_format=json`). Store integrated LUFS, LRA, true peak per job. Per-section readings when music is added.
2. **Default = voice only.** Music and SFX require `restricoes.musica_sfx_autorizados: true` and a source with rights `proprio|licenciado` (the user's or a licensed library). No music "found" on the internet.
3. **Normalize (two-pass `loudnorm`)** to the preset target (default −14 LUFS integrated, −1.5 dBTP): pass 1 measure, pass 2 with `measured_I/LRA/TP/thresh` and `linear=true`. Apply it LAST, after music/SFX mix.
4. **Music bed with ducking:** bed ~10 dB below speech as starting point; `sidechaincompress` keyed by the voice (starting values: threshold ~0.03, ratio ~5, attack ~30 ms, release ~400–500 ms), tune by measurement. The bed starts/ends with a short fade; no bed under a silence beat.
5. **SFX:** one sound per meaningful event (an insert entering, a number landing), aligned by peak to the visual event, not by file start; level relative to speech; no risers before reveals. SFX from a library with rights recorded; never synthesized silently as a fallback.
6. **Forced silence:** `audio.silencio[]` spans turn music/SFX off (emphasis pauses).
7. **Voice cleanup** (noise/click) only as a loudness-matched A/B for the user to choose; never promise studio quality.
8. **Verify:** re-measure the output; report LUFS/peak before→after as `observado`; "não ouvi o mix, ouça uma vez".

## Guardrails
Voice is never re-encoded through the graphics path: mux the processed voice track onto the visual render once. Cough/noise removal feeds the cut plan rather than being hidden in the mix.

Spec: `audio` in `KB § PATTERNS/media/video-edit-spec.md`.
