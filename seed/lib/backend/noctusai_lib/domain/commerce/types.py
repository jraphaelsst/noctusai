"""Commerce vocabulary — every enum of `projects/commerce-seed-p3/CONTRACT.md §1`.

`str` Enums, so a value serialises as its bare string in JSON and compares equal
to the literal the frontend organ (`@noctusai/lib` `commerce/types.ts`) mirrors.
A parity test pins the two sides; renaming a member here is a wire-contract
change, never a refactor.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class ProductType(_StrEnum):
    DIGITAL = "digital"
    PHYSICAL = "physical"
    SERVICE = "service"
    PRINT_ON_DEMAND = "print_on_demand"


class FulfillmentType(_StrEnum):
    DIGITAL_DELIVERY = "digital_delivery"
    SHIPPING = "shipping"
    PICKUP = "pickup"
    LOCAL_DELIVERY = "local_delivery"
    NONE = "none"


class ProductStatus(_StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    UNLISTED = "unlisted"
    RETIRED = "retired"


class OrderStatus(_StrEnum):
    CREATED = "created"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    CHARGEBACK = "chargeback"


class TaxRegime(_StrEnum):
    MEI = "mei"
    SIMPLES = "simples"
    LUCRO_PRESUMIDO = "lucro_presumido"
    LUCRO_REAL = "lucro_real"
    OUTRO = "outro"


class TaxTreatment(_StrEnum):
    SERVICE_NFSE = "service_nfse"
    RIGHTS_RECEIPT = "rights_receipt"
    GOODS_NFE = "goods_nfe"
    NONE = "none"


class CouponKind(_StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class ConsentKind(_StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"
    MARKETING = "marketing"
    IMMEDIATE_DELIVERY_WAIVER = "immediate_delivery_waiver"


class PrivacyRequestKind(_StrEnum):
    ACCESS = "access"
    CORRECTION = "correction"
    DELETION = "deletion"
    PORTABILITY = "portability"
    REVOKE_CONSENT = "revoke_consent"


class FieldSource(_StrEnum):
    FORM = "form"
    PAYMENT = "payment"
    STAFF = "staff"


class PaymentMethod(_StrEnum):
    PIX = "pix"
    BOLETO = "boleto"
    CREDIT_CARD = "credit_card"


class MediaKind(_StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class PrivacyRequestStatus(_StrEnum):
    OPEN = "open"
    VERIFIED = "verified"
    DONE = "done"
    REJECTED = "rejected"


class OrderEventSource(_StrEnum):
    CHECKOUT = "checkout"
    WEBHOOK = "webhook"
    STAFF = "staff"
    SYSTEM = "system"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    """The wire values of an enum, in declaration order (SQL CHECKs + parity tests)."""
    return tuple(member.value for member in enum_cls)


def is_digital_line(product_type: str, fulfillment_type: str) -> bool:
    """A line whose delivery is immediate and digital — the CDC art. 49 withdrawal
    right needs the buyer's EXPRESS waiver for it (Decreto 7.962 / CDC), so the
    checkout demands `immediate_delivery_waiver` when any line is digital."""
    return (
        product_type == ProductType.DIGITAL.value
        or fulfillment_type == FulfillmentType.DIGITAL_DELIVERY.value
    )


__all__ = [
    "ConsentKind",
    "CouponKind",
    "FieldSource",
    "FulfillmentType",
    "MediaKind",
    "OrderEventSource",
    "OrderStatus",
    "PaymentMethod",
    "PrivacyRequestKind",
    "PrivacyRequestStatus",
    "ProductStatus",
    "ProductType",
    "TaxRegime",
    "TaxTreatment",
    "is_digital_line",
    "values",
]
