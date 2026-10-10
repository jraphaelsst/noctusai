"""`check_redis_client_via_seam` — every Redis client is built by the seed seam.

→ KB § PATTERNS/backend/redis-auth-seam.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_redis_client_via_seam  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SEAM = "seed/lib/backend/noctusai_lib/integrations/redis.py"


def _w(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def _files(issues):
    return sorted({i["file"] for i in issues})


class TestBypassesAreFlagged:
    def test_each_construction_shape_is_flagged(self, tmp_path):
        shapes = {
            "a.py": "import redis\nredis.from_url('x')\n",
            "b.py": "from redis import Redis\nRedis.from_url('x')\n",
            "c.py": "import redis\nredis.Redis(host='h')\n",
            "d.py": "import redis.asyncio as ar\nar.Redis.from_url('x')\n",
            "e.py": "from redis.asyncio import Redis\nRedis(host='h')\n",
            "f.py": "import aioredis\n",
            "g.py": "from redis import StrictRedis\nStrictRedis()\n",
            "h.py": "from redis import ConnectionPool\nConnectionPool.from_url('x')\n",
        }
        for name, body in shapes.items():
            _w(tmp_path, f"seed/lib/backend/pkg/{name}", body)
        got = check_redis_client_via_seam(tmp_path)
        assert _files(got) == sorted(f"seed/lib/backend/pkg/{n}" for n in shapes)
        assert all(i["severity"] == "high" for i in got)

    def test_product_backend_is_scanned(self, tmp_path):
        _w(tmp_path, "products/acme/backend/app/x.py", "import redis\nredis.from_url('x')\n")
        got = check_redis_client_via_seam(tmp_path)
        assert got and got[0]["product"] == "acme"


class TestCleanAndExempt:
    def test_seam_module_is_exempt(self, tmp_path):
        _w(tmp_path, SEAM, "from redis import Redis\nRedis.from_url('x')\n")
        assert check_redis_client_via_seam(tmp_path) == []

    def test_tests_and_fakeredis_are_exempt(self, tmp_path):
        _w(tmp_path, "seed/lib/backend/tests/test_x.py", "import redis\nredis.from_url('x')\n")
        _w(tmp_path, "seed/lib/backend/pkg/conftest.py", "import redis\nredis.from_url('x')\n")
        _w(tmp_path, "seed/lib/backend/pkg/f.py", "import fakeredis\nfakeredis.FakeStrictRedis()\n")
        assert check_redis_client_via_seam(tmp_path) == []

    def test_seam_consumer_is_clean(self, tmp_path):
        _w(tmp_path, "seed/lib/backend/pkg/ok.py",
           "from noctusai_lib.integrations.redis import make_async_redis_client\n"
           "c = make_async_redis_client('redis://h')\n")
        assert check_redis_client_via_seam(tmp_path) == []


class TestPathsScoping:
    def test_paths_restricts_to_staged_files(self, tmp_path):
        _w(tmp_path, "seed/lib/backend/pkg/bad.py", "import redis\nredis.from_url('x')\n")
        _w(tmp_path, "seed/lib/backend/pkg/other.py", "x = 1\n")
        assert check_redis_client_via_seam(tmp_path, paths=["seed/lib/backend/pkg/other.py"]) == []
        assert _files(check_redis_client_via_seam(tmp_path, paths=["seed/lib/backend/pkg/bad.py"])) == [
            "seed/lib/backend/pkg/bad.py"
        ]


def test_seed_tree_is_clean():
    seed_only = [i for i in check_redis_client_via_seam(REPO) if i["product"] == "seed"]
    assert seed_only == []
