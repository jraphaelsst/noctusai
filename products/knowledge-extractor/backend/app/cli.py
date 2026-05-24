"""Command-line entry point for the extraction flow.

Temporary surface (noc § MCP-first): on absorption this becomes product routers
plus a `noctus.*` MCP tool. Run from the `backend/` directory:

    python -m app.cli run --drive-url "<folder share link>"
    python -m app.cli run --video /path/to/class.mp4
    python -m app.cli run --fake          # no keys / no ffmpeg — sample data
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.integrations.google_drive import make_drive_downloader
from app.logging_config import get_logger
from app.pipeline import build_default_pipeline, build_fake_pipeline, is_video
from app.services.indexing import build_index

logger = get_logger("cli")

# Fake-pipeline impl lives in app.pipeline (single source of truth, shared with
# the runs API `POST /api/runs {fake:true}`).
_build_fake_pipeline = build_fake_pipeline


async def _tree(args: argparse.Namespace) -> int:
    """Render the recursive file tree of a Drive folder (no download)."""
    from app.integrations.google_drive.drive_v3_adapter import DriveV3Downloader

    downloader = make_drive_downloader()
    if not isinstance(downloader, DriveV3Downloader):
        print("tree needs the Drive v3 backend — set DRIVE_BACKEND=oauth.")
        return 2

    entries = await downloader.walk_tree(args.drive_url)
    print(f"\n{args.drive_url}")

    n_files = n_videos = 0
    total_bytes = 0
    for path, is_folder, df in entries:
        indent = "  " * (len(path.parts) - 1)
        if is_folder:
            print(f"{indent}📂 {path.name}/")
            continue
        is_vid = is_video(df)
        n_files += 1
        n_videos += int(is_vid)
        total_bytes += df.size_bytes or 0
        size = f"{df.size_bytes / 1e6:.1f} MB" if df.size_bytes else "?"
        print(f"{indent}{'🎬' if is_vid else '📄'} {path.name}  ({size})")

    print(
        f"\nTotals: {n_files} file(s), {n_videos} video(s), "
        f"{total_bytes / 1e9:.2f} GB across the tree."
    )
    return 0


async def _list_folders(args: argparse.Namespace) -> int:
    """Connectivity probe — list top-level folders (My Drive + Shared with me)."""
    from app.integrations.google_drive.drive_v3_adapter import DriveV3Downloader

    downloader = make_drive_downloader()
    if not isinstance(downloader, DriveV3Downloader):
        print("list-folders needs the Drive v3 backend — set DRIVE_BACKEND=oauth.")
        return 2

    n = args.limit
    mine = await downloader.list_folders(parent="root", limit=n)
    print(f"\n📁 My Drive — first {n} folder(s):")
    for f in mine[:n]:
        print(f"   • {f.name}")
    if not mine:
        print("   (none)")

    shared = await downloader.list_folders(shared_with_me=True, limit=n)
    print(f"\n🤝 Shared with me — first {n} folder(s):")
    for f in shared[:n]:
        print(f"   • {f.name}   [id: {f.id}]")
    if not shared:
        print("   (none)")
    return 0


async def _check_drive(args: argparse.Namespace) -> int:
    """Reachability probe — list the shared folder without downloading."""
    downloader = make_drive_downloader()
    files = await downloader.list_folder(args.drive_url)
    videos = [f for f in files if is_video(f)]

    print(f"\n✓ Reached the folder — {len(files)} file(s), {len(videos)} video(s):\n")
    for f in files:
        is_vid = is_video(f)
        size = f"{f.size_bytes / 1e6:.1f} MB" if f.size_bytes else "?"
        print(f"  {'🎬' if is_vid else '  '} {f.name}  ({size})")
    if not videos:
        print("\n⚠ No video files detected — check the folder/share or the extensions.")
    return 0


async def _list_modules(args: argparse.Namespace) -> int:
    """List the module subfolders of a course folder (with their ids)."""
    from app.integrations.google_drive import parse_drive_url
    from app.integrations.google_drive.drive_v3_adapter import DriveV3Downloader

    downloader = make_drive_downloader()
    if not isinstance(downloader, DriveV3Downloader):
        print("list-modules needs the Drive v3 backend — set DRIVE_BACKEND=oauth.")
        return 2

    course_id = parse_drive_url(args.drive_url)
    folders = await downloader.list_folders(parent=course_id, limit=100)
    print(f"\nModules in {course_id}:\n")
    for f in folders:
        print(f"  • {f.name}   [id: {f.id}]")
    return 0


async def _run_module(args: argparse.Namespace) -> int:
    """Transcribe + summarize one module folder, organized + resumable."""
    pipeline = build_default_pipeline()
    await pipeline.run_module(args.folder_id, args.name, wait_seconds=args.wait)

    print(
        f"\n✓ Module done — {len(pipeline.results)} processed, "
        f"{len(pipeline.skipped)} skipped, {len(pipeline.failures)} failed."
    )
    for r in pipeline.results:
        print(f"  • [{r.module}] {r.name}")
        print(f"      transcript: {r.transcript_path}")
        print(f"      summary:    {r.summary_path}")
    for s in pipeline.skipped:
        print(f"  ⏭ skipped (already done): {s}")
    for fd in pipeline.failures:
        print(f"  ✗ FAILED: {fd['module']}/{fd['title']} — {fd['error']}")

    # Refresh the cumulative course index so manifest.json/INDEX.md stay whole.
    build_index(pipeline.data_dir)
    return 0


async def _resummarize(args: argparse.Namespace) -> int:
    """Regenerate summaries from existing transcripts (upgraded prompt, no download)."""
    pipeline = build_default_pipeline()
    await pipeline.resummarize(
        only=args.only, wait_seconds=args.wait, overwrite=not args.skip_existing
    )
    build_index(pipeline.data_dir)
    print(
        f"\n✓ Resummarized {len(pipeline.results)} lesson(s), "
        f"{len(pipeline.skipped)} skipped, {len(pipeline.failures)} failed."
    )
    for fd in pipeline.failures:
        print(f"  ✗ FAILED: {fd['module']}/{fd['title']} — {fd['error']}")
    return 0


async def _methodology(args: argparse.Namespace) -> int:
    """Step 2: synthesize the course methodology from the lesson summaries."""
    from app.services.methodology_service import extract_methodology

    result = await extract_methodology(get_settings().data_path)
    print(f"\n✓ Methodology extracted across {len(result['modules'])} module(s):")
    for f in result["module_files"]:
        print(f"  • {f}")
    print(f"\n  → {result['course_file']}")
    return 0


def _export_docx(args: argparse.Namespace) -> int:
    """Export METHODOLOGY.md + each methodology/*.md to methodology/docx/*.docx."""
    from app.services.docx_export import export_methodology_docx

    written = export_methodology_docx(get_settings().data_path)
    if not written:
        print("Nothing to export — run `methodology` first.")
        return 1
    print(f"\n✓ Exported {len(written)} .docx file(s):")
    for p in written:
        print(f"  • {p}")
    return 0


# Drive folder that mirrors local data/ for this course ("Transcrições/Resumos").
_DEFAULT_PUBLISH_PARENT = "1ZrtvzTD2BYVDu33Mv7c2CAIVdp2wbrLi"


async def _upload_docx(args: argparse.Namespace) -> int:
    """Generate summaries+transcripts docx and upload them into Drive.

    Mirrors the methodology docx layout: data/<kind>/<module>/docx/*.docx →
    Drive <parent>/<kind>/<module>/docx/. Requires Drive write (drive.file);
    runs a one-time consent the first time the broadened scope is needed.
    """
    from app.integrations.google_drive import WRITE_SCOPES, DriveV3Downloader
    from app.integrations.google_drive.oauth import get_oauth_credentials
    from app.services.docx_export import export_methodology_docx, export_tree_docx
    from app.services.drive_publish import ensure_child_folder, publish_docx_tree

    settings = get_settings()
    data = settings.data_path

    # 1) (re)generate the docx locally — cheap, deterministic, no network.
    kinds = list(args.kind)
    generated: dict[str, int] = {}
    for kind in kinds:
        generated[kind] = len(export_tree_docx(data / kind))
    if args.methodology:
        generated["methodology"] = len(export_methodology_docx(data))
    print("\nGenerated docx locally:")
    for kind, n in generated.items():
        print(f"  • {kind}: {n} file(s)")

    # 2) build a write-capable Drive client (consent runs here if scope missing).
    creds = get_oauth_credentials(settings, scopes=WRITE_SCOPES)
    downloader = DriveV3Downloader(oauth_credentials=creds)

    # 3) upload each kind under <parent>/<kind>/.
    parent_id = args.parent_id
    total_uploaded = total_skipped = 0
    for kind in kinds:
        kind_folder = await ensure_child_folder(downloader, kind, parent_id)
        results = await publish_docx_tree(
            downloader,
            parent_id=kind_folder.id,
            local_root=data / kind,
            overwrite=args.overwrite,
        )
        uploaded = [r for r in results if not r.skipped]
        skipped = [r for r in results if r.skipped]
        total_uploaded += len(uploaded)
        total_skipped += len(skipped)
        print(f"\n📂 {kind}/ — {len(uploaded)} uploaded, {len(skipped)} skipped:")
        for r in uploaded:
            print(f"  ✓ [{r.module}] {r.name}")
        for r in skipped:
            print(f"  ⏭ already in Drive: [{r.module}] {r.name}")

    print(f"\n✓ Done — {total_uploaded} uploaded, {total_skipped} skipped (already present).")
    return 0


def _index(args: argparse.Namespace) -> int:
    """Rebuild the cumulative course index (manifest.json + INDEX.md) from disk."""
    data_dir = get_settings().data_path
    m = build_index(data_dir)
    print(
        f"\n✓ Index built — {m['total_lessons']} lessons across "
        f"{len(m['modules'])} module(s):"
    )
    for mod, n in sorted(m["modules"].items()):
        print(f"  {n:3d}  {mod}")
    print(f"\n  → {data_dir / 'INDEX.md'}")
    print(f"  → {data_dir / 'manifest.json'}")
    return 0


def _check_anon(args: argparse.Namespace) -> int:
    """Scan methodology/docs for anonymization-policy leaks. Non-zero on findings."""
    import subprocess

    from app.config import REPO_ROOT
    from app.services.anonymization import scan_paths

    data_dir = get_settings().data_path
    if args.staged:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True,
        )
        files = [
            REPO_ROOT / f
            for f in proc.stdout.splitlines()
            if f.endswith(".md")
            and (f.startswith("data/methodology/") or f.startswith("doc/") or f == "data/METHODOLOGY.md")
        ]
    elif args.paths:
        files = [Path(p) for p in args.paths]
    else:
        files = sorted((data_dir / "methodology").rglob("*.md"))
        files += sorted((REPO_ROOT / "doc").rglob("*.md"))
        if (data_dir / "METHODOLOGY.md").exists():
            files.append(data_dir / "METHODOLOGY.md")

    results = scan_paths(files)
    total = sum(len(v) for v in results.values())
    if total == 0:
        print(f"✓ check-anon: clean ({len(results)} file(s) scanned, 0 findings).")
        return 0
    print(f"✗ check-anon: {total} finding(s) — anonymization policy violated:")
    for path, findings in results.items():
        for f in findings:
            print(f"  {path}:{f.line} [{f.kind}] {f.match!r} — {f.context[:80]}")
    return 1


def _build_manual(args: argparse.Namespace) -> int:
    """Assemble METHODOLOGY.md deterministically from the per-module files (no LLM)."""
    from app.services.methodology_service import build_manual

    out = build_manual(get_settings().data_path)
    print(f"\n✓ Manual assembled → {out}")
    return 0


async def _audit_coverage(args: argparse.Namespace) -> int:
    """Audit transcript→methodology coverage per module (writes doc/analysis/)."""
    from app.services.coverage_audit import audit_all

    written = await audit_all(get_settings().data_path, only=args.only)
    print(f"\n✓ Coverage audit — {len(written)} module report(s):")
    for mod, p in written.items():
        print(f"  • {mod} → {p}")
    return 0


async def _kb_build(args: argparse.Namespace) -> int:
    """Build the local KB cache: embed methodology chunks → data/kb_local.json."""
    from app.integrations.llm import generate_embedding
    from app.integrations.vectors import make_vector_store
    from app.services.kb_ingest import ingest_methodology

    settings = get_settings()
    store = make_vector_store(use_local=True)
    result = await ingest_methodology(settings.data_path, store=store, embed_fn=generate_embedding)
    print(
        f"\n✓ Local KB built — {result['documents']} doc(s), "
        f"{result['chunks_ingested']} chunk(s) ingested, "
        f"{result.get('chunks_skipped', 0)} skipped (anonymization guard)."
    )
    print(f"  → {settings.kb_local_path}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    if args.fake:
        logger.info("running FAKE pipeline (sample data, no keys)")
        pipeline = _build_fake_pipeline()
        await pipeline.run_from_drive("fake://folder")
    elif args.drive_url:
        pipeline = build_default_pipeline()
        await pipeline.run_from_drive(args.drive_url)
    elif args.drive_file:
        pipeline = build_default_pipeline()
        await pipeline.run_drive_files(args.drive_file)
    elif args.video:
        pipeline = build_default_pipeline()
        await pipeline.run_local([Path(v) for v in args.video])
    else:
        logger.error("nothing to do — pass --drive-url, --video, or --fake")
        return 2

    print(f"\n✓ Processed {len(pipeline.results)} video(s).")
    for r in pipeline.results:
        print(f"  • {r.name}")
        print(f"      transcript: {r.transcript_path}")
        print(f"      summary:    {r.summary_path}")
    print(f"  manifest: {pipeline.data_dir / 'manifest.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knowledge-extractor")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the extraction flow")
    src = run.add_mutually_exclusive_group(required=True)
    src.add_argument("--drive-url", help="Google Drive folder share link")
    src.add_argument("--drive-file", action="append", help="Drive file id to process (repeatable)")
    src.add_argument("--video", action="append", help="local video file (repeatable)")
    src.add_argument("--fake", action="store_true", help="demo with sample data, no keys")

    check = sub.add_parser("check-drive", help="list a shared folder without downloading")
    check.add_argument("--drive-url", required=True, help="Google Drive folder share link")

    lf = sub.add_parser("list-folders", help="list top-level folders (connectivity probe)")
    lf.add_argument("--limit", type=int, default=3, help="how many per section (default 3)")

    tree = sub.add_parser("tree", help="render a folder's recursive file tree (no download)")
    tree.add_argument("--drive-url", required=True, help="Drive folder share link or id")

    lm = sub.add_parser("list-modules", help="list module subfolders of a course folder")
    lm.add_argument("--drive-url", required=True, help="course folder link or id")

    rm = sub.add_parser("run-module", help="transcribe+summarize one module (organized, resumable)")
    rm.add_argument("--folder-id", required=True, help="module folder id")
    rm.add_argument("--name", help="module label (default: the folder's own name)")
    rm.add_argument("--wait", type=int, default=5, help="seconds between lessons (default 5)")

    sub.add_parser("index", help="rebuild the cumulative course index (manifest.json + INDEX.md)")

    rs = sub.add_parser("resummarize", help="regenerate summaries from existing transcripts")
    rs.add_argument("--only", help="filter lessons by case-insensitive substring")
    rs.add_argument("--wait", type=int, default=0, help="seconds between lessons (default 0)")
    rs.add_argument("--skip-existing", action="store_true", help="skip lessons already summarized")

    sub.add_parser("methodology", help="extract the course methodology from transcripts (Step 2)")

    sub.add_parser("export-docx", help="export the methodology markdown files to .docx")

    ca = sub.add_parser("check-anon", help="scan methodology/docs for anonymization-policy leaks")
    ca.add_argument("--staged", action="store_true", help="scan git-staged files (pre-commit hook)")
    ca.add_argument("paths", nargs="*", help="explicit files to scan (default: methodology + doc)")

    sub.add_parser("build-manual", help="assemble METHODOLOGY.md from per-module files (deterministic)")

    ac = sub.add_parser("audit-coverage", help="audit transcript→methodology coverage per module")
    ac.add_argument("--only", help="filter modules by case-insensitive substring")

    sub.add_parser("kb-build", help="build the local KB cache (embed methodology → data/kb_local.json)")

    ud = sub.add_parser(
        "upload-docx",
        help="generate summaries/transcripts docx and upload them into Drive",
    )
    ud.add_argument(
        "--kind",
        action="append",
        choices=["summaries", "transcripts"],
        help="content to publish (repeatable; default: summaries + transcripts)",
    )
    ud.add_argument(
        "--parent-id",
        default=_DEFAULT_PUBLISH_PARENT,
        help="Drive folder to publish under (default: this course's Transcrições/Resumos)",
    )
    ud.add_argument(
        "--methodology",
        action="store_true",
        help="also (re)generate the methodology docx locally before uploading",
    )
    ud.add_argument(
        "--overwrite",
        action="store_true",
        help="re-upload docx even if a file of the same name already exists in Drive",
    )

    args = parser.parse_args(argv)
    if args.command == "upload-docx" and not args.kind:
        args.kind = ["summaries", "transcripts"]  # default: publish both
    if args.command == "run":
        return asyncio.run(_run(args))
    if args.command == "check-drive":
        return asyncio.run(_check_drive(args))
    if args.command == "list-folders":
        return asyncio.run(_list_folders(args))
    if args.command == "tree":
        return asyncio.run(_tree(args))
    if args.command == "list-modules":
        return asyncio.run(_list_modules(args))
    if args.command == "run-module":
        return asyncio.run(_run_module(args))
    if args.command == "index":
        return _index(args)
    if args.command == "export-docx":
        return _export_docx(args)
    if args.command == "check-anon":
        return _check_anon(args)
    if args.command == "build-manual":
        return _build_manual(args)
    if args.command == "audit-coverage":
        return asyncio.run(_audit_coverage(args))
    if args.command == "kb-build":
        return asyncio.run(_kb_build(args))
    if args.command == "upload-docx":
        return asyncio.run(_upload_docx(args))
    if args.command == "resummarize":
        return asyncio.run(_resummarize(args))
    if args.command == "methodology":
        return asyncio.run(_methodology(args))
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
