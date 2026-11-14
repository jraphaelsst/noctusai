"""`check_signed_url_ttl` + `check_pii_query_params` -- red/green fixtures, escape markers and the per-file
ratchet. KB § PATTERNS/security/url-hygiene.md"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import url_hygiene as uh  # noqa: E402
from tools.noctus.dev.compliance import check_pii_query_params, check_signed_url_ttl, REPO_ROOT  # noqa: E402

SVC = "products/demo/backend/app/services/files.py"
ROUTER = "products/demo/backend/app/routers/people.py"
TTL_BL = "mcp/noctusai/tests/signed_url_ttl_baseline.json"
PII_BL = "mcp/noctusai/tests/pii_query_params_baseline.json"


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _baseline(root: Path, rel: str, files: dict[str, int]) -> None:
    _write(root, rel, json.dumps({"arquivos": files}))


class TestSignedUrlTtl:
    def test_literal_over_cap_flagged(self):
        assert uh.signed_url_ttl_hits("await s.signed_url(bucket='b', key='k', expires_in_seconds=3600)") == [(1, 3600)]

    def test_module_constant_and_arithmetic_resolved(self):
        src = "TTL = 60 * 60\nawait s.signed_url(bucket='b', key='k', expires_in_seconds=TTL)\n"
        assert [t for _, t in uh.signed_url_ttl_hits(src)] == [3600]

    def test_positional_storage3_call(self):
        assert uh.signed_url_ttl_hits("bucket.create_signed_url(path, 7200)") == [(1, 7200)]

    def test_at_or_below_cap_clean(self):
        assert uh.signed_url_ttl_hits("s.signed_url(bucket='b', key='k', expires_in_seconds=600)") == []

    def test_unresolvable_ttl_clean(self):
        assert uh.signed_url_ttl_hits("s.signed_url(bucket='b', key='k', expires_in_seconds=cfg.ttl)") == []

    def test_ttl_reason_kwarg_accepted(self):
        assert uh.signed_url_ttl_hits("s.signed_url(bucket='b', key='k', expires_in_seconds=3600, ttl_reason='export')") == []

    def test_other_reason_kwarg_not_accepted(self):
        # Only the seam's kwarg (validate_signed_url_ttl(..., ttl_reason)) escapes; a stray `reason=` would not reach it.
        assert uh.signed_url_ttl_hits("s.signed_url(bucket='b', key='k', expires_in_seconds=3600, reason='export')") == [(1, 3600)]

    def test_comment_escape(self):
        src = "s.signed_url(bucket='b', key='k', expires_in_seconds=3600)  # signed-url-ttl-ok: offline export\n"
        assert uh.signed_url_ttl_hits(src) == []

    def test_definition_default_flagged(self):
        src = "class S:\n    async def signed_url(self, path, *, expires_in_seconds: int = 3600):\n        ...\n"
        assert uh.signed_url_ttl_hits(src) == [(2, 3600)]

    def test_ttl_constant_flagged(self):
        assert uh.signed_url_ttl_hits("SIGNED_URL_TTL_SECONDS = 3600\n") == [(1, 3600)]
        assert uh.signed_url_ttl_hits("SIGNED_URL_TTL_SECONDS = 300\n") == []

    def test_ratchet_blocks_new_and_demands_lowering(self, tmp_path):
        _write(tmp_path, SVC, "s.signed_url(bucket='b', key='k', expires_in_seconds=3600)\n")
        assert len(check_signed_url_ttl(tmp_path)) == 1  # no baseline -> blocks
        _baseline(tmp_path, TTL_BL, {SVC: 1})
        assert check_signed_url_ttl(tmp_path) == []
        _write(tmp_path, SVC, "s.signed_url(bucket='b', key='k', expires_in_seconds=300)\n")
        stale = check_signed_url_ttl(tmp_path)
        assert len(stale) == 1 and "lower" in stale[0]["issue"]

    def test_lower_never_raises(self, tmp_path):
        _write(tmp_path, SVC, "s.signed_url(bucket='b', key='k', expires_in_seconds=3600)\n")
        _baseline(tmp_path, TTL_BL, {})
        assert uh.lower_signed_url_ttl_baseline(tmp_path) == {}


class TestPiiQueryParams:
    def test_explicit_query_flagged(self):
        src = "from fastapi import Query\ndef f(email: str = Query(None)):\n    ...\n"
        assert uh.pii_query_param_hits(src) == [(2, "f", "email")]

    def test_plain_scalar_on_get_flagged(self):
        src = "@router.get('/x')\nasync def f(cpf: str):\n    ...\n"
        assert [p for *_, p in uh.pii_query_param_hits(src)] == ["cpf"]

    def test_post_scalar_not_flagged_without_query(self):
        assert uh.pii_query_param_hits("@router.post('/x')\nasync def f(cpf: str):\n    ...\n") == []

    def test_path_param_and_body_model_clean(self):
        assert uh.pii_query_param_hits("@router.get('/x/{cpf}')\nasync def f(cpf: str):\n    ...\n") == []
        assert uh.pii_query_param_hits("@router.get('/x')\nasync def f(payload: Person):\n    ...\n") == []

    def test_non_pii_and_generic_names_clean(self):
        src = "@router.get('/x')\nasync def f(nome: str = Query(None), name: str = Query(None), cep: str = Query(None), tipo_documento: str = Query(None)):\n    ...\n"
        assert uh.pii_query_param_hits(src) == []

    def test_token_match_compound_names(self):
        assert uh.is_pii_name("cliente_email") and uh.is_pii_name("telefone_lead") and uh.is_pii_name("documento")
        assert not uh.is_pii_name("emailed_at") and not uh.is_pii_name("phonebook_id")

    def test_escape_marker_needs_reason(self):
        ok = "def f(email: str = Query(None)):  # pii-query-ok: operator lookup, never logged\n    ...\n"
        bare = "def f(email: str = Query(None)):  # pii-query-ok:\n    ...\n"
        assert uh.pii_query_param_hits(ok) == []
        assert len(uh.pii_query_param_hits(bare)) == 1

    def test_ratchet(self, tmp_path):
        _write(tmp_path, ROUTER, "def f(email: str = Query(None)):\n    ...\n")
        assert len(check_pii_query_params(tmp_path)) == 1
        _baseline(tmp_path, PII_BL, {ROUTER: 1})
        assert check_pii_query_params(tmp_path) == []
        _write(tmp_path, ROUTER, "def f(email: str = Query(None), cpf: str = Query(None)):\n    ...\n")
        assert len(check_pii_query_params(tmp_path)) == 1  # grew past baseline


class TestRealTree:
    def test_real_tree_green_against_baseline(self):
        assert check_signed_url_ttl(REPO_ROOT) == []
        assert check_pii_query_params(REPO_ROOT) == []
