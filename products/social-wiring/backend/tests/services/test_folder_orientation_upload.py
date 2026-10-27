"""Folder-orientation upload flow: landscape → video, portrait → Short,
exclusive-listing logo detection, ambiguous-group menu + resume.

Seams only (no monkeypatching): ``FakeWatermarkDetector`` is injected via
the constructor; the test subclass records ``_reply`` / child ``_run_upload``
instead of touching WAHA / YouTube; Redis is an in-memory fake.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.modules.youtube.services.watermark import (
    FakeWatermarkDetector,
    LogoVerdict,
    WatermarkDetectionError,
)
from app.schemas.whatsapp import PendingUpload
from app.services.gdrive_service import VideoCandidate
from app.services.whatsapp_intake_service import WhatsAppIntakeService

PHONE = "+5544999999999"


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, ex=None):
        self.store[k] = v

    def delete(self, *ks):
        for k in ks:
            self.store.pop(k, None)

    def incr(self, k, amount=1):
        self.store[k] = int(self.store.get(k, 0)) + amount
        return self.store[k]

    def decr(self, k):
        self.store[k] = int(self.store.get(k, 0)) - 1
        return self.store[k]

    def expire(self, *_a):
        return True


class _Intake(WhatsAppIntakeService):
    """Records outbound replies and child uploads instead of doing IO."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.replies: list[str] = []
        self.uploads: list[PendingUpload] = []
        self.preheld: list[bool] = []

    async def _reply(self, phone, text):
        self.replies.append(text)

    async def _run_upload(self, phone, pending, *, counter_preheld=False):
        self.uploads.append(pending)
        self.preheld.append(counter_preheld)


def _intake(detector, tmp_path) -> _Intake:
    return _Intake(
        waha_base_url="https://waha.example.com",
        waha_api_key="k",
        waha_session="default",
        redis_client=FakeRedis(),
        authorized_numbers=[],
        crm_service=None,
        admin_supabase=None,
        youtube_service=None,
        upload_dir=tmp_path,
        org_id=uuid4(),
        watermark_detector=detector,
    )


def _cand(tmp_path: Path, name: str, fmt: str) -> VideoCandidate:
    p = tmp_path / name
    p.write_bytes(b"x" * 10)
    return VideoCandidate(local_path=p, file_name=name, file_size_bytes=10, format=fmt)


def _pending(**kw) -> PendingUpload:
    return PendingUpload(
        product_code="ONE1", drive_url="https://drive.google.com/drive/folders/abc",
        crm_title="Casa", **kw,
    )


async def _plan_and_dispatch(intake, cands):
    pending = _pending()
    msgs: list[str] = []

    async def say(m):
        msgs.append(m)

    chosen = await intake._plan_orientation_upload(PHONE, pending, cands, say)
    if chosen is None:
        return pending, None, msgs
    spawned = await intake._dispatch_selected_videos(
        PHONE, pending, chosen, say=say, inline_ok=True
    )
    await asyncio.sleep(0)
    return pending, spawned, msgs


def test_two_video_folder_uploads_both_without_vision(tmp_path):
    det = FakeWatermarkDetector()
    intake = _intake(det, tmp_path)
    cands = [_cand(tmp_path, "tour.mp4", "youtube"), _cand(tmp_path, "reel.mp4", "reels")]
    pending, spawned, msgs = asyncio.run(_plan_and_dispatch(intake, cands))
    assert det.calls == []
    assert spawned is True
    assert sorted(u.local_video_filename for u in intake.uploads) == ["reel.mp4", "tour.mp4"]
    assert all("Parte" not in (u.crm_title or "") for u in intake.uploads)
    assert intake.preheld == [True, True]
    assert len(msgs) == 1
    assert "🎬 Vídeo: tour.mp4" in msgs[0] and "📱 Short: reel.mp4" in msgs[0]
    assert "Exclusividade" not in msgs[0]


def test_exclusive_folder_picks_logo_version_per_group(tmp_path):
    det = FakeWatermarkDetector(logo_files=["tour_one.mp4", "reel_one.mp4"])
    intake = _intake(det, tmp_path)
    cands = [
        _cand(tmp_path, "tour_one.mp4", "youtube"),
        _cand(tmp_path, "tour_clean.mp4", "youtube"),
        _cand(tmp_path, "reel_one.mp4", "reels"),
        _cand(tmp_path, "reel_clean.mp4", "reels"),
    ]
    pending, spawned, msgs = asyncio.run(_plan_and_dispatch(intake, cands))
    assert len(det.calls) == 2
    assert sorted(u.local_video_filename for u in intake.uploads) == ["reel_one.mp4", "tour_one.mp4"]
    assert "Exclusividade" in msgs[0]
    # partner versions deleted from disk
    assert not (tmp_path / "tour_clean.mp4").exists()
    assert not (tmp_path / "reel_clean.mp4").exists()
    assert (tmp_path / "tour_one.mp4").exists()


