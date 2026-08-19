"""Regression tests for check_conftest_env_setdefault.

THE INCIDENT THIS ENCODES
─────────────────────────
p-studio's `conftest.py` carried

    os.environ.setdefault("ASAAS_WEBHOOK_TOKEN", "token-de-webhook-de-teste")

and the platform `.env` carries `ASAAS_WEBHOOK_TOKEN=` — present, EMPTY. Any
process that loads that file (the MCP server, therefore `predeploy_check`)
exports the key, `setdefault` treats it as already-set, and the suite runs with
an empty expected token: 15 of 20 webhook tests fail on a 503 that has nothing
to do with what they assert. Run from a plain shell, all 20 pass.

The suite was reporting on the developer's shell, in BOTH directions — it also
means a green local run proves nothing about CI, and vice versa.

The sharper half: `setdefault("SUPABASE_SERVICE_ROLE_KEY", "")` and
`setdefault("PROVEDOR_COBRANCA", "fake")` in the same file, and the same shape
in therapy-platform directly beneath a comment promising the suite "never
reaches a real Supabase". Export the real values and it does.

KB § PATTERNS/compliance/testing.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_conftest_env_setdefault,
)

PATH = "products/p-studio/backend/tests/conftest.py"


class TestConftestEnvSetdefault:
    """Class shape is load-bearing: `check_detector_has_regression_test`
    matches `class Test<CamelCase-of-detector>`, so a file of bare module-level
    functions reads to it as "this detector has no test at all"."""



    def _check(self, source: str):
        return check_conftest_env_setdefault(conftests={PATH: source})


    def test_the_incident_verbatim(self):
        """🔴 THE line. If this stops flagging, the class is live again."""
        found = self._check('os.environ.setdefault("ASAAS_WEBHOOK_TOKEN", "token-de-teste")')
        assert len(found) == 1
        assert found[0]["severity"] == "high"
        assert found[0]["product"] == "p-studio"
        # The message must name the remedy — a refusal that only forbids gets
        # satisfied by writing the same thing a different way.
        assert "own_test_env" in found[0]["issue"]


    def test_credentials_and_endpoints_are_all_covered(self):
        for key in (
            "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
            "ENCRYPTION_KEY", "ASAAS_API_KEY", "ASAAS_BASE_URL",
            "P_STUDIO_ORG_ID", "STRIPE_ACCESS_TOKEN",
        ):
            assert self._check(f'os.environ.setdefault("{key}", "x")'), key


    def test_a_locally_generated_session_key_stays_exempt(self):
        """Two products deliberately let a real Fernet key win, and say so. Any
        valid key works there, so it is harmless — and a keeper that flagged it
        would be red forever, which is how a keeper stops being read."""
        assert self._check('_os.environ.setdefault("SESSION_ENCRYPTION_KEY", _Fernet.generate_key().decode())') == []
        assert self._check('_os.environ.setdefault("REDIS_SESSION_ENCRYPTION_KEY", _k)') == []


    def test_an_unrelated_key_is_not_flagged(self):
        assert self._check('os.environ.setdefault("PYTHONHASHSEED", "0")') == []
        assert self._check('os.environ.setdefault("TZ", "UTC")') == []


    def test_the_prefixed_alias_form_is_caught_too(self):
        """`import os as _os` is the house style in three of the four conftests —
        matching only the bare `os.` spelling would have missed all of them."""
        assert self._check('_os.environ.setdefault("SUPABASE_URL", "http://test.local")')


    def test_plain_assignment_is_what_we_want_and_is_never_flagged(self):
        assert self._check('os.environ["ASAAS_WEBHOOK_TOKEN"] = "token-de-teste"') == []
        assert self._check('own_test_env({"ASAAS_WEBHOOK_TOKEN": "token-de-teste"})') == []


    def test_the_line_number_points_at_the_offending_call(self):
        src = "\n".join(["# header", "import os", 'os.environ.setdefault("SUPABASE_URL", "x")'])
        found = self._check(src)
        assert found[0]["file"].endswith(":3")


    def test_the_live_tree_is_clean(self):
        """Both offenders are fixed. This is the check that keeps them fixed."""
        assert check_conftest_env_setdefault() == []
