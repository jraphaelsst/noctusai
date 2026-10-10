"""Regression suite for `check_product_guide_cochange` (keeper) and its
guide-derivation helper, plus `scan_live_state_claims` (advisory tool).

Synthetic trees under tmp_path; no git, no network (the staged list, commit
message, Supabase executor and prod-tip resolver are all injected).

→ KB § PATTERNS/common/live-state-alignment.md
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import migrate_product as mp  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_product_guide_cochange,
    check_product_guide_cochange_range,
    derive_help_chat_guides,
)
from tools.noctus.dev.scan_live_state_claims import scan_live_state_claims  # noqa: E402

GUIDE = "products/igig/backend/app/knowledge/guia-igig.md"


def _w(root: Path, rel: str, body: str = "x\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(body))


def _tree(tmp: Path) -> Path:
    _w(tmp, "deploy/fleet/active-scope.txt", "igig\ncore\nother\n")
    _w(tmp, GUIDE, "# guia\n")
    _w(tmp, "products/igig/backend/app/routers/ajuda_router.py", '''
        from pathlib import Path
        from noctusai_lib.domain.help_chat import create_help_chat_router
        GUIA_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "guia-igig.md"
        router = create_help_chat_router(product_name="IgIg", knowledge_path=GUIA_PATH)
    ''')
    _w(tmp, "products/other/backend/app/main.py", "x = 1\n")
    return tmp


class TestProductGuideCochange:
    def test_derives_guide_from_consumer(self, tmp_path):
        guides, unresolved = derive_help_chat_guides(_tree(tmp_path))
        assert guides == {"igig": [GUIDE]} and unresolved == []

    def test_behaviour_without_guide_flags(self, tmp_path):
        root = _tree(tmp_path)
        out = check_product_guide_cochange(root, staged=["products/igig/frontend/src/pages/A.tsx"])
        assert len(out) == 1 and out[0]["severity"] == "high" and GUIDE in out[0]["issue"]

    def test_backend_behaviour_flags(self, tmp_path):
        root = _tree(tmp_path)
        assert check_product_guide_cochange(root, staged=["products/igig/backend/app/services/x.py"])

    def test_guide_staged_passes(self, tmp_path):
        root = _tree(tmp_path)
        assert not check_product_guide_cochange(
            root, staged=["products/igig/backend/app/services/x.py", GUIDE])

    def test_tests_and_migrations_do_not_fire(self, tmp_path):
        root = _tree(tmp_path)
        staged = ["products/igig/backend/tests/test_x.py",
                  "products/igig/frontend/src/a.test.tsx",
                  "products/igig/backend/migrations/001_x.sql"]
        assert not check_product_guide_cochange(root, staged=staged)

    def test_product_without_guide_never_fires(self, tmp_path):
        root = _tree(tmp_path)
        assert not check_product_guide_cochange(root, staged=["products/other/backend/app/main.py"])

    def test_seed_help_chat_change_flags_every_consumer(self, tmp_path):
        root = _tree(tmp_path)
        out = check_product_guide_cochange(
            root, staged=["seed/lib/backend/noctusai_lib/domain/help_chat/service.py"])
        assert [i["product"] for i in out] == ["igig"]

    def test_seed_help_chat_tests_do_not_fire(self, tmp_path):
        root = _tree(tmp_path)
        assert not check_product_guide_cochange(
            root, staged=["seed/lib/backend/noctusai_lib/domain/help_chat/tests/test_a.py"])

    def test_trailer_escape_hatch_requires_reason(self, tmp_path):
        root = _tree(tmp_path)
        staged = ["products/igig/backend/app/services/x.py"]
        ok = check_product_guide_cochange(
            root, staged=staged, commit_message="fix: x\n\nGuide-Unaffected: pure refactor\n")
        assert ok == []
        empty = check_product_guide_cochange(
            root, staged=staged, commit_message="fix: x\n\nGuide-Unaffected:\n")
        assert empty

    def test_unresolvable_knowledge_path_is_reported_not_dropped(self, tmp_path):
        root = _tree(tmp_path)
        _w(root, "products/igig/backend/app/routers/ajuda_router.py", '''
            from noctusai_lib.domain.help_chat import create_help_chat_router
            router = create_help_chat_router(product_name="IgIg", knowledge_path=get_guide)
        ''')
        out = check_product_guide_cochange(root, staged=["products/igig/backend/app/services/x.py"])
        assert out == [] or all(i["severity"] == "warning" for i in out)
        _, unresolved = derive_help_chat_guides(root)
        assert unresolved and unresolved[0]["product"] == "igig"


ORG = "df6c3ace-1111-2222-3333-444455556666"
OTHER = "aaaa1111-1111-2222-3333-444455556666"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _commit(root: Path, files: dict[str, str], msg: str) -> str:
    for rel, body in files.items():
        _w(root, rel, body)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", msg)
    return _git(root, "rev-parse", "HEAD")


def _repo(tmp: Path) -> tuple[Path, str]:
    root = _tree(tmp)
    _git(root, "init", "-q")
    return root, _commit(root, {}, "base")


class TestProductGuideCochangeRange:
    """CI leg: each commit of a range judged on its own diff + message (real git)."""

    def test_behaviour_commit_without_guide_flags_and_names_commit(self, tmp_path):
        root, base = _repo(tmp_path)
        bad = _commit(root, {"products/igig/backend/app/services/x.py": "y = 2\n"}, "feat: change")
        out = check_product_guide_cochange_range(f"{base}..HEAD", repo_root=root)
        assert len(out) == 1 and out[0]["severity"] == "high"
        assert bad[:9] in out[0]["issue"] and GUIDE in out[0]["issue"]

    def test_commit_with_guide_or_trailer_passes(self, tmp_path):
        root, base = _repo(tmp_path)
        _commit(root, {"products/igig/backend/app/services/x.py": "y = 2\n", GUIDE: "# guia v2\n"},
                "feat: change + guide")
        _commit(root, {"products/igig/backend/app/services/z.py": "z = 1\n"},
                "refactor: rename\n\nGuide-Unaffected: internal rename, no behaviour change")
        assert check_product_guide_cochange_range(f"{base}..HEAD", repo_root=root) == []

    def test_each_commit_is_judged_alone_not_the_squashed_range(self, tmp_path):
        # The guide landing in a LATER commit does not excuse the earlier one —
        # the commit-msg hook would have refused that earlier commit too.
        root, base = _repo(tmp_path)
        bad = _commit(root, {"products/igig/frontend/src/pages/A.tsx": "x\n"}, "feat: ui")
        _commit(root, {GUIDE: "# guia v2\n"}, "docs: guide")
        out = check_product_guide_cochange_range(f"{base}..HEAD", repo_root=root)
        assert [bad[:9] in i["issue"] for i in out] == [True]

    def test_accepted_historical_commit_is_skipped(self, tmp_path):
        root, base = _repo(tmp_path)
        bad = _commit(root, {"products/igig/backend/app/services/x.py": "y = 2\n"}, "feat")
        assert check_product_guide_cochange_range(
            f"{base}..HEAD", repo_root=root, accepted={bad: "predates the CI leg"}) == []

    def test_unresolvable_range_fails_closed(self, tmp_path):
        root, _ = _repo(tmp_path)
        out = check_product_guide_cochange_range("nope..HEAD", repo_root=root)
        assert len(out) == 1 and out[0]["severity"] == "high" and "fail-closed" in out[0]["issue"]

    def test_malformed_range_refused(self, tmp_path):
        root, _ = _repo(tmp_path)
        assert check_product_guide_cochange_range("HEAD", repo_root=root)[0]["severity"] == "high"


def _scan(tmp_path: Path, doc: str, tip="abc1234def", rows=None):
    f = tmp_path / "doc.md"
    f.write_text(doc)
    ex = mp.FakeSqlExecutor(preset_rows=rows or {
        "public.organizations": [{"id": ORG, "nome": "Giovanna Org"}, {"id": OTHER, "nome": "Betaland"}],
        "public.noctus_users": [{"email": "g@x.com", "org_id": ORG, "org_role": "owner"}],
    })
    return scan_live_state_claims(
        root=tmp_path, memory_dir=tmp_path / "nomem", executor=ex, files=[f],
        prod_sha_resolver=lambda: (tip, "fake"), is_ancestor=lambda c, t: True, include_ok=True)


class TestScanLiveStateClaims:
    def test_org_prefix_ok_and_stale_mismatch(self, tmp_path):
        r = _scan(tmp_path, "Giovanna has her org df6c3ace here\nthe org deadbe01 is gone\n")
        st = {c["claim"]: c["status"] for c in r["claims"]}
        assert st == {"df6c3ace": "ok", "deadbe01": "mismatch"}
        assert r["ok"] is False

    def test_org_name_cross_check(self, tmp_path):
        r = _scan(tmp_path, "Betaland org df6c3ace\n")
        assert r["claims"][0]["status"] == "unknown"

    def test_email_role(self, tmp_path):
        r = _scan(tmp_path, "g@x.com is admin\nz@y.com exists\nnoreply@example.com\n")
        st = {c["claim"]: c["status"] for c in r["claims"]}
        assert st == {"g@x.com": "mismatch", "z@y.com": "unknown"}

    def test_prod_sha(self, tmp_path):
        r = _scan(tmp_path, "prod is at abc1234\nprod is at 99aa11bb\nshipped prod 2026-10-01 99aa11bb\n")
        st = [c["status"] for c in sorted(r["claims"], key=lambda c: c["line"])]
        assert st == ["ok", "mismatch", "unverifiable"]

    def test_no_credentials_is_unverifiable_not_ok(self, tmp_path, monkeypatch):
        f = tmp_path / "d.md"
        f.write_text("org df6c3ace\n")
        monkeypatch.setattr(mp, "make_sql_executor", lambda **k: None)
        r = scan_live_state_claims(root=tmp_path, memory_dir=tmp_path, files=[f],
                                   prod_sha_resolver=lambda: (None, "x"))
        assert r["claims"][0]["status"] == "unverifiable" and r["errors"]
