"""Colocated regression test for `check_prod_compose_env_manifest_sync`
(meta-detector: every keeper ships Test<CamelCase>).

THE INCIDENT (2026-09-16, agents/academia-de-reciclagem cutover):
`docker-compose.prod.yml` maps `ANTHROPIC_API_KEY: ${JULIA_ANTHROPIC_API_KEY:-}`
for `agents`. `${VAR}` interpolation is resolved from `deploy/fleet/.env.fleet`
(compose-parse time) — a DIFFERENT mechanism from `env_file:` (which reads the
root `.env` inside the already-started container). `JULIA_ANTHROPIC_API_KEY`
was only ever documented as a root-`.env` key, so it silently interpolated to
`''` — every Julia turn failed at the CLI-spawn step while the container
stayed healthy. This keeper is the mechanism: (1) every ${VAR} either prod
compose file interpolates must be listed (names only) in
`deploy/fleet/env.fleet.keys`; (2) a secret-shaped var name with no enforced
non-empty default is flagged unconditionally, escape-hatchable via an
`env-fleet-empty-ok` comment for a REVIEWED, intentional degrade.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_prod_compose_env_manifest_sync,
    _parse_compose_interpolated_vars,
    _parse_env_fleet_manifest_keys,
    _strip_yaml_comment,
)


def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


_MANIFEST_ALL = (
    "# names only\n"
    "NOCTUS_IMAGE_TAG\n"
    "ANTHROPIC_API_KEY\n"
    "JULIA_ANTHROPIC_API_KEY\n"
    "NOCTUS_CACHE_PG_PASSWORD\n"
)

_COMPOSE_TEXT = (
    "services:\n"
    "  core:\n"
    "    image: ghcr.io/x/noctus-core:${NOCTUS_IMAGE_TAG:-latest}\n"
    "  dev-team:\n"
    "    environment:\n"
    "      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}  # env-fleet-empty-ok — reviewed\n"
    "    expose:\n"
    "      - \"8009\"\n"
    "    healthcheck:\n"
    "      test: [\"CMD\", \"curl\", \"http://localhost:8009/api/health\"]\n"
    "  agents:\n"
    "    environment:\n"
    "      ANTHROPIC_API_KEY: ${JULIA_ANTHROPIC_API_KEY:-}\n"
    "  x-cache-env:\n"
    "    DSN: postgresql://u:${NOCTUS_CACHE_PG_PASSWORD}@host/db\n"
)

# A genuinely CLEAN compose — every secret-shaped var is either non-empty-
# defaulted, bare (out of scope), or explicitly escape-hatched. Distinct
# from `_COMPOSE_TEXT`, which deliberately reproduces the 2026-09-16
# incident shape (JULIA_ANTHROPIC_API_KEY unescaped) for the drift tests.
_COMPOSE_TEXT_CLEAN = (
    "services:\n"
    "  core:\n"
    "    image: ghcr.io/x/noctus-core:${NOCTUS_IMAGE_TAG:-latest}\n"
    "  dev-team:\n"
    "    environment:\n"
    "      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}  # env-fleet-empty-ok — reviewed\n"
    "  agents:\n"
    "    environment:\n"
    "      ANTHROPIC_API_KEY: ${JULIA_ANTHROPIC_API_KEY:-}  # env-fleet-empty-ok — reviewed, verified in .env.fleet\n"
    "  x-cache-env:\n"
    "    DSN: postgresql://u:${NOCTUS_CACHE_PG_PASSWORD}@host/db\n"
)


class TestParsers:
    def test_parse_manifest_keys_skips_blank_and_comment_lines(self):
        text = "# comment\n\nFOO\n  BAR  \n# another\nBAZ\n"
        assert _parse_env_fleet_manifest_keys(text) == {"FOO", "BAR", "BAZ"}

    def test_parse_interpolated_vars_distinguishes_bare_and_empty_default(self):
        text = (
            "a: ${BARE_VAR}\n"
            "b: ${EMPTY_DEFAULT:-}\n"
            "c: ${WITH_DEFAULT:-latest}\n"
        )
        parsed = _parse_compose_interpolated_vars(text)
        assert parsed["BARE_VAR"] == [(1, None)]
        assert parsed["EMPTY_DEFAULT"] == [(2, "")]
        assert parsed["WITH_DEFAULT"] == [(3, "latest")]

    def test_strip_yaml_comment_truncates_at_unquoted_hash(self):
        assert _strip_yaml_comment("a: 1  # trailing comment") == "a: 1  "
        assert _strip_yaml_comment("no comment here") == "no comment here"
        assert _strip_yaml_comment("  # full-line comment") == "  "

    def test_strip_yaml_comment_respects_quotes(self):
        # A '#' inside quotes is data, not a comment marker.
        assert _strip_yaml_comment("a: 'value#not-a-comment'  # real") == "a: 'value#not-a-comment'  "

    def test_prose_comment_mentioning_var_syntax_is_not_an_interpolation_site(self):
        # A comment EXPLAINING the incident inline (as this repo's own compose
        # comments now do) must not itself register as a real interpolation
        # site — exactly what broke the first draft of this keeper.
        text = (
            "  # the explicit `ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}` line\n"
            "      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}  # env-fleet-empty-ok\n"
        )
        parsed = _parse_compose_interpolated_vars(text)
        assert parsed["ANTHROPIC_API_KEY"] == [(2, "")]


class TestProdComposeEnvManifestSync:
    def test_no_prod_compose_file_is_clean(self, tmp_path):
        # Not a noc tree yet / fleet not configured — silent skip, not an error.
        assert check_prod_compose_env_manifest_sync(repo_root=tmp_path) == []

    def test_missing_manifest_file_flags_high(self, tmp_path):
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", _COMPOSE_TEXT)
        issues = check_prod_compose_env_manifest_sync(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "prod-compose-env-manifest-missing-file"
        assert issues[0]["severity"] == "high"

    def test_complete_manifest_and_escape_hatch_is_clean(self, tmp_path):
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", _COMPOSE_TEXT_CLEAN)
        _write(tmp_path, "deploy/fleet/env.fleet.keys", _MANIFEST_ALL)
        assert check_prod_compose_env_manifest_sync(repo_root=tmp_path) == []

    def test_var_missing_from_manifest_is_flagged(self, tmp_path):
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", _COMPOSE_TEXT)
        # Manifest omits NOCTUS_IMAGE_TAG.
        incomplete = _MANIFEST_ALL.replace("NOCTUS_IMAGE_TAG\n", "")
        _write(tmp_path, "deploy/fleet/env.fleet.keys", incomplete)
        issues = check_prod_compose_env_manifest_sync(repo_root=tmp_path)
        symbols = {i["symbol"] for i in issues}
        assert "prod-compose-env-manifest-missing" in symbols
        missing_issue = next(
            i for i in issues if i["symbol"] == "prod-compose-env-manifest-missing"
        )
        assert "NOCTUS_IMAGE_TAG" in missing_issue["issue"]
        assert missing_issue["severity"] == "high"

    def test_secret_shaped_var_with_no_escape_hatch_is_flagged(self, tmp_path):
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", _COMPOSE_TEXT)
        _write(tmp_path, "deploy/fleet/env.fleet.keys", _MANIFEST_ALL)
        issues = check_prod_compose_env_manifest_sync(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "prod-compose-secret-empty-default"
        # JULIA_ANTHROPIC_API_KEY has no escape hatch, must be flagged.
        assert "JULIA_ANTHROPIC_API_KEY" in issues[0]["issue"]
        # ANTHROPIC_API_KEY (dev-team) carries env-fleet-empty-ok — excluded.
        assert "'ANTHROPIC_API_KEY'" not in issues[0]["issue"]
        assert issues[0]["severity"] == "high"

    def test_bare_var_with_no_default_at_all_is_not_flagged_as_secret(self, tmp_path):
        # NOCTUS_CACHE_PG_PASSWORD has NO ':-' clause at all (bare ${VAR}) —
        # deliberately OUT of scope: a secret with no sensible default has
        # no "safe" shape to require, so flagging it would be permanent
        # noise on an already-required, already-correct var.
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", _COMPOSE_TEXT)
        _write(tmp_path, "deploy/fleet/env.fleet.keys", _MANIFEST_ALL)
        issues = check_prod_compose_env_manifest_sync(repo_root=tmp_path)
        secret_issue = next(i for i in issues if i["symbol"] == "prod-compose-secret-empty-default")
        assert "NOCTUS_CACHE_PG_PASSWORD" not in secret_issue["issue"]

    def test_non_secret_var_with_empty_default_is_not_flagged_as_secret(self, tmp_path):
        text = "services:\n  x:\n    TAG: ${NOCTUS_IMAGE_TAG:-}\n"
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", text)
        _write(tmp_path, "deploy/fleet/env.fleet.keys", "NOCTUS_IMAGE_TAG\n")
        assert check_prod_compose_env_manifest_sync(repo_root=tmp_path) == []

    def test_escape_hatch_must_be_within_window(self, tmp_path):
        # env-fleet-empty-ok present, but 5 lines above — outside the
        # 3-preceding-line window, so it must NOT suppress the finding.
        text = (
            "services:\n"
            "  agents:\n"
            "    # env-fleet-empty-ok (stale, far away)\n"
            "    a: 1\n"
            "    b: 2\n"
            "    c: 3\n"
            "    environment:\n"
            "      ANTHROPIC_API_KEY: ${JULIA_ANTHROPIC_API_KEY:-}\n"
        )
        _write(tmp_path, "deploy/fleet/docker-compose.prod.yml", text)
        _write(tmp_path, "deploy/fleet/env.fleet.keys", "JULIA_ANTHROPIC_API_KEY\n")
        issues = check_prod_compose_env_manifest_sync(repo_root=tmp_path)
        assert any(i["symbol"] == "prod-compose-secret-empty-default" for i in issues)
