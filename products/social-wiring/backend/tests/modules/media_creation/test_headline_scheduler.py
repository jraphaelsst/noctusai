"""Daily automatic headline suggestions (contract 3.5): who gets a batch, dedupe, switches."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation import headline_scheduler as hs

ORG = "org-1"
NOW = datetime.now(timezone.utc)
CFG = SimpleNamespace(
    geracao_worker_enabled=True, headlines_sugeridas_por_dia_marca=5, headline_lotes_dia_usuario=30,
)


def _marca(sb, *, bio="Eu sou X", nichos=(3,), org=ORG):
    mid = str(uuid.uuid4())
    sb.from_("marcas").insert({"id": mid, "org_id": org, "name": "M"}).execute()
    sb.from_("cs_marca_perfil").insert({"marca_id": mid, "org_id": org, "bio": bio, "nichos": list(nichos)}).execute()
    return mid


def _viral(sb, *, nichos=(3,), score=5.0, org=ORG, e_viral=True):
    vid = str(uuid.uuid4())
    sb.from_("cs_virais").insert({
        "id": vid, "org_id": org, "perfil_id": "p1", "classificacao_status": "concluida", "blueprint": "BP",
        "blueprint_slots": [], "nicho_ids": list(nichos), "formato_ids": [], "score_viral": score,
        "e_viral": e_viral, "publicado_em": (NOW - timedelta(days=2)).isoformat(),
    }).execute()
    return vid


def _run(sb, repo=None, cfg=CFG):
    repo = repo or FakeJobRepository()
    out = asyncio.run(hs.gerar_sugestoes_diarias(client=lambda: sb, repo=repo, cfg=cfg))
    return out, repo


def _lotes(sb):
    return sb.from_("cs_headline_lotes").select("*").execute().data


class TestDailyRun:
    def test_schedule_is_0610_brt_and_registered_on_the_seed_scheduler(self):
        assert hs.CRON == "10 6 * * *" and hs.JOB_ID == "headline_sugestoes_diarias"
        from noctusai_lib.api import scheduler as seed_scheduler

        hs.configure()
        hs.configure()  # idempotent: re-registering replaces, never duplicates
        pending = [j for j in seed_scheduler.scheduler.get_jobs() if j.id == hs.JOB_ID]
        assert len(pending) == 1 and pending[0].misfire_grace_time == hs.MISFIRE_GRACE_SECONDS
        assert str(pending[0].trigger).startswith("cron[") and "hour='6'" in str(pending[0].trigger)
        assert "minute='10'" in str(pending[0].trigger)

    def test_one_automatic_batch_per_eligible_marca(self):
        sb = MockSupabaseClient()
        a, b = _marca(sb), _marca(sb)
        for i in range(7):
            _viral(sb, score=float(i))
        out, repo = _run(sb)
        assert out == {"criados": 2, "ignorados": 0, "falhas": 0}
        rows = _lotes(sb)
        assert {r["marca_id"] for r in rows} == {a, b} and {r["origem"] for r in rows} == {"sugestao_auto"}
        assert all(len(r["parametros"]["viral_ids"]) == 5 and r["created_by"] is None for r in rows)
        assert len(repo._jobs) == 2

    def test_skips_marcas_without_bio_or_niche_and_other_org_virals_never_leak(self):
        sb = MockSupabaseClient()
        ok = _marca(sb)
        _marca(sb, bio="  ")
        _marca(sb, nichos=())
        mine = _viral(sb)
        _viral(sb, org="other-org")
        out, _ = _run(sb)
        assert out == {"criados": 1, "ignorados": 2, "falhas": 0}
        [row] = _lotes(sb)
        assert row["marca_id"] == ok and row["parametros"]["viral_ids"] == [mine]

    def test_a_second_run_the_same_day_creates_nothing(self):
        sb = MockSupabaseClient()
        _marca(sb)
        _viral(sb)
        _run(sb)
        out, repo = _run(sb)
        assert out == {"criados": 0, "ignorados": 1, "falhas": 0} and len(_lotes(sb)) == 1 and repo._jobs == {}

    def test_no_structures_means_no_batch_never_an_empty_completo(self):
        sb = MockSupabaseClient()
        _marca(sb)
        _viral(sb, e_viral=False)
        out, _ = _run(sb)
        assert out["criados"] == 0 and out["ignorados"] == 1 and _lotes(sb) == []

    def test_worker_off_skips_the_whole_run(self):
        sb = MockSupabaseClient()
        _marca(sb)
        _viral(sb)
        out, _ = _run(sb, cfg=SimpleNamespace(**{**CFG.__dict__, "geracao_worker_enabled": False}))
        assert out == {"criados": 0, "ignorados": 0, "falhas": 0} and _lotes(sb) == []

    def test_one_marca_failing_does_not_stop_the_others(self):
        sb = MockSupabaseClient()
        _marca(sb)
        _marca(sb)
        _viral(sb)

        class FlakyRepo(FakeJobRepository):
            n = 0

            async def enqueue(self, **kw):
                FlakyRepo.n += 1
                if FlakyRepo.n == 1:
                    raise RuntimeError("queue blip")
                return await super().enqueue(**kw)

        out, _ = _run(sb, repo=FlakyRepo())
        assert out["criados"] == 1 and out["ignorados"] + out["falhas"] == 1

    def test_the_job_never_raises(self):
        def boom():
            raise RuntimeError("db down")

        out = asyncio.run(hs.gerar_sugestoes_diarias(client=boom, repo=FakeJobRepository(), cfg=CFG))
        assert out == {"criados": 0, "ignorados": 0, "falhas": 0}
