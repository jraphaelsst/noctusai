"""`noctus.brand-tokens/v1` (CONTRACT org-brand-identity §2): key derivation from
tokens.css, the CSS-injection regexes, fill-from-platform, deterministic dark
derivation, WCAG contrast, and the migration's platform literal."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

from app.services.brand import tokens as T

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tokens_css() -> str:
    path = T.find_tokens_css(BACKEND)
    assert path is not None, f"{T.TOKENS_CSS_REL} must exist in a checkout"
    return path.read_text(encoding="utf-8")


class TestKeyDerivation:
    def test_artifact_is_exactly_the_derivation_of_tokens_css(self, tokens_css):
        expected = T.render_artifact(tokens_css)
        assert T.ARTIFACT_PATH.read_text(encoding="utf-8") == expected, (
            "platform_tokens.json drifted from tokens.css — regenerate: "
            "python -c 'from app.services.brand.tokens import write_artifact; write_artifact()'"
        )

    def test_keys_are_every_hsl_custom_property_of_root(self, tokens_css):
        root = re.search(r":root\s*\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", tokens_css, flags=re.S)).group(1)
        hsl_vars = [k for k, v in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", root) if T.HSL_RE.match(v.strip())]
        assert list(T.token_keys()) == hsl_vars
        assert "radius" not in T.token_keys() and not any(k.startswith("gradient") for k in T.token_keys())
        assert {"background", "sidebar-ring", "chart-8", "danger-light"} <= set(T.token_keys())

    def test_root_and_dark_key_mismatch_is_refused(self):
        css = ":root { --a: 0 0% 1%; --b: 0 0% 2%; --radius: 1rem; } .dark { --a: 0 0% 3%; }"
        with pytest.raises(ValueError, match="different token keys"):
            T.parse_tokens_css(css)

    def test_migration_platform_row_equals_the_artifact(self):
        sql = migration_sql(BACKEND / "migrations", "org_brand_identities")
        literal = re.search(r"'(\{\"schema\": \"noctus\.brand-tokens/v1\".*?\})'::jsonb", sql, re.S).group(1)
        assert json.loads(literal) == T.platform_tokens()


class TestValidation:
    @pytest.mark.parametrize("value", [
        "red", "#fff", "hsl(0 0% 0%)", "0 0% 0%; background: url(x)", "0 0% 0%}", "361 0% 0%",
        "0 101% 0%", "0 0% 100%;", "0 0 0", " 0 0% 0%", "0 0% 0% ", 12, None,
    ])
    def test_injection_and_out_of_range_values_are_refused(self, value):
        with pytest.raises(T.BrandTokensError):
            T.validate_tokens({"light": {"primary": value}})

    @pytest.mark.parametrize("radius", ["1rem", "8px", "0.25rem"])
    def test_radius_accepted(self, radius):
        assert T.validate_tokens({"radius": radius}).tokens["radius"] == radius

    @pytest.mark.parametrize("radius", ["1em", "calc(1px)", "999rem", "8px;", "1 rem"])
    def test_radius_refused(self, radius):
        with pytest.raises(T.BrandTokensError):
            T.validate_tokens({"radius": radius})

    @pytest.mark.parametrize("family", ["Inter';}body{", "Lora<script>", "a" * 65, "Font/../x", ""])
    def test_font_family_charset_enforced(self, family):
        with pytest.raises(T.BrandTokensError):
            T.validate_tokens({"fonts": {"body": {"family": family, "weights": [400], "source": "google"}}})

    def test_unknown_token_role_and_field_are_refused(self):
        with pytest.raises(T.BrandTokensError) as exc:
            T.validate_tokens({"light": {"evil": "0 0% 0%"}, "css": "x", "fonts": {"logo": {"family": "A"}}})
        assert len(exc.value.errors) == 3

    def test_missing_keys_filled_from_platform_and_listed(self):
        res = T.validate_tokens({"light": {"primary": "10 50% 40%"}, "dark": {"primary": "10 50% 60%"}})
        assert res.tokens["light"]["primary"] == "10 50% 40%"
        assert res.tokens["light"]["background"] == T.platform_tokens()["light"]["background"]
        assert "light.background" in res.filled_from_default and "light.primary" not in res.filled_from_default
        assert "dark.background" in res.filled_from_default and "radius" in res.filled_from_default
        assert set(res.tokens["light"]) == set(T.token_keys()) == set(res.tokens["dark"])
        assert not res.dark_derived

    def test_missing_dark_is_derived_not_filled(self):
        res = T.validate_tokens({"light": {"primary": "10 50% 40%"}})
        assert res.dark_derived
        assert not any(k.startswith("dark.") for k in res.filled_from_default)
        assert res.tokens["dark"] == T.derive_dark(res.tokens["light"])

    def test_lenient_drops_bad_values_and_reports_them(self):
        res = T.validate_tokens({"light": {"primary": "url(javascript:x)", "accent": "200 50% 50%"}}, lenient=True)
        assert res.tokens["light"]["primary"] == T.platform_tokens()["light"]["primary"]
        assert res.tokens["light"]["accent"] == "200 50% 50%"
        assert any("light.primary" in r for r in res.refused)
        assert any("valor recusado" in w for w in res.as_validation()["warnings"])

    def test_platform_document_is_servable(self):
        assert T.assert_servable(T.platform_tokens())["light"] == T.platform_tokens()["light"]


class TestDarkDerivation:
    def test_deterministic_and_hue_preserving(self):
        light = T.platform_tokens()["light"] | {"primary": "210 60% 45%"}
        a, b = T.derive_dark(light), T.derive_dark(dict(light))
        assert a == b and set(a) == set(light)
        assert T.parse_hsl(a["primary"])[0] == 210

    def test_rules(self):
        light = {
            "background": "0 0% 97%", "foreground": "0 0% 10%",
            "primary": "220 40% 40%", "primary-foreground": "0 0% 100%",
            "sidebar-background": "0 0% 10%", "success-light": "142 40% 92%",
        }
        dark = T.derive_dark(light)
        assert dark["background"] == "0 0% 6%"            # light surface → max(100-97, 6)
        assert dark["foreground"] == "0 0% 90%"           # fg on a light surface → inverted
        assert dark["primary"] == "220 40% 50%"           # mid tone → +10
        assert dark["primary-foreground"] == "0 0% 100%"  # fg on a strong surface → kept
        assert dark["sidebar-background"] == "0 0% 6%"    # dark surface → -4
        assert dark["success-light"] == "142 20% 8%"      # tint → inverted, saturation halved


class TestContrast:
    def test_known_ratios(self):
        assert T.contrast_ratio("0 0% 0%", "0 0% 100%") == 21.0
        assert T.contrast_ratio("0 0% 50%", "0 0% 50%") == 1.0
        assert T.contrast_ratio("bad", "0 0% 100%") is None

    def test_report_pairs_derived_from_names_and_flags_failures(self):
        res = T.validate_tokens({"light": {"primary": "0 0% 60%", "primary-foreground": "0 0% 100%"}})
        pair = next(c for c in res.contrast if c["mode"] == "light" and c["foreground"] == "primary-foreground")
        assert pair["background"] == "primary" and pair["passes_aa"] is False
        assert any("primary-foreground sobre primary" in w for w in res.as_validation()["warnings"])
        assert {c["background"] for c in res.contrast} >= {"background", "card", "sidebar-background"}
