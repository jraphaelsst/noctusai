"""A missing gateway key refuses — the Fake is an explicit opt-in.

Before 2026-09-28 both default factories fell back to the Fake gateway on a
missing key, so a misconfigured deploy would have shown a paying member a
fake Pix QR and "cancelled" subscriptions that kept billing. The test
harness opts in (`PAYMENTS_ALLOW_FAKE=true` in conftest); these tests drive
the factories through their injection seam (`resolve=`, `allow_fake=`) to
pin the production behavior.
"""
import pytest

from app.config import SeedSettings
from app.services import assinaturas_service, checkout_service

MSG = "Pagamentos indisponíveis no momento. Tente novamente mais tarde."
ORG = "11111111-1111-1111-1111-111111111111"


def _sem_chave(_key: str, _org: str) -> None:
    return None


@pytest.mark.parametrize("gateway", ["asaas", "stripe"])
def test_checkout_refuses_503_without_key(gateway):
    with pytest.raises(checkout_service.CheckoutServiceError) as exc:
        checkout_service._default_hosted_checkout_factory(
            gateway, org_id=ORG, resolve=_sem_chave, allow_fake=False,
        )
    assert exc.value.status_code == 503
    assert exc.value.detail == MSG


@pytest.mark.parametrize("gateway", ["asaas", "stripe"])
def test_staff_cancel_refuses_503_without_key(gateway):
    with pytest.raises(assinaturas_service.AssinaturasServiceError) as exc:
        assinaturas_service._default_gateway_factory(
            gateway, org_id=ORG, resolve=_sem_chave, allow_fake=False,
        )
    assert exc.value.status_code == 503
    assert exc.value.detail == MSG


def test_fake_only_with_explicit_opt_in():
    checkout = checkout_service._default_hosted_checkout_factory(
        "asaas", org_id=ORG, resolve=_sem_chave, allow_fake=True,
    )
    assert type(checkout).__name__.startswith("Fake")


def test_setting_defaults_off():
    """The shipped default is refuse — only the environment turns the Fake on."""
    assert SeedSettings.model_fields["payments_allow_fake"].default is False
