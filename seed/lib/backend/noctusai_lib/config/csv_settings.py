"""Shared helpers for the platform's comma-separated-list settings idiom.

**Why list-typed settings fields stay raw `str` in this pydantic-settings
version.** `pydantic-settings` 2.5.2 (this repo's installed version — no
`NoDecode` available, that lands later) JSON-decodes ANY complex-typed
(`list[...]`/`dict[...]`) env-sourced field via `json.loads()` BEFORE any
`field_validator` runs — including `mode="before"` validators, which fire
AFTER that decode attempt, not instead of it. So a `list[str]` field fed a
plain `APPROVAL_ASSERTION_SECRETS=key1,key2` env value raises
`pydantic_settings.sources.SettingsError` at import time: `"key1,key2"` is
not valid JSON. The only way to accept a plain comma-separated env value on
this version is to declare the field as `str` and expose a `_list` property
that calls :func:`parse_csv_setting` — never `list[str]`. (A future
`pydantic-settings` upgrade that ships `NoDecode` would remove this
constraint; until then, EVERY new comma-separated setting must follow this
shape, not `list[str]` + a `mode="before"` validator — that shape looks
correct and fails only when a real env value hits it.)

Two call sites so far: `noctusai_lib.config.settings.BaseAppSettings.
cors_origins` (the original idiom; kept independent — see its own
docstring for why its "keep empties" behaviour is NOT reproduced here) and
`products/agents/backend/app/config.py::approval_assertion_secrets` +
`products/academia-de-reciclagem/backend/app/config.py`'s
`approval_assertion_secrets` / `primary_source_allowlist` (all three
consolidated onto this helper — the third copy of the idiom is the trigger
for extracting it, per the platform's N=3 DRY rule).
"""
from __future__ import annotations

__all__ = ["parse_csv_setting", "reject_json_array"]


def parse_csv_setting(raw: str, *, lower: bool = False) -> list[str]:
    """Split a comma-separated settings string into a clean list.

    Strips whitespace off every item and DROPS empty items (an item that is
    empty after stripping — e.g. a trailing comma, a doubled comma, or a
    lone-empty string — never appears in the result). Pass ``lower=True``
    to also lowercase every item (host-allowlist shape).

    NOT used by `BaseAppSettings.cors_origins_list`'s plain-comma-list
    branch — that property's current behaviour keeps empty items (e.g.
    ``"a,"`` → ``["a", ""]``), which is byte-different from this function's
    drop-empties behaviour, and CORS is a fleet-wide, live surface where
    changing that behaviour needs its own reviewed change, not a silent
    side effect of extracting this helper.
    """
    return [item.strip().lower() if lower else item.strip() for item in raw.split(",") if item.strip()]


def reject_json_array(value: str, env_name: str) -> str:
    """Fail loud on a `["a","b"]`-shaped raw value for a CSV-string setting.

    A field kept as raw `str` (see the module docstring for why) silently
    accepts a JSON-array-shaped env value as ONE item — the literal
    bracketed text — instead of the intended list, because nothing else
    rejects that shape. Call this from a `field_validator` on the raw
    field; returns `value` unchanged when it's not JSON-array-shaped, so it
    composes as the first line of a validator body.
    """
    if value.strip().startswith("["):
        raise ValueError(
            f"{env_name} is comma-separated ('key1,key2'), not a JSON "
            f"array — got a JSON-array-shaped value: {value!r}"
        )
    return value
