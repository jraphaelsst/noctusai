"""Request-path latency (2026-10-21): the process-wide clients are built ONCE, the
base auth dependency validates a token at most once per TTL, and the blocking
Supabase call never runs on the event loop. KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest

from noctusai_seed.database import DatabaseModule
from noctusai_seed.dependencies import ProductDependencies


def _settings() -> SimpleNamespace:
    key = "a" * 40 + "." + "b" * 40 + "." + "c" * 20
    return SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_anon_key=key,
        supabase_service_role_key=key,
    )


def _jwt(sub="u1", exp_in=3600):
    return pyjwt.encode({"sub": sub, "exp": int(time.time() + exp_in)}, "k" * 32, algorithm="HS256")


class TestProcessWideClients:
    def test_core_client_is_built_once_and_stable(self):
        db = DatabaseModule(_settings(), "orbity")
        assert db.get_core_client() is db.get_core_client()
        raw = db._raw_core()
        assert raw is db._raw_core()

    def test_core_client_is_pinned_to_public_even_after_a_cross_schema_call(self):
        db = DatabaseModule(_settings(), "orbity")
        core = db.get_core_client()
        core.schema("other")  # a deliberate one-off cross-schema call
        core.table("noctus_users")
        assert db._raw_core().options.schema == "public"

    def test_admin_client_still_cached_and_distinct_from_core(self):
        db = DatabaseModule(_settings(), "orbity")
        assert db.get_admin_client() is db.get_admin_client()
        assert db.get_admin_client() is not db.get_core_client()

    def test_user_clients_are_per_call_so_one_users_jwt_never_reaches_another(self):
        db = DatabaseModule(_settings(), "orbity")
        a, b = db.get_client("h.AAA.s"), db.get_client("h.BBB.s")
        assert a is not b
        assert a.postgrest.session.headers["authorization"] == "Bearer h.AAA.s"
        assert b.postgrest.session.headers["authorization"] == "Bearer h.BBB.s"

    def test_first_call_race_builds_one_client(self):
        import threading

        db = DatabaseModule(_settings(), "orbity")
        out = []
        ts = [threading.Thread(target=lambda: out.append(db._raw_core())) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert len({id(c) for c in out}) == 1


class _Db:
    def __init__(self, delay=0.0):
        self.built = 0
        self.get_user_calls = 0
        self._delay = delay

    def get_client(self):
        self.built += 1

        def get_user(_token):
            self.get_user_calls += 1
            if self._delay:
                time.sleep(self._delay)
            return SimpleNamespace(user=SimpleNamespace(id="u1", user_metadata={}))

        return SimpleNamespace(auth=SimpleNamespace(get_user=get_user))


class TestBaseDependencyValidatesOncePerTtl:
    def test_two_requests_with_the_same_token_ask_supabase_once(self):
        db = _Db()
        deps = ProductDependencies(db)
        tok = _jwt()

        async def go():
            u1, _ = await deps.get_current_user_ungated(f"Bearer {tok}")
            u2, _ = await deps.get_current_user_ungated(f"Bearer {tok}")
            return u1, u2

        u1, u2 = asyncio.run(go())
        assert u1.id == u2.id == "u1"
        assert db.get_user_calls == 1 and db.built == 1

    def test_concurrent_requests_overlap_instead_of_serialising(self):
        db = _Db(delay=0.3)
        deps = ProductDependencies(db)
        toks = [_jwt(sub=f"u{i}") for i in range(3)]

        async def go():
            return await asyncio.gather(*(deps.get_current_user_ungated(f"Bearer {t}") for t in toks))

        t0 = time.perf_counter()
        asyncio.run(go())
        assert time.perf_counter() - t0 < 0.7
        assert db.get_user_calls == 3

    def test_a_rejected_token_is_asked_again(self):
        from fastapi import HTTPException

        class Rejecting(_Db):
            def get_client(self):
                self.built += 1

                def get_user(_t):
                    self.get_user_calls += 1
                    return SimpleNamespace(user=None)

                return SimpleNamespace(auth=SimpleNamespace(get_user=get_user))

        db = Rejecting()
        deps = ProductDependencies(db)
        tok = _jwt()

        async def go():
            for _ in range(2):
                with pytest.raises(HTTPException) as e:
                    await deps.get_current_user_ungated(f"Bearer {tok}")
                assert e.value.status_code == 401

        asyncio.run(go())
        assert db.get_user_calls == 2
