"""youtube_chat_commands — parser table + executor flows (fakes, no patching)."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import fakeredis
import pytest

from app.services.youtube_chat_commands import (
    HELP_TEXT,
    ChatCommand,
    YouTubeChatCommands,
    parse_command,
)

ORG = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ONE10874 titulo Casa linda", ChatCommand("titulo", "ONE10874", None, "Casa linda")),
        ("one10874 TÍTULO: Casa linda", ChatCommand("titulo", "ONE10874", None, "Casa linda")),
        ("ONE10874 descrição linha 1\nlinha 2", ChatCommand("descricao", "ONE10874", None, "linha 1\nlinha 2")),
        ("ONE10874 privacidade publico", ChatCommand("privacidade", "ONE10874", None, "public")),
        ("ONE10874 privacidade Público", ChatCommand("privacidade", "ONE10874", None, "public")),
        ("ONE10874 privacidade privada", ChatCommand("privacidade", "ONE10874", None, "private")),
        ("ONE10874 privacidade não listado", ChatCommand("privacidade", "ONE10874", None, "unlisted")),
        ("ONE10874 privacidade unlisted", ChatCommand("privacidade", "ONE10874", None, "unlisted")),
        ("ONE10874 privacidade banana", ChatCommand("privacidade", "ONE10874", None, None)),
        ("ONE10874 apagar", ChatCommand("apagar", "ONE10874")),
        ("ONE10874 Excluir!", ChatCommand("apagar", "ONE10874")),
        ("ONE10874 deletar", ChatCommand("apagar", "ONE10874")),
        ("ONE10874 tentar de novo", ChatCommand("retry", "ONE10874")),
        ("ONE10874 refazer", ChatCommand("retry", "ONE10874")),
        ("ONE10874 retry", ChatCommand("retry", "ONE10874")),
        ("ONE10874 status", ChatCommand("status", "ONE10874")),
        ("ONE10874 short privacidade publico", ChatCommand("privacidade", "ONE10874", "short", "public")),
        ("ONE10874 video apagar", ChatCommand("apagar", "ONE10874", "video")),
        ("ONE10874 shorts status", ChatCommand("status", "ONE10874", "short")),
        ("ajuda", ChatCommand("help")),
        ("Comandos", ChatCommand("help")),
    ],
)
def test_parse_positive(text, expected):
    assert parse_command(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "ONE10874",
        "ONE10874 https://drive.google.com/drive/folders/abc",
        "https://drive.google.com/drive/folders/abc ONE10874",
        "oi tudo bem?",
        "sim",
        "não",
        "ONE10874 status do imóvel hoje?",
        "ONE10874 apagar tudo agora",
        "ONE10874 tituloX",
        "ONE10874x titulo a",
        "titulo ONE10874 a",
    ],
)
def test_parse_must_not_match(text):
    assert parse_command(text) is None


# ─── fakes ───────────────────────────────────────────────────────────────
class FakeYT:
    def __init__(self, fail_ids=()):
        self.updates: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.fail_ids = set(fail_ids)

    def update_video_metadata(self, *, org_id, video_id, title=None, description=None, privacy_status=None):
        if video_id in self.fail_ids:
            raise RuntimeError("quota")
        self.updates.append(
            {"id": video_id, "title": title, "description": description, "privacy": privacy_status}
        )

    def delete_youtube_video(self, *, org_id, video_id):
        if video_id in self.fail_ids:
            raise RuntimeError("quota")
        self.deleted.append(video_id)


class FakeJobs:
    def __init__(self, rows):
        self.rows = rows

    def list_jobs(self, code):
        return [r for r in self.rows if r["product_code"] == code]


class FakeRetrier:
    def __init__(self):
        self.retried: list[str] = []

    def retry(self, job_id):
        self.retried.append(job_id)


class FakeCatalog:
    def __init__(self):
        self.updates, self.deletes = [], []

    def mirror_update(self, video_id, patch):
        self.updates.append((video_id, patch))

    def mirror_delete(self, video_id):
        self.deletes.append(video_id)


ROWS = [
    {"id": "j3", "product_code": "ONE10874", "youtube_video_id": "SHORT1", "status": "published",
     "target_format": "shorts", "privacy_status": "private", "title": "ONE10874 — a"},
    {"id": "j2", "product_code": "ONE10874", "youtube_video_id": "VID1", "status": "notified",
     "target_format": "youtube", "privacy_status": "public", "title": "ONE10874 — b"},
    {"id": "j1", "product_code": "ONE10874", "youtube_video_id": None, "status": "failed",
     "target_format": "youtube", "privacy_status": "private", "title": "ONE10874 — c",
     "error_message": "drive offline"},
    {"id": "j0", "product_code": "ONE10874", "youtube_video_id": "VID1", "status": "published",
     "target_format": "youtube", "privacy_status": "private", "title": "dup"},
]


def make(rows=ROWS, yt=None, ttl=600):
    r = fakeredis.FakeRedis(decode_responses=True)
    yt = yt or FakeYT()
    retrier, cat = FakeRetrier(), FakeCatalog()
    ex = YouTubeChatCommands(
        org_id=ORG, youtube=yt, jobs=FakeJobs(rows), retrier=retrier,
        redis_client=r, catalog=cat, confirm_ttl_seconds=ttl,
    )
    return ex, yt, retrier, cat, r


def run(ex, text, sid="s1"):
    return asyncio.run(ex.try_handle(sid, text))


def test_non_command_returns_none():
    ex, *_ = make()
    assert run(ex, "ONE10874 https://drive.google.com/x") is None
    assert run(ex, "oi") is None


def test_help():
    ex, *_ = make()
    assert run(ex, "ajuda") == HELP_TEXT


def test_title_applies_to_video_and_short_with_prefix_and_dedup():
    ex, yt, _, cat, _ = make()
    out = run(ex, "ONE10874 titulo Casa nova")
    assert [u["id"] for u in yt.updates] == ["SHORT1", "VID1"]
    assert all(u["title"] == "ONE10874 — Casa nova" for u in yt.updates)
    assert [v for v, _ in cat.updates] == ["SHORT1", "VID1"]
    assert out.count("✅") == 2


def test_title_already_prefixed_kept_and_too_long_refused():
    ex, yt, *_ = make()
    run(ex, "ONE10874 titulo ONE10874 — Já tem")
    assert yt.updates[0]["title"] == "ONE10874 — Já tem"
    yt.updates.clear()
    out = run(ex, "ONE10874 titulo " + "x" * 100)
    assert "longo demais" in out and not yt.updates


def test_description_cap_and_multiline():
    ex, yt, *_ = make()
    run(ex, "ONE10874 descricao a\nb")
    assert yt.updates[0]["description"] == "a\nb"
    yt.updates.clear()
    assert "longa demais" in run(ex, "ONE10874 descricao " + "x" * 5001)
    assert not yt.updates


def test_privacy_and_invalid_privacy():
    ex, yt, *_ = make()
    run(ex, "ONE10874 privacidade nao listado")
    assert {u["privacy"] for u in yt.updates} == {"unlisted"}
    assert "inválida" in run(ex, "ONE10874 privacidade banana")


def test_qualifier_filters():
    ex, yt, *_ = make()
    run(ex, "ONE10874 short privacidade publico")
    assert [u["id"] for u in yt.updates] == ["SHORT1"]
    yt.updates.clear()
    run(ex, "ONE10874 video privacidade publico")
    assert [u["id"] for u in yt.updates] == ["VID1"]


def test_not_found():
    ex, *_ = make()
    assert run(ex, "ONE99999 titulo x") == "Não encontrei vídeos publicados de ONE99999."


def test_partial_failure_reported():
    ex, yt, *_ = make(yt=FakeYT(fail_ids={"SHORT1"}))
    out = run(ex, "ONE10874 titulo x")
    assert "falhou — quota" in out and [u["id"] for u in yt.updates] == ["VID1"]


def test_status_lists_all_rows():
    ex, *_ = make()
    out = run(ex, "ONE10874 status")
    assert "https://youtu.be/SHORT1" in out and "Short" in out
    assert "falhou" not in out or "drive offline" in out
    assert "drive offline" in out and "privado" in out and "público" in out


def test_retry_only_failed():
    ex, _, retrier, *_ = make()
    out = run(ex, "ONE10874 tentar de novo")
    assert retrier.retried == ["j1"] and "reenfileirado" in out
    ex2, _, r2, *_ = make(rows=[ROWS[0]])
    assert "Não há envios com falha" in run(ex2, "ONE10874 refazer")
    assert r2.retried == []


def test_delete_confirmation_yes():
    ex, yt, _, cat, r = make()
    out = run(ex, "ONE10874 apagar")
    assert "Responda *SIM* para apagar ou *NÃO* para cancelar" in out
    assert not yt.deleted and ex.has_pending_confirmation("s1")
    assert not ex.has_pending_confirmation("other")
    assert r.ttl("ytcmd:confirm:s1") > 0
    out = run(ex, "Sim")
    assert yt.deleted == ["SHORT1", "VID1"] and cat.deletes == ["SHORT1", "VID1"]
    assert not ex.has_pending_confirmation("s1")
    assert run(ex, "sim") is None


def test_delete_confirmation_no():
    ex, yt, *_ = make()
    run(ex, "ONE10874 short apagar")
    assert "nada foi apagado" in run(ex, "NÃO")
    assert not yt.deleted and not ex.has_pending_confirmation("s1")


def test_delete_confirmation_expired():
    ex, yt, _, _, r = make()
    run(ex, "ONE10874 apagar")
    r.delete("ytcmd:confirm:s1")  # TTL elapsed
    assert run(ex, "sim") is None and not yt.deleted


def test_yes_no_without_pending_falls_through():
    ex, *_ = make()
    assert run(ex, "sim") is None and run(ex, "não") is None


def test_other_text_during_pending_falls_through_and_keeps_pending():
    ex, yt, *_ = make()
    run(ex, "ONE10874 apagar")
    assert run(ex, "talvez") is None
    assert ex.has_pending_confirmation("s1")


def test_new_command_supersedes_pending():
    ex, yt, *_ = make()
    run(ex, "ONE10874 apagar")
    run(ex, "ONE10874 status")
    assert not ex.has_pending_confirmation("s1")
    assert run(ex, "sim") is None and not yt.deleted


def test_delete_failure_reported_not_silent():
    ex, yt, _, cat, _ = make(yt=FakeYT(fail_ids={"VID1"}))
    run(ex, "ONE10874 apagar")
    out = run(ex, "sim")
    assert "nada foi apagado" in out and yt.deleted == ["SHORT1"] and cat.deletes == ["SHORT1"]
