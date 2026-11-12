"""Red / green / ratchet fixtures for `check_http_detail_echoes_exception` (owner rule "no-leaking", 2026-11-11).

Each test builds a tiny repo; the keeper is real, nothing is patched. KB § PATTERNS/security/appsec-craft-canon.md."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.noctus.dev import http_detail_echo as h
from tools.noctus.dev.compliance import check_http_detail_echoes_exception

REPO = Path(__file__).resolve().parents[3]


def _repo(tmp_path: Path, files: dict[str, str], baseline: list[str] | None = None) -> Path:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    if baseline is not None:
        b = tmp_path / h.BASELINE_REL
        b.parent.mkdir(parents=True, exist_ok=True)
        b.write_text(json.dumps({"findings": {k: {} for k in baseline}}), encoding="utf-8")
    return tmp_path


def _handler(body: str) -> str:
    return f"from fastapi import HTTPException\ndef route():\n    try:\n        x()\n    except Exception as exc:\n{body}\n"


SEED = "seed/framework/backend/noctusai_seed/r.py"
PROD = "products/acme/backend/app/routers/r.py"


@pytest.mark.parametrize("expr", [
    "str(exc)", 'f"WAHA failed: {exc}"', "repr(exc)", "exc.args", "exc.args[0]", '"x: " + str(exc)',
    '{"detail": str(exc), "code": "x"}',
])
def test_red_exception_text_in_detail_is_refused_in_seed(tmp_path, expr):
    root = _repo(tmp_path, {SEED: _handler(f"        raise HTTPException(status_code=502, detail={expr})")})
    issues = check_http_detail_echoes_exception(root)
    assert len(issues) == 1 and issues[0]["file"] == SEED and "integration_error" in issues[0]["issue"]


def test_red_positional_detail_and_json_response_error_body(tmp_path):
    src = (
        "from fastapi import HTTPException\nfrom fastapi.responses import JSONResponse\n"
        "def a():\n    try:\n        x()\n    except Exception as e:\n        raise HTTPException(502, str(e))\n"
        "def b():\n    try:\n        x()\n    except Exception as e:\n"
        "        return JSONResponse(status_code=502, content={'error': str(e)})\n"
    )
    assert len(check_http_detail_echoes_exception(_repo(tmp_path, {SEED: src}))) == 2


def test_green_fixed_message_class_name_and_success_json(tmp_path):
    src = (
        "from fastapi import HTTPException\nfrom fastapi.responses import JSONResponse\n"
        "def a():\n    try:\n        x()\n    except Exception as exc:\n"
        "        log(exc)\n        raise HTTPException(status_code=502, detail='Falha ao falar com o WhatsApp')\n"
        "def b():\n    try:\n        x()\n    except Exception as exc:\n"
        "        raise HTTPException(status_code=502, detail=f'failed: {type(exc).__name__}')\n"
        "def c():\n    try:\n        x()\n    except Exception as exc:\n"
        "        return JSONResponse(status_code=200, content={'warning': str(exc)})\n"
        "def d(exc):\n    raise HTTPException(status_code=400, detail=str(exc))\n"  # not a caught exception name
    )
    assert check_http_detail_echoes_exception(_repo(tmp_path, {SEED: src})) == []


def test_green_escape_marks_domain_authored_text(tmp_path):
    body = "        raise HTTPException(422, detail=str(exc))  # detail-safe: domain-authored message"
    assert check_http_detail_echoes_exception(_repo(tmp_path, {SEED: _handler(body)})) == []


def test_name_does_not_leak_across_scopes(tmp_path):
    src = (
        "from fastapi import HTTPException\n"
        "def a():\n    try:\n        x()\n    except Exception as exc:\n        log(exc)\n"
        "    exc = 'static'\n    raise HTTPException(400, detail=str(exc))\n"
    )
    assert check_http_detail_echoes_exception(_repo(tmp_path, {SEED: src})) == []


class TestRatchet:
    echo = _handler("        raise HTTPException(status_code=502, detail=str(exc))")

    def test_existing_product_echo_in_baseline_passes(self, tmp_path):
        key = h.scan_source(self.echo, PROD)[0]["key"]
        assert check_http_detail_echoes_exception(_repo(tmp_path, {PROD: self.echo}, baseline=[key])) == []

    def test_new_product_echo_is_refused_while_backlog_drains(self, tmp_path):
        key = h.scan_source(self.echo, PROD)[0]["key"]
        second = self.echo + self.echo.replace("def route", "def other")
        issues = check_http_detail_echoes_exception(_repo(tmp_path, {PROD: second}, baseline=[key]))
        assert len(issues) == 1 and issues[0]["file"] == PROD

    def test_seed_is_never_baselined(self, tmp_path):
        key = h.scan_source(self.echo, SEED)[0]["key"]
        assert len(check_http_detail_echoes_exception(_repo(tmp_path, {SEED: self.echo}, baseline=[key]))) == 1

    def test_key_survives_line_shifts(self, tmp_path):
        key = h.scan_source(self.echo, PROD)[0]["key"]
        shifted = "# a\n# b\n" + self.echo
        assert check_http_detail_echoes_exception(_repo(tmp_path, {PROD: shifted}, baseline=[key])) == []

    def test_fixed_site_goes_stale_and_baseline_only_shrinks(self, tmp_path):
        key = h.scan_source(self.echo, PROD)[0]["key"]
        root = _repo(tmp_path, {PROD: _handler("        raise HTTPException(status_code=502, detail='x')")}, baseline=[key])
        assert h.stale_entries(root) == [key]
        h.write_baseline(root)  # shrink-only
        assert h.load_baseline(root) == {}
        # a new echo can NOT be added by the shrink rewrite
        (root / PROD).write_text(self.echo, encoding="utf-8")
        h.write_baseline(root)
        assert h.load_baseline(root) == {}


def test_tests_dirs_are_out_of_scope(tmp_path):
    root = _repo(tmp_path, {"seed/lib/backend/tests/test_x.py": _handler("        raise HTTPException(502, detail=str(exc))")})
    assert check_http_detail_echoes_exception(root) == []


class TestRealTree:
    def test_seed_has_zero_echoes(self):
        seed = [f for f in h.scan(REPO) if h.is_seed(f["file"])]
        assert seed == [], seed

    def test_assistant_has_zero_echoes(self):
        assert [f for f in h.scan(REPO) if f["file"].startswith("products/assistant/")] == []

    def test_repo_passes_with_committed_baseline(self):
        assert check_http_detail_echoes_exception(REPO) == []

    def test_seed_error_helper_body_is_code_only(self):
        from noctusai_lib.api.integration_errors import CATALOG, integration_error

        for code, (st, msg) in CATALOG.items():
            e = integration_error(code, exc=RuntimeError("http://waha-x:3000/secret"))
            assert e.status_code == st and e.detail == {"detail": msg, "code": code}
            assert "waha" not in msg.lower() and "http" not in msg.lower()  # fixed text, no host / env-style names


class TestHttpDetailEchoesException:
    """The detector's pinned true-positive / false-positive shapes (the parametrized cases above, in one place)."""

    def test_true_positive_f_string_with_internal_host(self, tmp_path):
        body = '        raise HTTPException(status_code=502, detail=f"WAHA QR fetch failed: {exc}")'
        assert len(check_http_detail_echoes_exception(_repo(tmp_path, {SEED: _handler(body)}))) == 1

    def test_false_positive_guard_fixed_message(self, tmp_path):
        body = '        raise HTTPException(status_code=502, detail={"detail": "Falha ao falar com o WhatsApp", "code": "waha_unavailable"})'
        assert check_http_detail_echoes_exception(_repo(tmp_path, {SEED: _handler(body)})) == []