def test_single_landscape_only_runs_inline(tmp_path):
    det = FakeWatermarkDetector()
    intake = _intake(det, tmp_path)
    pending, spawned, msgs = asyncio.run(
        _plan_and_dispatch(intake, [_cand(tmp_path, "a.mp4", "unknown")])
    )
    assert spawned is False  # caller uploads inline
    assert pending.local_video_filename == "a.mp4"
    assert det.calls == [] and intake.uploads == []
    assert msgs == ["🎬 Vídeo: a.mp4"]


def test_single_portrait_only_is_a_short(tmp_path):
    intake = _intake(FakeWatermarkDetector(), tmp_path)
    pending, spawned, msgs = asyncio.run(
        _plan_and_dispatch(intake, [_cand(tmp_path, "r.mp4", "reels")])
    )
    assert spawned is False
    assert pending.local_video_filename == "r.mp4"
    assert msgs == ["📱 Short: r.mp4"]


def test_vision_failure_opens_menu_then_resume_uploads_everything(tmp_path):
    # landscape pair: ambiguous (vision error); portrait pair: clear.
    class _Det(FakeWatermarkDetector):
        async def detect(self, videos):
            if videos[0].name.startswith("tour"):
                raise WatermarkDetectionError("quota")
            return await super().detect(videos)

    det = _Det(logo_files=["reel_one.mp4"])
    intake = _intake(det, tmp_path)
    cands = [
        _cand(tmp_path, "tour_a.mp4", "youtube"),
        _cand(tmp_path, "tour_b.mp4", "youtube"),
        _cand(tmp_path, "reel_one.mp4", "reels"),
        _cand(tmp_path, "reel_clean.mp4", "reels"),
    ]
    pending, chosen, msgs = asyncio.run(_plan_and_dispatch(intake, cands))
    assert chosen is None and intake.uploads == []
    assert pending.state == "awaiting_video_choice"
    assert pending.choice_kind == "video"
    assert [c.file_name for c in pending.decided_videos] == ["reel_one.mp4"]
    assert "tour_a.mp4" in msgs[0] and "tour_b.mp4" in msgs[0]

    # user answers "2" -> tour_b + the already-decided short are uploaded
    saved = PendingUpload(**json.loads(intake._redis.store[intake._redis_key(PHONE)]))

    async def answer():
        await intake._handle_video_choice(PHONE, "2", saved)
        await asyncio.sleep(0)

    asyncio.run(answer())
    assert sorted(u.local_video_filename for u in intake.uploads) == ["reel_one.mp4", "tour_b.mp4"]
    assert not (tmp_path / "tour_a.mp4").exists()
    assert not (tmp_path / "reel_clean.mp4").exists()
    assert "🎬 Vídeo: tour_b.mp4" in intake.replies[-1]
    assert "📱 Short: reel_one.mp4" in intake.replies[-1]


def test_two_ambiguous_groups_ask_in_sequence_and_cancel_cleans_all(tmp_path):
    det = FakeWatermarkDetector(verdicts={
        n: LogoVerdict(False, 0.9)
        for n in ("t1.mp4", "t2.mp4", "r1.mp4", "r2.mp4")
    })
    intake = _intake(det, tmp_path)
    cands = [
        _cand(tmp_path, "t1.mp4", "youtube"), _cand(tmp_path, "t2.mp4", "youtube"),
        _cand(tmp_path, "r1.mp4", "reels"), _cand(tmp_path, "r2.mp4", "reels"),
    ]
    pending, chosen, _ = asyncio.run(_plan_and_dispatch(intake, cands))
    assert chosen is None
    assert pending.choice_kind == "video" and len(pending.group_queue) == 1

    async def flow():
        await intake._handle_video_choice(PHONE, "1", pending)
        assert pending.choice_kind == "short"
        assert "verticais" in intake.replies[-1]
        await intake._handle_video_choice(PHONE, "todos", pending)
        await asyncio.sleep(0)

    asyncio.run(flow())
    names = sorted(u.local_video_filename for u in intake.uploads)
    assert names == ["r1.mp4", "r2.mp4", "t1.mp4"]
    titles = {u.local_video_filename: u.crm_title for u in intake.uploads}
    assert titles["t1.mp4"] == "Casa"
    assert titles["r1.mp4"].endswith("Parte 1/2")


def test_cancel_in_orientation_menu_deletes_every_file(tmp_path):
    det = FakeWatermarkDetector(error=WatermarkDetectionError("boom"))
    intake = _intake(det, tmp_path)
    cands = [
        _cand(tmp_path, "t1.mp4", "youtube"), _cand(tmp_path, "t2.mp4", "youtube"),
        _cand(tmp_path, "r1.mp4", "reels"), _cand(tmp_path, "r2.mp4", "reels"),
    ]
    pending, chosen, _ = asyncio.run(_plan_and_dispatch(intake, cands))
    assert chosen is None

    asyncio.run(intake._handle_video_choice(PHONE, "cancelar", pending))
    assert list(tmp_path.iterdir()) == []
    assert intake._redis.get(intake._redis_key(PHONE)) is None
