"""Tests for noctus.dev.scan_remediation_markers (KB § PATTERNS/common/remediation-markers.md).

Real git repos + real `git grep` (no monkey-patch of our own code) so the
parse/classify/group predicates exercise the actual plumbing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.scan_remediation_markers import scan_remediation_markers


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True,
                   capture_output=True, text=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    r = tmp_path / "noc"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    for rel, content in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "seed")
    return r


class TestScan:
    def test_wellformed_grouped_and_clean_exit(self, tmp_path):
        r = _repo(tmp_path, {
            "a.py": "# NOC-REMEDIATE[perf]: tighten the loop — 2026-05-01\nx = 1\n",
            "b.py": "# NOC-REMEDIATE[perf]: cache the call — 2026-05-02\n",
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 2
        assert res["by_class"] == {"perf": 2}
        assert res["promote_candidates"] == []        # perf at N=2 (< 3)
        assert res["malformed"] == []
        assert res["on_except"] == []
        assert res["exit_code"] == 0
        assert res["status"] == "markers"

    def test_recurrence_promote_candidate_at_n3(self, tmp_path):
        lines = "".join(
            f"# NOC-REMEDIATE[dry]: extract helper {i} — 2026-05-1{i}\n" for i in range(3)
        )
        r = _repo(tmp_path, {"c.py": lines})
        res = scan_remediation_markers(repo_root=r)
        assert res["by_class"]["dry"] == 3
        assert "dry" in res["promote_candidates"]      # N≥3 ⇒ promote

    def test_malformed_missing_date_flagged(self, tmp_path):
        r = _repo(tmp_path, {
            "d.py": "# NOC-REMEDIATE[bug]: no date here\n",  # real class, missing date
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1
        assert len(res["malformed"]) == 1
        assert res["exit_code"] == 1                   # defect ⇒ nonzero

    def test_prose_mentions_not_flagged(self, tmp_path):
        """The scanner must NOT trip on docs/code that merely MENTION the token
        (placeholder `[<class>]` or no bracket) — the false-positive fix."""
        r = _repo(tmp_path, {
            "doc.md": "The `NOC-REMEDIATE[<class>]: <what> — <YYYY-MM-DD>` token is "
                      "the sanctioned channel; NOC-REMEDIATE markers are swept.\n",
            "help.py": 'HELP = "batch-sweep the NOC-REMEDIATE deferral markers"\n',
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, f"prose mentions must not count: {res}"
        assert res["exit_code"] == 0
        assert res["status"] == "clean"

    def test_on_except_is_forbidden(self, tmp_path):
        r = _repo(tmp_path, {
            "e.py": "try:\n    pass\n"
                    "except Exception:  # NOC-REMEDIATE[err]: handle it — 2026-05-13\n"
                    "    pass\n",
        })
        res = scan_remediation_markers(repo_root=r)
        assert len(res["on_except"]) == 1
        assert res["on_except"][0]["class"] == "err"
        assert res["exit_code"] == 1                   # marker-on-except is a defect

    def test_no_markers_is_clean(self, tmp_path):
        r = _repo(tmp_path, {"f.py": "x = 1\n"})
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0
        assert res["status"] == "clean"
        assert res["exit_code"] == 0


class TestFrozenHistoryIsNotDebt:
    """Archived `git format-patch` output is a RECORD, not live code.

    2026-08-11, caught in CI on `main`: salvaging `feat/harness-audit-refit`
    before deleting it wrote the branch's patch under
    `project-history/orphan-remote-archive-.../*.patch`. That patch embeds
    source lines verbatim — including a `NOC-REMEDIATE[codify]` marker with no
    date — so `check_codification_debt` reported a NEW high-severity malformed
    marker and reddened the compliance baseline.

    The marker is unfixable by construction: editing an archived patch would
    falsify the history it exists to preserve. So the scanner must not look.
    """

    MALFORMED = "# NOC-REMEDIATE[codify]: no date here so this is malformed\n"

    def test_marker_inside_an_archived_patch_is_ignored(self, tmp_path):
        r = _repo(tmp_path, {
            "project-history/orphan-remote-archive-2026-08-11/feat_x/0001-thing.patch":
                "From abc123 Mon Sep 17 00:00:00 2001\n"
                "Subject: [PATCH] a thing\n"
                "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1,2 @@\n+" + self.MALFORMED,
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, res

    def test_the_same_marker_in_LIVE_code_still_fires(self, tmp_path):
        """The exclusion must be surgical — prove it did not mute the detector."""
        r = _repo(tmp_path, {"mod.py": self.MALFORMED})
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1
        assert res["exit_code"] == 1, "a malformed marker in live code is still a defect"

    def test_a_non_patch_file_under_project_history_still_counts(self, tmp_path):
        """Only `.patch` files are frozen. A roadmap/notes markdown under
        project-history/ is editable prose and stays in scope."""
        r = _repo(tmp_path, {
            "project-history/roadmaps/thing.md":
                "# NOC-REMEDIATE[codify]: real deferral — 2026-08-01\n",
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1

    def test_a_patch_OUTSIDE_project_history_still_counts(self, tmp_path):
        """Scoped to the archive dir, not to the extension — a stray patch in
        the working tree is not sanctioned history."""
        r = _repo(tmp_path, {"scratch/wip.patch": self.MALFORMED})
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1


class TestDeclarationVsCitation:
    """2026-08-31 rewrite: a fresh sweep of the real repo found 142 markers,
    ~120 "malformed" — nearly all of them prose *citing* a marker that lives
    elsewhere, not a genuine deferral. These fixtures pin the declaration/
    citation discriminator per marker declared in the module docstring.
    Each is proven to fail against the pre-rewrite scanner (single-line-only,
    `[class]` + optional date-anywhere-on-the-line) before this fix landed —
    see the dispatch note; `d0170d92` is the standing lesson that a fixture
    unable to express the failure passes forever.
    """

    def test_real_multiline_marker_date_on_continuation_line(self, tmp_path):
        """The `— <date>` frequently lands 2-3 lines below the `[class]:`
        open — a genuine, common shape (`imovel_normalizer.py`,
        `config.py`'s `house-port` marker). The OLD scanner only ever looked
        at the single git-grep-captured line, so this was reported
        malformed (missing date) even though the marker IS dated."""
        r = _repo(tmp_path, {
            "svc.py": (
                "def f():\n"
                "    # NOC-REMEDIATE[dry]: extract this helper once the 3rd\n"
                "    # consumer lands; keep it local until then, tracked\n"
                "    # here rather than a premature seed lift — 2026-05-25\n"
                "    return 1\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1
        assert res["malformed"] == [], f"date on line 3 of the block missed: {res}"
        assert res["exit_code"] == 0

    def test_prose_citation_with_real_class_not_counted_at_all(self, tmp_path):
        """A KB/roadmap sentence CITING a marker declared elsewhere (`` `NOC-
        REMEDIATE[x]` `` — a backtick-quoted noun-phrase reference, no colon,
        no fresh deferral text) must not be counted as a marker at all — not
        even as malformed. This is the `auth-boundary-false-green.md` /
        `roteiros-visitas-PROJECT.md` shape verified in the live repo."""
        r = _repo(tmp_path, {
            "doc.md": (
                "Actual test execution is scoped as\n"
                "`NOC-REMEDIATE[canonical-runner-exec]` — see that module for rationale.\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, f"a citation must not be counted at all: {res}"
        assert res["status"] == "clean"

    def test_python_docstring_citation_pointing_elsewhere_not_counted(self, tmp_path):
        """A docstring CAN also merely cite a marker ("See the ... marker at
        the handling site") — being inside a docstring is necessary but not
        sufficient; the declaration-shape check still applies. This is the
        `whatsapp_router.py:28` shape."""
        r = _repo(tmp_path, {
            "svc.py": (
                '"""Module doc.\n\n'
                "Acknowledged but not persisted. See the ``NOC-REMEDIATE[x]``\n"
                "marker at the handling site.\n"
                '"""\n'
                "x = 1\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, f"a docstring citation must not be counted: {res}"

    def test_python_string_literal_citation_not_counted(self, tmp_path):
        """`assert "NOC-REMEDIATE[x]" in some_string` tests that ANOTHER
        function emits the marker text — it is not itself a declaration.
        AST/tokenize context (comment vs. docstring vs. ordinary string
        literal) is the discriminator; a colon-shaped ordinary string still
        must not count. This is the `test_canonical_test_audit.py` /
        `test_component_bundle.py` shape."""
        r = _repo(tmp_path, {
            "test_thing.py": (
                "def test_x():\n"
                '    assert _marker("// NOC-REMEDIATE[x]: something") is True\n'
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, f"a marker inside a plain string literal is a citation: {res}"

    def test_ellipsis_class_placeholder_not_counted(self, tmp_path):
        """`NOC-REMEDIATE[...]` (the ellipsis-as-"some class" notation, seen
        in `validation_signal.py`'s own docstring) is a placeholder, exactly
        like the pre-existing `[<class>]` angle-bracket rule — not a real
        class."""
        r = _repo(tmp_path, {
            "svc.py": (
                "def f():\n"
                '    """has_x: True when a ``NOC-REMEDIATE[...]`` marker appears."""\n'
                "    return 1\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, f"ellipsis class is a placeholder, not real: {res}"

    def test_undated_real_marker_still_reported_defective(self, tmp_path):
        """A genuine comment-based declaration with NO date anywhere in its
        block must still be counted and flagged malformed — the point of the
        exercise is to STOP under-reporting genuine debt, not to suppress
        it. This is the `canonical_test_audit.py:33` /
        `meta_ads_service.py` shape (verified real, undated, in the live
        repo)."""
        r = _repo(tmp_path, {
            "svc.py": (
                "def f():\n"
                "    # NOC-REMEDIATE[orbity-x]: wire the real client once\n"
                "    # credentials are available.\n"
                "    return 1\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1
        assert len(res["malformed"]) == 1
        assert res["malformed"][0]["class"] == "orbity-x"
        assert res["exit_code"] == 1

    def test_adjacent_reversed_bullet_declarations_stay_separate(self, tmp_path):
        """Three sibling bullet-form declarations (`label — NOC-REMEDIATE
        [class]`), one per line, must be parsed as THREE independent
        markers — not concatenated into one garbled record (the bug this
        rewrite introduced-then-fixed: the block-extension step originally
        pulled each bullet's SIBLING line in as "continuation text").
        Mirrors `meta_ads_service.py`'s three-bullet docstring."""
        r = _repo(tmp_path, {
            "svc.py": (
                '"""\n'
                "Seams:\n"
                "  - OAuth flow    — NOC-REMEDIATE[x]\n"
                "  - Sync pull     — NOC-REMEDIATE[x]\n"
                "  - CAPI feedback — NOC-REMEDIATE[x]\n"
                '"""\n'
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 3, f"each bullet is its own marker: {res}"
        for m in res["malformed"]:
            assert "NOC-REMEDIATE" not in m["text"], (
                f"a sibling bullet's own marker leaked into this record's text: {m}"
            )
            assert m["text"].startswith("-"), m

    def test_leading_date_before_marker_is_never_misread_as_the_markers_date(self, tmp_path):
        """A bullet whose line OPENS with an unrelated timestamp
        (`2026-05-29 (W5): ... NOC-REMEDIATE[x]`, a changelog-entry-date
        prefix) must not have that leading date misattributed to the marker
        — the date search is scoped to text strictly AFTER the marker's own
        `]`. This citation (no colon, not bare, not a reversed-bullet
        ending) is also not a declaration at all."""
        r = _repo(tmp_path, {
            "doc.md": (
                "- 2026-05-29 (W5): shipped the loop. Tracked as "
                "`NOC-REMEDIATE[x]`.\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, (
            f"a leading changelog date must not manufacture a fake well-formed marker: {res}"
        )

    def test_forbidden_on_except_still_fires_multiline(self, tmp_path):
        """The FORBIDDEN on-`except` shape must still fire even when the
        marker's own explanatory text wraps onto a second line — the
        multi-line read must not accidentally launder a suppression marker
        into a plain (non-except) malformed one."""
        r = _repo(tmp_path, {
            "svc.py": (
                "try:\n"
                "    pass\n"
                "except Exception:  # NOC-REMEDIATE[err]: handle it properly\n"
                "    # once the retry policy lands — 2026-05-13\n"
                "    pass\n"
            ),
        })
        res = scan_remediation_markers(repo_root=r)
        assert len(res["on_except"]) == 1
        assert res["on_except"][0]["class"] == "err"
        assert res["exit_code"] == 1
