"""End-to-end pipeline wiring, driven entirely by fakes (no network/keys/ffmpeg).

Per noc methodology: seed real data + inject fakes via DI — never monkeypatch our
own code. The only thing faked here are the external seams (Drive/audio/LLM).
"""
import shutil
from pathlib import Path

import pytest

from app.integrations.google_drive import FakeDriveDownloader
from app.pipeline import ExtractionPipeline


def _build(tmp_path: Path) -> tuple[ExtractionPipeline, FakeDriveDownloader]:
    drive = FakeDriveDownloader()
    drive.add_fake_file("v1", "aula-01.mp4", b"VIDEOBYTES", mime_type="video/mp4")
    drive.add_fake_file("readme", "leiame.txt", b"not a video")  # filtered out

    def fake_extract(video: Path, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(video, out)
        return out

    async def fake_transcribe(audio: Path, chunk_dir: Path) -> str:
        return "transcrição de teste da aula"

    async def fake_summarize(title: str, transcript: str) -> str:
        return f"## Resumo\nresumo de {title}"

    pipeline = ExtractionPipeline(
        downloader=drive,
        audio_extractor=fake_extract,
        transcriber=fake_transcribe,
        summarizer=fake_summarize,
        data_dir=tmp_path,
    )
    return pipeline, drive


@pytest.mark.asyncio
async def test_run_from_drive_processes_only_videos(tmp_path):
    pipeline, _ = _build(tmp_path)
    results = await pipeline.run_from_drive("fake://folder")

    # Only the .mp4 is processed; the .txt is filtered out.
    assert len(results) == 1
    r = results[0]
    assert r.name == "aula-01"
    assert r.transcript_path.exists()
    assert "transcrição de teste" in r.transcript_path.read_text(encoding="utf-8")
    assert r.summary_path.exists()
    assert "resumo de aula-01" in r.summary_path.read_text(encoding="utf-8")
    assert (tmp_path / "manifest.json").exists()


@pytest.mark.asyncio
async def test_run_module_organizes_and_resumes(tmp_path):
    pipeline, _ = _build(tmp_path)
    results = await pipeline.run_module("mod-folder", "Modulo 1", wait_seconds=0)

    assert len(results) == 1
    r = results[0]
    assert r.module == "Modulo 1"
    assert (tmp_path / "transcripts" / "Modulo 1" / "aula-01.md").exists()
    assert (tmp_path / "summaries" / "Modulo 1" / "aula-01.md").exists()

    # Second run on a fresh pipeline → already done → skipped, nothing processed.
    pipeline2, _ = _build(tmp_path)
    results2 = await pipeline2.run_module("mod-folder", "Modulo 1", wait_seconds=0)
    assert results2 == []
    assert pipeline2.skipped == ["Modulo 1/aula-01"]


@pytest.mark.asyncio
async def test_run_module_reorganizes_flat_pilot_outputs(tmp_path):
    pipeline, _ = _build(tmp_path)
    # Simulate a pilot run that wrote flat (un-organized) outputs for aula-01.
    (tmp_path / "transcripts").mkdir(parents=True)
    (tmp_path / "summaries").mkdir(parents=True)
    (tmp_path / "transcripts" / "aula-01.md").write_text("flat transcript")
    (tmp_path / "summaries" / "aula-01.md").write_text("flat summary")

    results = await pipeline.run_module("mod-folder", "Modulo 1", wait_seconds=0)

    # Reorganized into the module folder + skipped (NOT re-transcribed).
    assert results == []
    assert pipeline.skipped == ["Modulo 1/aula-01"]
    moved = tmp_path / "transcripts" / "Modulo 1" / "aula-01.md"
    assert moved.read_text() == "flat transcript"
    assert not (tmp_path / "transcripts" / "aula-01.md").exists()


@pytest.mark.asyncio
async def test_resummarize_from_existing_transcripts(tmp_path):
    pipeline, _ = _build(tmp_path)
    # Seed an existing transcript (as a prior run would have written).
    tdir = tmp_path / "transcripts" / "Modulo 1"
    tdir.mkdir(parents=True)
    (tdir / "aula-01.md").write_text("# aula-01\n\ntranscrição completa da aula")

    results = await pipeline.resummarize(wait_seconds=0)

    assert len(results) == 1
    assert results[0].module == "Modulo 1"
    summary = tmp_path / "summaries" / "Modulo 1" / "aula-01.md"
    assert summary.exists()
    # _build's fake summarizer returns "## Resumo\nresumo de <title>"
    assert "resumo de aula-01" in summary.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_process_local_video(tmp_path):
    pipeline, _ = _build(tmp_path)
    video = tmp_path / "minha-aula.mp4"
    video.write_bytes(b"LOCALVIDEO")

    results = await pipeline.run_local([video])

    assert len(results) == 1
    assert results[0].name == "minha-aula"
    assert results[0].transcript_chars > 0
    assert results[0].summary_chars > 0
