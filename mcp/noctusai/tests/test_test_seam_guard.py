"""`test_seam_guard` — the write-time half of the no-self-monkeypatch rule.

Per `KB § PATTERNS/common/methodology-execution-discipline.md` principle 4
("prove the check can FAIL — a green that cannot go red proves nothing"),
every case below is paired: the guard must DENY the violation and must stay
silent on the legitimate shape next to it. A guard that only ever allows is
indistinguishable from no guard at all.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD_PATH = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "test_seam_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("noc_test_seam_guard_under_test", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

TEST_PATH = str(REPO_ROOT / "products" / "social-wiring" / "backend" / "tests" / "test_x.py")

SELF_PATCH = '''
from app.services import clientes_service

def test_thing(monkeypatch):
    monkeypatch.setattr(clientes_service, "resolve", lambda *_: None)
    assert True
'''

EXTERNAL_PATCH = '''
import httpx

def test_thing(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *_: None)
    assert True
'''

ALLOWLISTED = '''
from app.services import clientes_service

def test_thing(monkeypatch):
    monkeypatch.setattr(  # self-patch-ok: neutralises ambient .env, not our logic
        clientes_service, "resolve", lambda *_: None
    )
    assert True
'''

DI_SEAM = '''
from app.services import clientes_service

def test_thing():
    result = clientes_service.resolve(store=FakeStore())
    assert result is None
'''


class TestDeniesTheViolation:
    def test_write_of_a_self_patching_test_is_refused(self):
        verdict = guard.decide("Write", {"file_path": TEST_PATH, "content": SELF_PATCH})
        assert verdict is not None
        assert "clientes_service.resolve" in " ".join(verdict["targets"])

    def test_the_refusal_names_the_remedy_not_just_the_sin(self):
        """A refusal that does not say what to do instead gets retried a
        different way — the whole reason the primary guard spells it out."""
        verdict = guard.decide("Write", {"file_path": TEST_PATH, "content": SELF_PATCH})
        reason = verdict["reason"]
        assert "di-test-seam" in reason
        assert "dependency_overrides" in reason
        assert "self-patch-ok" in reason

    def test_it_says_not_to_route_around_via_bash(self):
        verdict = guard.decide("Write", {"file_path": TEST_PATH, "content": SELF_PATCH})
        assert "check_no_self_monkeypatch" in verdict["reason"]


class TestStaysQuietOnLegitimateWork:
    def test_patching_an_external_boundary_is_allowed(self):
        assert guard.decide("Write", {"file_path": TEST_PATH, "content": EXTERNAL_PATCH}) is None

    def test_the_allowlist_comment_is_honoured(self):
        """Same escape the keeper honours — written once, accepted at both ends."""
        assert guard.decide("Write", {"file_path": TEST_PATH, "content": ALLOWLISTED}) is None

    def test_a_real_di_seam_is_allowed(self):
        assert guard.decide("Write", {"file_path": TEST_PATH, "content": DI_SEAM}) is None

    def test_non_test_files_are_not_policed(self):
        src = str(REPO_ROOT / "products" / "social-wiring" / "backend" / "app" / "svc.py")
        assert guard.decide("Write", {"file_path": src, "content": SELF_PATCH}) is None

    def test_unrelated_tools_pass_through(self):
        assert guard.decide("Read", {"file_path": TEST_PATH}) is None
        assert guard.decide("Bash", {"command": "pytest"}) is None


class TestFailsSafely:
    def test_unparseable_content_is_not_a_violation(self):
        """A half-typed file must not be refused — the keeper sees the
        finished article regardless."""
        assert guard.decide("Write", {"file_path": TEST_PATH, "content": "def broken("}) is None

    def test_missing_file_for_an_edit_is_not_a_violation(self):
        verdict = guard.decide(
            "Edit",
            {"file_path": str(REPO_ROOT / "tests" / "nope_does_not_exist.py"),
             "old_string": "a", "new_string": "b"},
        )
        assert verdict is None

    def test_env_override_disables_the_write_time_half(self, monkeypatch):
        monkeypatch.setenv(guard.ALLOW_ENV, "1")  # self-patch-ok: env var, not our logic
        assert guard.decide("Write", {"file_path": TEST_PATH, "content": SELF_PATCH}) is None


class TestEditPathReconstructsTheWholeFile:
    def test_an_edit_that_introduces_a_self_patch_is_refused(self, tmp_path):
        f = tmp_path / "tests" / "test_edited.py"
        f.parent.mkdir(parents=True)
        f.write_text("from app.services import clientes_service\n\n\ndef test_a():\n    assert True\n")
        # Point the guard at a path it will treat as ours.
        target = str(f).replace(str(tmp_path), str(REPO_ROOT / "products" / "x"))

        verdict = guard.find_self_patches(
            f.read_text() + '\n\ndef test_b(monkeypatch):\n    monkeypatch.setattr(clientes_service, "resolve", None)\n',
            target,
        )
        assert verdict, "an edit that adds a self-patch must be detected"

    def test_a_fragment_alone_would_not_have_parsed(self):
        """Why the Edit path reconstructs the file instead of parsing
        `new_string`: the fragment on its own is not valid Python, so a
        fragment-parse would silently find nothing — a false green inside
        the guard itself."""
        fragment = '    monkeypatch.setattr(clientes_service, "resolve", None)'
        assert guard.find_self_patches(fragment, TEST_PATH) == []


class TestSharesThePredicateWithTheKeeper:
    def test_it_uses_the_keepers_own_helpers(self):
        """If this module grew its own predicate, the two ends could disagree
        — an agent blocked for something the keeper permits learns to distrust
        both gates. Pin the import so a future refactor cannot quietly fork it.
        """
        comp = guard._load_compliance()
        for helper in (
            "_extract_patch_target",
            "_resolve_target_via_imports",
            "_classify_patch_target",
            "_build_import_map",
            "_SELF_PATCH_OK_COMMENT_RE",
        ):
            assert hasattr(comp, helper), f"keeper helper {helper} moved — guard would fork"


class TestTheHookActuallyFiresInProduction:
    """The guard runs under whatever `python3` is on PATH — NOT the venv.

    This class exists because the first version of this guard imported
    `compliance.py`, which imports pydantic at module scope. Under the system
    interpreter that raised, the hook failed OPEN by design, and the guard
    silently never fired. Every test above still passed, because they run
    under the venv. Only exercising the hook end-to-end caught it.

    So: assert the predicate module is importable with NO third-party
    packages available, and that the hook process itself emits a deny.
    """

    def test_predicate_module_imports_with_no_site_packages(self):
        """`-I` isolates the interpreter: no user site, no PYTHONPATH."""
        import subprocess

        leaf = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "self_patch_predicate.py"
        proc = subprocess.run(
            [sys.executable, "-I", "-c",
             "import importlib.util,sys;"
             f"spec=importlib.util.spec_from_file_location('p',r'{leaf}');"
             "m=importlib.util.module_from_spec(spec);sys.modules['p']=m;"
             "spec.loader.exec_module(m);print('ok')"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            "the predicate module must import with stdlib only — a third-party "
            f"import here silently disables the write-time guard.\n{proc.stderr}"
        )

    def test_the_hook_process_emits_a_deny(self, tmp_path):
        """End-to-end through the real hook script, not the module."""
        import json as _json
        import subprocess

        hook = REPO_ROOT / "scripts" / "hooks" / "claude-guard-test-seams.py"
        payload = _json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": TEST_PATH, "content": SELF_PATCH},
        })
        proc = subprocess.run(
            [sys.executable, str(hook)], input=payload, capture_output=True, text=True
        )
        assert proc.returncode == 0
        assert proc.stdout.strip(), (
            f"hook produced no verdict — it failed open. stderr: {proc.stderr}"
        )
        out = _json.loads(proc.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_the_hook_is_wired_into_settings(self):
        """A guard nothing invokes is not a guard."""
        import json as _json

        settings = _json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
        wired = _json.dumps(settings.get("hooks", {}).get("PreToolUse", []))
        assert "claude-guard-test-seams.py" in wired
