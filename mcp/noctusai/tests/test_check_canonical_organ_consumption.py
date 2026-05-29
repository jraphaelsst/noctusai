"""Regression tests for check_canonical_organ_consumption.

Six test cases per the Phase 2.1 brief:
  1. canonical_consumer_passes      — import from @noctusai/lib → no issue
  2. silent_fork_fails              — local `function LoginForm` without declaration → blocked
  3. declared_named_seam_passes     — @consumes-organ header + local wrapper → allowed
  4. undeclared_wrapper_blocks      — local const without declaration → blocked
  5. shelfware_organ_not_scoped     — PageSkeleton (shelfware, not in registry) → allowed
  6. same_shape_rename_not_detected — `AuthForm` structurally == `LoginForm` → known limitation,
                                      NOT caught by name-only; scoped-improvement documented

KB § PATTERNS/architect/products-consume-canonical-organs.md
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_canonical_organ_consumption


def _make_repo(tmp: Path) -> Path:
    """Scaffold a minimal fake-repo layout under `tmp`."""
    (tmp / "products").mkdir(parents=True, exist_ok=True)
    (tmp / "seed" / "lib" / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    return tmp


def _product_file(repo: Path, slug: str, rel: str, content: str) -> Path:
    """Write a TS/TSX file under products/<slug>/frontend/src/."""
    target = repo / "products" / slug / "frontend" / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


class TestCanonicalConsumerPasses:
    """A product that imports LoginForm from @noctusai/lib must not be flagged."""

    def test_import_from_lib_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _product_file(
                repo,
                "erp",
                "pages/Login.tsx",
                'import { LoginForm } from "@noctusai/lib/components/auth/LoginForm";\n'
                "\n"
                "export function LoginPage() {\n"
                "  return <LoginForm onSuccess={() => {}} />;\n"
                "}\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        organ_issues = [i for i in issues if "LoginForm" in i["issue"]]
        assert not organ_issues, f"Expected clean scan; got {organ_issues}"


class TestSilentForkFails:
    """A local `function LoginForm` without a declaration header is blocked."""

    def test_local_function_declaration_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _product_file(
                repo,
                "erp",
                "components/LoginForm.tsx",
                "import React from 'react';\n"
                "\n"
                "export function LoginForm({ onSuccess }: { onSuccess: () => void }) {\n"
                "  return <form>...</form>;\n"
                "}\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        organ_issues = [
            i for i in issues if "LoginForm" in i["issue"] and i["severity"] == "high"
        ]
        assert organ_issues, "Expected blocking issue for silent LoginForm fork"
        assert "import from `@noctusai/lib`" in organ_issues[0]["issue"]


class TestDeclaredNamedSeamPasses:
    """A wrapper with // @consumes-organ header is an approved named-seam extension."""

    def test_declared_seam_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _product_file(
                repo,
                "erp",
                "components/DigestCard.tsx",
                "// @consumes-organ DigestCard@1.0 +seam=data-binding\n"
                "// Extends canonical DigestCard with ERP-specific data source.\n"
                'import { DigestCard as _DigestCard } from "@noctusai/lib/components/digest/DigestCard";\n'
                "\n"
                "export const DigestCard = (props: any) => <_DigestCard {...props} source='erp' />;\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        organ_issues = [i for i in issues if "DigestCard" in i["issue"]]
        assert not organ_issues, (
            f"Declared named-seam should be exempt; got {organ_issues}"
        )


class TestUndeclaredWrapperBlocks:
    """A `const LoginForm =` without the declaration header is still blocked."""

    def test_const_declaration_without_header_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _product_file(
                repo,
                "social-wiring",
                "components/LoginForm.tsx",
                'import { LoginForm as Base } from "@noctusai/lib/components/auth/LoginForm";\n'
                "\n"
                "// Wrapping base but NOT declaring the seam.\n"
                "const LoginForm = (p: any) => <Base {...p} />;\n"
                "export default LoginForm;\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        organ_issues = [
            i for i in issues if "LoginForm" in i["issue"] and i["severity"] == "high"
        ]
        assert organ_issues, (
            "Undeclared wrapper should be blocked; missing high-severity issue"
        )


class TestShelfwareOrganNotScoped:
    """An organ not in the canonical registry (shelfware) may be re-implemented locally."""

    def test_page_skeleton_local_impl_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _product_file(
                repo,
                "erp",
                "components/PageSkeleton.tsx",
                "export function PageSkeleton() {\n"
                "  return <div className='skeleton' />;\n"
                "}\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        organ_issues = [i for i in issues if "PageSkeleton" in i.get("issue", "")]
        assert not organ_issues, (
            "PageSkeleton is shelfware; local impl should not be flagged"
        )


class TestSameShapeRenameNotDetected:
    """Known limitation: a same-shape rename (`AuthForm` ≡ `LoginForm`) evades
    name-only detection. Test documents this gap and emits a scoped-improvement
    note per the methodology.

    scoped-improvement: name-only matching misses structural siblings; a future
    s4 pass can use `noctus.dev.find_reusable_component` vector similarity to
    surface rename candidates (intent-match rather than identifier-match).
    """

    def test_auth_form_rename_not_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            _product_file(
                repo,
                "erp",
                "components/AuthForm.tsx",
                "// Same structure as LoginForm but different name — evades keeper.\n"
                "export function AuthForm({ onSuccess }: { onSuccess: () => void }) {\n"
                "  return <form>...</form>;\n"
                "}\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        # The keeper should NOT flag AuthForm — it's a different identifier.
        organ_issues = [i for i in issues if "AuthForm" in i.get("issue", "")]
        assert not organ_issues, (
            "AuthForm is a different name; keeper must not flag it "
            "(name-only matching limitation — see class docstring)"
        )
        # scoped-improvement: intent-based detection would catch this.


class TestOrganyamlSidecarExtension:
    """A canonical organ registered only via organ.yaml sidecar is also enforced."""

    def test_organ_yaml_canonical_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = _make_repo(Path(tmp_str))
            # Write a sidecar for a new organ not in the hard-coded set.
            sidecar_dir = repo / "seed" / "lib" / "frontend" / "src" / "components" / "metrics"
            sidecar_dir.mkdir(parents=True, exist_ok=True)
            (sidecar_dir / "MetricCard.organ.yaml").write_text(
                "name: MetricCard\nvalidation_status: validated\n", encoding="utf-8"
            )
            # Product re-declares it without the seam header.
            _product_file(
                repo,
                "erp",
                "components/MetricCard.tsx",
                "export const MetricCard = () => <div />;\n",
            )
            issues = check_canonical_organ_consumption(repo_root=repo)
        organ_issues = [
            i for i in issues if "MetricCard" in i.get("issue", "")
        ]
        assert organ_issues, (
            "organ.yaml-registered canonical organ should be enforced like the hard-coded set"
        )
