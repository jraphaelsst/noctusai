"""build_index — scans transcripts/summaries on disk into a cumulative index."""
from app.services.indexing import build_index


def test_build_index_scans_modules(tmp_path):
    (tmp_path / "transcripts" / "Mod 1").mkdir(parents=True)
    (tmp_path / "summaries" / "Mod 1").mkdir(parents=True)
    (tmp_path / "transcripts" / "Mod 1" / "aula-01.md").write_text("transcript body")
    (tmp_path / "summaries" / "Mod 1" / "aula-01.md").write_text("summary body")
    (tmp_path / "transcripts" / "Mod 1" / "aula-02.md").write_text("x")  # no summary

    m = build_index(tmp_path)

    assert m["total_lessons"] == 2
    assert m["modules"]["Mod 1"] == 2
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "INDEX.md").exists()
    assert "Mod 1 (2)" in (tmp_path / "INDEX.md").read_text()

    lessons = {lsn["name"]: lsn for lsn in m["lessons"]}
    assert lessons["aula-01"]["summary"] is not None
    assert lessons["aula-02"]["summary"] is None
