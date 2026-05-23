"""Cumulative course index — scans the data dir for all transcripts/summaries.

Unlike the per-run manifest the pipeline writes during a single module run, this
rebuilds the WHOLE picture from disk, so it always reflects every lesson processed
across every module run. Writes `manifest.json` (machine) + `INDEX.md` (human).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def build_index(data_dir: Path) -> dict:
    """Scan transcripts/summaries on disk; write manifest.json + INDEX.md.

    Returns the manifest dict.
    """
    transcripts_dir = data_dir / "transcripts"
    summaries_dir = data_dir / "summaries"

    modules: dict[str, list[dict]] = {}
    lessons: list[dict] = []

    for tpath in sorted(transcripts_dir.rglob("*.md")):
        rel = tpath.relative_to(transcripts_dir)
        module = rel.parent.as_posix() if rel.parent != Path(".") else "(uncategorized)"
        spath = summaries_dir / rel
        entry = {
            "module": module,
            "name": tpath.stem,
            "transcript": str(tpath),
            "summary": str(spath) if spath.exists() else None,
            "transcript_chars": len(tpath.read_text(encoding="utf-8")),
            "summary_chars": len(spath.read_text(encoding="utf-8")) if spath.exists() else 0,
        }
        lessons.append(entry)
        modules.setdefault(module, []).append(entry)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_lessons": len(lessons),
        "modules": {m: len(v) for m, v in modules.items()},
        "lessons": lessons,
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Human-readable index with relative links (angle brackets handle spaces).
    out = [
        "# Course Index",
        "",
        f"_Generated {manifest['generated_at']}_ · **{len(lessons)} lessons** "
        f"across {len(modules)} module(s)",
        "",
    ]
    for module in sorted(modules):
        items = modules[module]
        out.append(f"## {module} ({len(items)})")
        out.append("")
        for e in items:
            t_rel = Path(e["transcript"]).relative_to(data_dir).as_posix()
            line = f"- [{e['name']}](<{t_rel}>) · {e['transcript_chars'] // 1000}k chars"
            if e["summary"]:
                s_rel = Path(e["summary"]).relative_to(data_dir).as_posix()
                line += f" · [resumo](<{s_rel}>)"
            out.append(line)
        out.append("")
    (data_dir / "INDEX.md").write_text("\n".join(out), encoding="utf-8")

    return manifest


__all__ = ["build_index"]
