"""Leaf module: the API-token bearer prefixes (no package imports, so both
``_reasons`` and ``session.*`` can use it without an import cycle)."""

NEW_TOKEN_PREFIX = "noc_"
# NOC-REMEDIATE[pk-prefix-cutoff]: drop once every live token is reissued as noc_.
LEGACY_TOKEN_PREFIX = "pk_"
ACCEPTED_TOKEN_PREFIXES = (NEW_TOKEN_PREFIX, LEGACY_TOKEN_PREFIX)


def has_api_token_prefix(value: str) -> bool:
    """``True`` when a bearer value looks like one of our API tokens."""
    return value.startswith(ACCEPTED_TOKEN_PREFIXES)
