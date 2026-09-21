"""`default_llm_config`'s `usage_tracking_supports_image_columns` wiring.

Custos-page slice: social-wiring's `llm_usage` table is the WIDE shape
(`122_llm_usage.sql`, from `llm_usage.sql.template`), so its
`SupabaseUsageSink` must be constructed with `supports_image_columns=True`.
Before this change, `default_llm_config` never forwarded that flag, so
every product's sink silently used the narrow (default False) shape
regardless of which table template it was actually built from — the
image_input_tokens / image_output_tokens / model_version / batch columns
were computed on every `UsageEvent` but dropped at insert time.

Pure unit test against `default_llm_config` + `LLMConfig.usage_sink` —
no app factory, no network, no DB.
"""
from __future__ import annotations

from noctusai_lib.integrations.llm.usage import SupabaseUsageSink
from noctusai_seed.llm_defaults import default_llm_config


class _StubDbClient:
    """`default_llm_config` only stores this on the sink — never calls it
    in this test, so an empty stand-in is enough."""


def test_default_llm_config_forwards_supports_image_columns_true() -> None:
    config = default_llm_config(
        usage_tracking_db=_StubDbClient(),
        usage_tracking_schema="social_wiring",
        usage_tracking_supports_image_columns=True,
    )

    assert isinstance(config.usage_sink, SupabaseUsageSink)
    assert config.usage_sink._supports_image_columns is True
    assert config.usage_sink._schema == "social_wiring"


def test_default_llm_config_defaults_supports_image_columns_false() -> None:
    """Back-compat: a product that doesn't pass the new kwarg (every
    pre-existing caller) gets the narrow shape, byte-identical to before
    this change."""
    config = default_llm_config(
        usage_tracking_db=_StubDbClient(),
        usage_tracking_schema="erp",
    )

    assert isinstance(config.usage_sink, SupabaseUsageSink)
    assert config.usage_sink._supports_image_columns is False


def test_default_llm_config_no_sink_when_db_or_schema_missing() -> None:
    """Unrelated to the new kwarg — confirms the existing guard clause
    still short-circuits (usage_sink stays whatever the base LLMConfig
    default is) when either half of the pair is missing."""
    config = default_llm_config(usage_tracking_db=_StubDbClient())
    assert not isinstance(config.usage_sink, SupabaseUsageSink)
