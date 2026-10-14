"""Enum parity with CONTRACT §1 (the frontend organ mirrors these literals)."""
from __future__ import annotations

from noctusai_lib.domain.commerce import types as t

CONTRACT_ENUMS = {
    "ProductType": ["digital", "physical", "service", "print_on_demand"],
    "FulfillmentType": ["digital_delivery", "shipping", "pickup", "local_delivery", "none"],
    "ProductStatus": ["draft", "in_review", "published", "unlisted", "retired"],
    "OrderStatus": [
        "created", "pending_payment", "paid", "expired", "failed", "cancelled", "refunded", "chargeback",
        "partially_refunded", "disputed",
    ],
    "TaxRegime": ["mei", "simples", "lucro_presumido", "lucro_real", "outro"],
    "TaxTreatment": ["service_nfse", "rights_receipt", "goods_nfe", "none"],
    "CouponKind": ["percent", "fixed"],
    "ConsentKind": ["terms", "privacy", "marketing", "immediate_delivery_waiver"],
    "PrivacyRequestKind": ["access", "correction", "deletion", "portability", "revoke_consent"],
    "FieldSource": ["form", "payment", "staff"],
    "PaymentMethod": ["pix", "boleto", "credit_card"],
    "RefundStatus": ["requested", "done", "failed"],
    "ChargeAttemptStatus": ["pending", "paid", "expired", "cancelled", "failed"],
    "ReminderKind": ["before_expiry", "after_expiry"],
    # closed sets fixed by §2 columns (mirrored by the FE types.ts)
    "MediaKind": ["image", "video"],
    "PrivacyRequestStatus": ["open", "verified", "done", "rejected"],
    "OrderEventSource": ["checkout", "webhook", "staff", "system"],
}


def test_every_contract_enum_matches_exactly():
    for name, expected in CONTRACT_ENUMS.items():
        assert list(t.values(getattr(t, name))) == expected, name


def test_enums_serialise_as_bare_strings():
    assert t.OrderStatus.PAID == "paid"
    assert t.ProductType("digital") is t.ProductType.DIGITAL


def test_digital_line_detection():
    assert t.is_digital_line("digital", "none")
    assert t.is_digital_line("service", "digital_delivery")
    assert not t.is_digital_line("physical", "shipping")
