"""extract_methodology orchestration — reads summaries, fake chat_fn (no network)."""
import pytest

from app.services.methodology_service import extract_methodology


@pytest.mark.asyncio
async def test_extract_methodology_orchestration(tmp_path):
    (tmp_path / "summaries" / "Mod 1").mkdir(parents=True)
    (tmp_path / "summaries" / "Mod 2").mkdir(parents=True)
    (tmp_path / "summaries" / "Mod 1" / "a1.md").write_text("resumo detalhado a1")
    (tmp_path / "summaries" / "Mod 1" / "a2.md").write_text("resumo detalhado a2")
    (tmp_path / "summaries" / "Mod 2" / "b1.md").write_text("resumo detalhado b1")

    calls = []

    async def fake_chat(messages, *, model=None, **kw):
        calls.append(messages)
        return "SÍNTESE"

    result = await extract_methodology(tmp_path, chat_fn=fake_chat, delay_seconds=0)

    # 2 module syntheses + 1 course synthesis
    assert len(calls) == 3
    assert (tmp_path / "methodology" / "Mod 1.md").exists()
    assert (tmp_path / "methodology" / "Mod 2.md").exists()
    assert (tmp_path / "METHODOLOGY.md").exists()
    assert "SÍNTESE" in (tmp_path / "METHODOLOGY.md").read_text()
    assert set(result["modules"]) == {"Mod 1", "Mod 2"}


@pytest.mark.asyncio
async def test_extract_methodology_errors_without_summaries(tmp_path):
    (tmp_path / "summaries").mkdir(parents=True)

    async def fake_chat(messages, *, model=None, **kw):
        return "x"

    with pytest.raises(FileNotFoundError):
        await extract_methodology(tmp_path, chat_fn=fake_chat, delay_seconds=0)
