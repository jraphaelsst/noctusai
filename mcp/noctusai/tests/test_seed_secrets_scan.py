"""CI-gating coverage for `noctusai_lib.security.secrets_scan` (A1c,
project-history/roadmaps/julia-agents-academia-2026-09.md, contract
§B.6).

``seed/lib/backend/tests/`` is NOT run by CI (open drift, 2026-09-09) —
this file is the CI-gating leg for the hoisted content-secret scan,
mirroring `test_seed_token_scopes.py`'s rationale for the same gap.

Cases ported from BOTH pre-hoist copies' test suites:
  - `products/academia-de-reciclagem/backend/tests/importer/test_secrets.py`
    (`scan_content`, boolean-only — the importer's own test file stays
    in place post-hoist, since `scan_content` is still a thin re-export
    there, but every case it covers is duplicated here too so this
    module has standalone CI-gating coverage independent of the product
    suite).
  - `mcp/noctusai/tools/noctus/dev/knowledge_bundle_export.py`'s own
    pre-hoist `_content_has_secret` had no dedicated unit tests of its
    own (only exercised indirectly through
    `tests/test_knowledge_bundle_export.py::TestSecretRefusal`, which
    stays green unchanged since the hoist is behaviour-preserving).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from noctusai_lib.security import find_secret, has_secret


class TestKnownPatterns:
    def test_stripe_secret_key(self):
        content = "here is a key sk-abcdefghijklmnop1234567890 inline"
        assert has_secret(content) is True
        assert find_secret(content) == "stripe_secret_key"

    def test_stripe_publishable_key(self):
        # The realistic `pk_live_...` shape embeds an underscore right
        # after the `pk_` prefix, which breaks the `pk_[A-Za-z0-9]{16,}`
        # pattern (immediately-following alnum run only) — so this
        # particular shape is actually caught by the entropy heuristic,
        # not the known-pattern check. Both are legitimate secret
        # detectors; either firing is correct (`has_secret` is what the
        # contract cares about).
        content = "pk_live_ABCDEFGHIJ1234567890abcdefgh"
        assert has_secret(content) is True
        assert find_secret(content) == "high_entropy_token"

    def test_github_pat(self):
        content = "token: ghp_1234567890abcdefghijklmnopqrstuvwx"
        assert has_secret(content) is True
        assert find_secret(content) == "github_pat"

    def test_aws_access_key_id(self):
        content = "AKIAABCDEFGHIJKLMNOP"
        assert has_secret(content) is True
        assert find_secret(content) == "aws_access_key_id"

    def test_pem_private_key_header(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n"
        assert has_secret(content) is True
        assert find_secret(content) == "pem_private_key"

    def test_short_prefix_alone_is_not_a_match(self):
        # "pk_" / "sk-" with too few trailing chars should not trip —
        # avoids flagging incidental short substrings.
        content = "sk-8 e pk_2 sao valores de exemplo"
        assert has_secret(content) is False
        assert find_secret(content) is None


class TestEntropyHeuristic:
    def test_random_looking_long_token_flagged(self):
        token = "x9J2kLmQ8pZ7vN4rT1sW6yU3bH0dF5gA7cE1nR6"
        content = f"segredo encontrado: {token}"
        assert has_secret(content) is True
        assert find_secret(content) == "high_entropy_token"

    def test_hex_looking_long_token_flagged(self):
        token = "3f9a1c2e7b8d4f6a0c5e2b9d7f1a4c8e6b3d0f9a2c7e5b1d8f4a6c0e3b7d9f2a"
        assert has_secret(token) is True
        assert find_secret(token) == "high_entropy_token"


class TestFalsePositives:
    """§B.6 explicitly requires this scan not to fire on ordinary PT-BR
    prose — including the long hyphenated compound phrases/slugs that
    are common in this knowledge base.
    """

    def test_plain_ptbr_sentence(self):
        content = (
            "A reciclagem de materiais organicos e inorganicos exige "
            "atencao especial ao descarte correto de residuos solidos "
            "urbanos conforme a legislacao vigente no Brasil."
        )
        assert has_secret(content) is False
        assert find_secret(content) is None

    def test_long_hyphenated_ptbr_slug(self):
        content = (
            "conforme-a-politica-nacional-de-residuos-solidos-e-a-lei-"
            "12305-de-2010-sobre-logistica-reversa-obrigatoria"
        )
        assert has_secret(content) is False

    def test_multiple_hyphenated_slugs_in_one_document(self):
        content = "\n".join(
            [
                "# Dominio regulatorio",
                "",
                "Ver dominio-regulatorio-pnrs e logistica-reversa-obrigatoria-",
                "para-fabricantes-e-importadores-conforme-normas-ambientais.",
                "",
                "Outro tema: a-reciclagem-de-materiais-organicos-e-inorganicos-",
                "no-brasil-contemporaneo-e-seus-desafios-logisticos.",
            ]
        )
        assert has_secret(content) is False

    def test_markdown_table_of_decisions_is_clean(self):
        content = (
            "| # | Decisão | Motivo |\n"
            "|---|---|---|\n"
            "| D-01 | Usar Supabase para persistencia | Reduz custo operacional |\n"
            "| D-02 | Adotar RLS por organizacao | Isola dados entre clientes |\n"
        )
        assert has_secret(content) is False


class TestCodePathFalsePositives:
    """`/`-separated lowercase code paths are the same false-positive
    class as the hyphenated PT-BR slugs above, just for `/` instead of
    `-`: a 28+ char, all-lowercase path measures ~3.8-4.0 bits/char once
    slashes are folded into the entropy calc — clearing
    ``_ENTROPY_THRESHOLD`` (3.5) even though it is plainly source code,
    not a secret. Blocked the academia knowledge-bundle export on
    ``docs/SPEC.md`` (which references
    ``backend/app/services/agent_runner.py``) — see
    ``_looks_like_code_path`` in ``secrets_scan.py`` for the fix.
    """

    def test_exact_reported_false_positive_path(self):
        # The precise 33-char string from the bug report: lowercase,
        # 3.84 bits/char, no known-pattern prefix.
        content = "see backend/app/services/agent_runner for the wrapper"
        assert has_secret(content) is False
        assert find_secret(content) is None

    def test_reported_path_with_file_extension(self):
        content = "backend/app/services/agent_runner.py wraps the SDK client"
        assert has_secret(content) is False

    def test_realistic_longer_source_path(self):
        content = "mcp/noctusai/tools/noctus/dev/knowledge_bundle_export.py"
        assert has_secret(content) is False

    def test_realistic_longer_doc_path_with_extension(self):
        content = "see docs/architecture/decisions/adr_0001_agent_design.md"
        assert has_secret(content) is False

    def test_lowercase_only_token_with_no_slash_is_still_flagged(self):
        # Documented, deliberate: a bare (no `/`) long lowercase random
        # token never reaches `_looks_like_code_path` at all (it only
        # runs when `"/" in token`) — its entropy-only behaviour from
        # before this fix is UNCHANGED. This particular 39-char token
        # has no real-word structure and clears the entropy threshold,
        # so it stays flagged exactly as it always was.
        token = "x9j2klmq8pz7vn4rt1sw6yu3bh0df5ga7ce1nr6"
        assert has_secret(token) is True
        assert find_secret(token) == "high_entropy_token"

    def test_random_blob_split_into_short_path_shaped_segments_still_flagged(self):
        # Deliberate call (documented in `_looks_like_code_path`): a
        # random blob adversarially chopped into short "path-shaped"
        # segments mixes a digit into nearly every segment (unlike a
        # real path, which is mostly whole words). We choose to keep
        # flagging this shape rather than let a digit-salted blob dodge
        # detection just by inserting `/` — a detector that misses a
        # real secret is worse than one that's slightly conservative.
        token = "k3j9x/q8w2z/m5t7r/b1n4v/x8k2p/w9q3z/j6m1t"
        assert has_secret(token) is True
        assert find_secret(token) == "high_entropy_token"

    def test_real_base64_secret_containing_slash_is_still_flagged(self):
        # Mixed-case + digits + `/` + `=` padding — real base64 shape.
        # Fails `_CODE_PATH_SEGMENT_RE` immediately (uppercase present),
        # so it never takes the code-path exemption and is scored on
        # entropy exactly as before this fix.
        token = "aGVsbG8gd29ybGQ/QUJDZGVmMTIzNDU2Nzg5MEFCQ0RFRg=="
        assert has_secret(token) is True
        assert find_secret(token) == "high_entropy_token"


class TestFindSecretNeverLeaksTheValue:
    """The whole point of returning a NAME instead of a match object —
    a caller can always safely log/return the result."""

    def test_return_value_is_a_short_fixed_name_not_the_matched_text(self):
        token = "AKIAABCDEFGHIJKLMNOPQRSTUV"
        result = find_secret(f"aws key: {token}")
        assert result == "aws_access_key_id"
        assert token not in result


class TestCodePathExemptionDoesNotHideSecrets:
    """Security review of the `/` exemption (2026-09-17): lowercase hex
    secrets after a `/` must still be caught."""

    def test_hex_webhook_secret_in_url_is_flagged(self):
        url = "https://hooks.example.com/webhook/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b"
        assert find_secret(f"POST to {url}") is not None

    def test_hex_api_key_after_a_slash_is_flagged(self):
        assert find_secret("keys/a1b2c3d4e5f60718293a4b5c6d7e8f90") is not None

    def test_hex_bot_token_in_url_is_flagged(self):
        url = "https://api.telegram.org/bot/f3a9c1d2e4b5a6978877665544332211aa"
        assert find_secret(url) is not None

    def test_the_original_code_path_is_still_not_flagged(self):
        assert find_secret("see backend/app/services/agent_runner.py") is None

    def test_real_stripe_secret_prefixes_are_named(self):
        for prefix in ("sk_live_", "rk_live_", "sk_test_"):
            content = f"STRIPE={prefix}" + "a" * 24
            assert find_secret(content) == "stripe_live_or_restricted_key", prefix
