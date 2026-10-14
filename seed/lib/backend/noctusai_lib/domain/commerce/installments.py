"""Card installments -- the quote math (CONTRACT §2.4, owner decisions D33 + D41).

* The buyer may pay a card order in `1..installments_max` parcelas.
* Up to `installments_interest_free` parcelas the buyer pays the order total; above
  that the total is the Price-table (tabela Price, "parcelas iguais") amount at the
  monthly interest rate, and the buyer carries the interest (the merchant receives it).
* Everything is integer cents. The total is rounded to the cent ONCE; the parcelas
  are `total // n` each and the LAST one absorbs the remainder, so
  `sum(split_installments(total, n)) == total` always.
* A created charge keeps the total it was quoted: changing the rate afterwards only
  affects new quotes (the charge row stores `amount_cents`).

Rate resolution (D41) -- first hit wins:

    1. the store's `installment_interest_monthly_bps` (nullable; null = follow the platform);
    2. the platform-tier credential/setting `commerce_installment_interest_bps`
       (`resolve_credential`), so ops can change the default without a deploy;
    3. the code constant `DEFAULT_INSTALLMENT_INTEREST_BPS = 199` (1.99 % a.m.).

A platform value that is not a sane integer is LOGGED at error level and skipped --
never silently coerced into a price.

Pure functions only (the one IO seam, the credential lookup, is injectable), so the
whole module is table-testable.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Mapping, Optional

logger = logging.getLogger(__name__)

#: 1.99 % a.m. -- the owner's platform default (D41).
DEFAULT_INSTALLMENT_INTEREST_BPS = 199
#: The platform-tier `resolve_credential` key that overrides the constant.
INSTALLMENT_INTEREST_CREDENTIAL = "commerce_installment_interest_bps"
#: Hard ceiling for any configured rate (20 % a.m.): a typo must not become a price.
MAX_INSTALLMENT_INTEREST_BPS = 2000
#: Gateway-side card minimum per parcela (Asaas refuses smaller ones); options below are not offered.
MIN_INSTALLMENT_CENTS = 500
#: Absolute limits of the product (Asaas allows up to 12 on a one-off card charge).
MAX_INSTALLMENTS = 12
DEFAULT_INSTALLMENTS_MAX = 12
DEFAULT_INSTALLMENTS_INTEREST_FREE = 3

CredentialResolver = Callable[[str, Optional[str]], Optional[str]]


def _platform_resolver(name: str, org_id: Optional[str]) -> Optional[str]:
    from noctusai_lib.security.api_keys import resolve_credential

    return resolve_credential(name, org_id)


def _parse_bps(raw: Any, source: str) -> Optional[int]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        bps = int(str(raw).strip())
    except ValueError:
        logger.error("commerce installments: %s is not an integer (%r); ignored", source, raw)
        return None
    if not 0 <= bps <= MAX_INSTALLMENT_INTEREST_BPS:
        logger.error("commerce installments: %s=%s is outside 0..%s bps; ignored", source, bps, MAX_INSTALLMENT_INTEREST_BPS)
        return None
    return bps


def resolve_interest_bps(profile: Optional[Mapping[str, Any]], *, resolver: Optional[CredentialResolver] = None) -> int:
    """The monthly buyer-interest rate in bps for this store (D41 resolution order)."""
    stored = _parse_bps((profile or {}).get("installment_interest_monthly_bps"), "the store's installment_interest_monthly_bps")
    if stored is not None:
        return stored
    try:
        platform = (resolver or _platform_resolver)(INSTALLMENT_INTEREST_CREDENTIAL, None)
    except Exception:  # noqa: BLE001 - an unreachable settings store must not break checkout; the constant is the documented floor
        logger.warning("commerce installments: platform rate lookup failed; using the default", exc_info=True)
        platform = None
    parsed = _parse_bps(platform, f"platform setting {INSTALLMENT_INTEREST_CREDENTIAL}")
    return parsed if parsed is not None else DEFAULT_INSTALLMENT_INTEREST_BPS


def price_table_total(principal_cents: int, count: int, monthly_bps: int) -> int:
    """Total paid in `count` equal parcelas at `monthly_bps` a.m. (tabela Price), in cents.

    PMT = P * i / (1 - (1 + i) ** -n);  total = PMT * n, rounded half-up to the cent once.
    `monthly_bps == 0` (or one parcela) is the principal untouched.
    """
    if principal_cents <= 0:
        raise ValueError("principal_cents must be > 0")
    if count < 1:
        raise ValueError("count must be >= 1")
    if count == 1 or monthly_bps <= 0:
        return principal_cents
    i = Decimal(monthly_bps) / Decimal(10000)
    factor = (1 + i) ** count
    # PMT * n = P * i * n * (1 + i)^n / ((1 + i)^n - 1)
    total = Decimal(principal_cents) * i * count * factor / (factor - 1)
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def split_installments(total_cents: int, count: int) -> list[int]:
    """`count` parcelas that sum to `total_cents`; the last absorbs the remainder."""
    if count < 1:
        raise ValueError("count must be >= 1")
    base = total_cents // count
    parts = [base] * count
    parts[-1] = total_cents - base * (count - 1)
    return parts


def installment_settings(profile: Optional[Mapping[str, Any]]) -> tuple[int, int]:
    """`(installments_max, installments_interest_free)` of the store, with the product defaults."""
    p = profile or {}
    max_n = int(p.get("installments_max") or DEFAULT_INSTALLMENTS_MAX)
    free_n = int(p.get("installments_interest_free") or DEFAULT_INSTALLMENTS_INTEREST_FREE)
    max_n = max(1, min(max_n, MAX_INSTALLMENTS))
    return max_n, max(1, min(free_n, max_n))


def installment_options(
    total_cents: int,
    profile: Optional[Mapping[str, Any]],
    *,
    resolver: Optional[CredentialResolver] = None,
) -> list[dict]:
    """The card options for `total_cents`: `[{count, installment_cents, total_cents, interest_free}]`.

    `installment_cents` is the regular parcela (the last one may differ by the rounding
    remainder). A count whose parcela would fall under the gateway minimum is not offered
    (the one-parcela option always is).
    """
    if total_cents <= 0:
        return []
    max_n, free_n = installment_settings(profile)
    bps = resolve_interest_bps(profile, resolver=resolver)
    options: list[dict] = []
    for count in range(1, max_n + 1):
        free = count <= free_n
        total = total_cents if free else price_table_total(total_cents, count, bps)
        parts = split_installments(total, count)
        if count > 1 and parts[0] < MIN_INSTALLMENT_CENTS:
            continue
        options.append(
            {"count": count, "installment_cents": parts[0], "total_cents": total, "interest_free": total == total_cents}
        )
    return options


def option_for(
    total_cents: int,
    count: int,
    profile: Optional[Mapping[str, Any]],
    *,
    resolver: Optional[CredentialResolver] = None,
) -> Optional[dict]:
    """The offered option for exactly `count` parcelas, or None (-> 422 `parcelamento_invalido`)."""
    for option in installment_options(total_cents, profile, resolver=resolver):
        if option["count"] == count:
            return option
    return None


__all__ = [
    "DEFAULT_INSTALLMENTS_INTEREST_FREE",
    "DEFAULT_INSTALLMENTS_MAX",
    "DEFAULT_INSTALLMENT_INTEREST_BPS",
    "INSTALLMENT_INTEREST_CREDENTIAL",
    "MAX_INSTALLMENTS",
    "MAX_INSTALLMENT_INTEREST_BPS",
    "MIN_INSTALLMENT_CENTS",
    "installment_options",
    "installment_settings",
    "option_for",
    "price_table_total",
    "resolve_interest_bps",
    "split_installments",
]
