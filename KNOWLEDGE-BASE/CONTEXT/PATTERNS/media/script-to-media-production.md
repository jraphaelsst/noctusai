# Script-to-media production — from an approved roteiro to a narrated reel and a carousel, no footage

> **Status:** learned on ONE real round (Mônica Tangerino, 2026-11-18: 6 reels + 3 carousels, all 6 reels narrated with an ElevenLabs instant voice clone). Method trial `narrated-reel-pipeline-ivc`. This is the process the CoreStudio editing agent will run once the owner validates it; until then it is a playbook, not a gate. Numbers below are `observado` unless labelled.
>
> **Why it exists.** `video-edit-spec.md` and agent `diretor-de-edicao` assume a raw clip to clean and caption. A large share of creator content has **no footage at all**: an approved script becomes a motion-graphics explainer (and a carousel) with a voice that is either the creator's recording or a consented clone. That path has its own stages, its own failure modes and its own consent gate.

## 1 · The pipeline (stage → artifact → gate)

| # | Stage | Artifact | Gate (who says yes) |
|---|---|---|---|
| 1 | **Pautas + roteiros** (writer agent, e.g. `roteirista-monica`, Elias 9-block method) | `roteiros.md`: headline + labelled roteiro + **teleprompter version** per pauta | owner approves headlines + roteiros **before any production** |
| 2 | **Style from a reference** → skill `edicao-video-referencia-para-preset` | `estilo-referencia.md`: measured rhythm/layout/palette, 3-column study, preset draft (`status: nao_testado`) + preview covers | owner looks at the covers |
| 3 | **Storyboard** per pauta: which pautas are reel, carousel or both; scenes anchored to sentences | `storyboards.md` → `pecas.py` (scene plan as **data**) | owner picks reel vs carousel |
| 4 | **Spec** per reel from the teleprompter text (word tokens `wN`, caption groups, scenes anchored by `palavra_id`) | `spec.json` (`video-edit-spec.md`) | — (deterministic) |
| 5 | **Text-guided render** (silent, timed at the creator's measured speech rate) | `-final.mp4`, `.srt`, key frames, `relatorio.md` | owner previews the visuals |
| 6 | **Voice** — the creator's recording, OR a synthetic clone **under a signed consent term** (§3) | `-narracao.mp3` + word timings | consent term signed; owner (and the creator) approve the voice |
| 7 | **Retime** the spec to the voice (§2) and **re-render** | narrated `-final.mp4` | measured checks (§4) |
| 8 | **Carousel** render from the same storyboard (1080×1350, 10 slides) | `slide-NN.png` | owner approves the slide text adaptations |
| 9 | **Deliver** — never publish; hand to the post's media approval | files + report | CoreStudio approval flow |

Stage 5 before stage 6 is deliberate: the owner judges the visuals while the voice question (record vs clone, consent) is still open, and scenes anchored to **word ids** survive any later voice without re-planning.

## 2 · Retime by word id (the load-bearing trick)

- Scenes, beats, captions and lettering anchor to **word ids** (`w0…wN`) of the teleprompter text, never to seconds. A new voice only rewrites `palavras[].inicio_s/fim_s`; nothing else is re-planned.
- **Synthetic voice:** the TTS alignment (ElevenLabs `with-timestamps`, character-level, grouped to words by the connector) is used directly. The retime **refuses unless the TTS words match the script tokens 1:1** (punctuation-insensitive): that is the mechanical form of the "no new speech" rule. Observed: 6/6 reels matched 1:1, including years ("1914") and "Seminário 10", because the alignment is on the input text, not on what is spoken.
- **Recorded voice:** use `noctus.transcription.transcribe palavras=true`; expect mismatches (ad-libs, retakes) → a cut list first (`edicao-video-corte-e-legenda`), then align.
- Re-render is the same command; keep the silent version (`-sem-voz.mp4` + `spec-sem-narracao.json`) and always retime from the clean silent spec, so re-runs are idempotent.

## 3 · Synthetic voice — consent and tool

- Voice is **biometric sensitive data** (LGPD art. 5 II, art. 11 I). A clone is created and used only under a **signed term** from the voice owner (purpose, scope, revocation, deletion, who holds the voice). Instant clone (IVC) for validation in our account; Professional clone (PVC) is created in the **creator's own** ElevenLabs account and shared to ours. The term template lives with the client's private material, not in git.
- Tool: the house connector `mcp/elevenlabs/` (`KB § MCP-SERVERS/elevenlabs.md`): `tts.synthesize` is confirm-gated (412 estimate first), writes `<audio>.timings.json`; `voice.clone_instant` requires a `consent_reference`. Outputs default to the noc-level private dir; the job copies what it needs into its own folder.
- Cost measured (6 reels, billed header): `eleven_v4` billed **2 987 credits for 6 788 input characters = 0.4400 credit/char** (per reel 0.4396–0.4404; 473–528 credits for 1 074–1 201 chars, 77.44–86.48 s of audio). The pre-flight estimate is 1 credit/char: a ceiling, never the result.
- Pace measured: the IVC read at 145.7–160.4 wpm (6 reels; words ÷ aligned audio seconds) vs the creator's measured median of 165 wpm on 30 transcribed reels.

## 4 · Checks that must run on every narrated render

1. **Loudness** two-pass `loudnorm` to −14 LUFS / −1.5 dBTP, measured on the final mp4 with `ebur128`. ⚠️ **Mono TTS → stereo: pan BEFORE measuring.** Duplicating a normalized mono signal to two channels reads **+3 LU** (observed −11.3 LUFS instead of −14). ⚠️ **Measure the ENCODED mp4, not the WAV:** AAC raised true peak from −1.5 to −0.8 dBTP; normalize 1.0 dB below the TP target (measured after the fix: −2.1 to −2.3 dBTP on 6 reels, all −14.1 LUFS) and fail the render (do not deliver) when the final file is off target. → skill `edicao-video-audio`.
2. **Independent transcription — a GATE, not a report** (owner, 2026-11-18): transcribe the final file (`noctus.transcription.transcribe palavras=true`) and diff it word by word against the approved script. Compare **canonical forms**, because the transcriber writes the formal spelling of what it heard: `pra/pro/pras/pros` → `para (o/as/os)`, `pra` + a word starting with *a* → `para a` (sandhi), hyphens split. A lone `a` next to `para` is equal either way (the same spoken "pra aquela" came back as "para a aquela" and as "para aquela"). An insertion AFTER the last script word is a hallucination when the audio after the voice's own end (`fala_fim_s`, from the TTS alignment) **measures** below −60 dB over 1 s; never decide by a time cutoff or a window that overlaps the last word's decay (both let "muito obrigado obrigado obrigado" through; the correct window read −91.0 dB). Cache each transcription by the final file's sha256 next to the piece, so a comparator fix re-scores without re-transcribing (each check costs 95–133 s of wall time per ~80 s reel, measured). Every remaining difference becomes a **listen-at-t item** (exact second, script word, transcriber word) and the piece is `pendente_escuta`, not approved; zero differences = `aprovado_por_medicao`. Measured on 6 reels: strict diff rejected 6/6 with 23 differences (14 were `pra→para` alone); the canonical comparator left 3 reels `aprovado_por_medicao` and 5 listen items on the other 3 (three "salva esse vídeo" heard as salve/salvo, one "pra apagar" heard as "pagar", one dropped "a"). Deliver each listen item as a 3.5 s clip named by its second. A strict text diff is a false alarm machine; a lenient one hides real slips; the listen list is the honest middle. This is the only check that hears what the viewer will hear: the 1:1 retime proves the TTS *alignment* matches the text, not that the voice *pronounced* it (numbers, names, foreign titles). ⚠️ Whisper invents short phrases on trailing silence ("E aí", confidence 0.29/0.33, over audio measured at −87 dBFS): verify any tail word by measuring the audio level there before calling it a defect.
3. **Sync** — key frame at each scene midpoint: the on-screen title must be the sentence being spoken.
4. **Hook** — frame 0 has title + object + first caption (no fade from black).
5. **Safe zone** — every beat and caption box (union across animation) inside the zone table.
6. **Source hash** — roteiro sha256 unchanged from spec creation to render.

## 5 · Batch creation is measured per item (owner rule, 2026-11-18)

Batches are the normal mode (headlines/scripts in batch next, then media, then avatar video; the owner chooses how many posts). So **every request in a batch records its own measured numbers** and reports only measured values, never "about N":

- one ledger row per step per piece (`voz`, `retime`, `render`, `relatorio`, `conferencia`), plus `peca-total` and `lote-total`;
- fields: start/end, wall `duracao_s`, `cpu_s`, outcome (`ok`/`erro`); for voice: `caracteres`, `creditos_cobrados` from the vendor's response header, `audio_s`, `request_id`, voice and model; for render: `video_s`, `velocidade_render_x` (video seconds per wall second), LUFS, true peak, safe-zone violations; for the check: differences, similarity, transcription RTF;
- the batch total cross-checks billed credits against the account balance delta (usage before vs after);
- a value that was not measured is `null` + `nao_medido`, never an estimate. Estimates exist only as the labelled pre-flight ceiling (the TTS 412 gate).

First implementation: the round's `lote.py` (ledger `producao/medicoes.ndjson`, zero-credit re-runs with `--reusar-voz`). The CoreStudio worker inherits the row shape as job events (measurement-by-design).

## 6 · Craft lessons (paper-explainer preset, first round)

- Render time is **load-bound, so record the machine load with it**. Measured, same code, 79–88 s reels: 124.4 s (0.67× real time) → 582.0 s (0.15×) as the 8-core machine's 1-min load average reached 47.4 from other sessions; one render process at a time on 8 GB. Heavy batches go through `noctus.dev.hw_admission` and wait when the machine is overloaded, or their timings measure the neighbours, not the pipeline.
- Text on screen is always a span of the speech or an approved tag word; numbers carry author + year.
- Mid-video CTAs become a paper tag ("salve" / "compartilhe") without changing scene; one "interior" (dark) scene per video at the most intimate moment.
- Carousel text is an adaptation of spoken text ("esse vídeo" is dropped) → needs the owner's ok.
- Caption groups: 3–5 words, ≤ 26 chars, never across a sentence, function words carried to the next group.

## 7 · Open (named destinations)

- Voice-ID ↔ consent-reference audit log in the connector → `KB § MCP-SERVERS/elevenlabs.md` open items.
- A seed IO adapter (Protocol + Fake + Real + factory) for TTS when CoreStudio consumes it → same doc.
- The production scripts (`produzir.py`, `pecas.py`, `ilustracoes.py`) live in the client's private study folder; turning them into the CoreStudio render worker is the agent's build step, after the owner validates this round.
- Validate the PVC swap (same two commands, new voice id) → trial `narrated-reel-pipeline-ivc` follow-up.

→ Composes with `KB § PATTERNS/media/video-edit-spec.md` · agent `diretor-de-edicao` · skills `edicao-video-*` · `KB § MCP-SERVERS/elevenlabs.md` · `KB § PATTERNS/common/method-trials.md`.
