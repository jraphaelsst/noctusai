import pytest

from noctusai_lib.integrations.invoices import (
    FakeInvoiceProvider,
    FocusNFeInvoiceProvider,
    InvoiceEnvironment,
    InvoiceNotConfigured,
    make_invoice_provider,
    resolve_invoice_environment,
)

NO_CRED = lambda key: None  # noqa: E731


def env(cred, allow, tier):
    return resolve_invoice_environment(
        environment_credential=cred, allow_production_env=allow, token_environment=tier, fetch_credential=NO_CRED
    )


def test_default_is_homologacao():
    assert env(None, False, None) is InvoiceEnvironment.HOMOLOGACAO
    assert env("homologacao", True, "homologacao") is InvoiceEnvironment.HOMOLOGACAO


def test_producao_needs_both_gates_and_declared_tier():
    assert env("producao", True, "producao") is InvoiceEnvironment.PRODUCAO
    with pytest.raises(InvoiceNotConfigured) as exc:
        env("producao", False, "producao")  # credential alone is not enough
    assert exc.value.code == "production_not_allowed"
    with pytest.raises(InvoiceNotConfigured) as exc:
        env("producao", True, None)  # undeclared tier is refused in production
    assert exc.value.code == "token_tier_undeclared"


def test_env_flag_alone_does_not_enable_producao():
    assert env(None, True, None) is InvoiceEnvironment.HOMOLOGACAO
    assert env("homologacao", True, None) is InvoiceEnvironment.HOMOLOGACAO


@pytest.mark.parametrize("cred,tier", [("producao", "homologacao"), ("homologacao", "producao")])
def test_token_tier_environment_mismatch_refused(cred, tier):
    with pytest.raises(InvoiceNotConfigured) as exc:
        env(cred, True, tier)
    assert exc.value.code == "token_environment_mismatch"


def test_invalid_environment_value():
    with pytest.raises(InvoiceNotConfigured) as exc:
        env("staging", True, None)
    assert exc.value.code == "environment_invalid"


def test_use_fake_wins():
    assert isinstance(make_invoice_provider(use_fake=True), FakeInvoiceProvider)


def test_unconfigured_refuses_unless_allow_fake():
    with pytest.raises(InvoiceNotConfigured) as exc:
        make_invoice_provider(fetch_credential=NO_CRED)
    assert exc.value.code == "not_configured"
    assert isinstance(make_invoice_provider(fetch_credential=NO_CRED, allow_fake=True), FakeInvoiceProvider)
    sentinel = make_invoice_provider(fetch_credential=NO_CRED, unconfigured=lambda: None)
    assert sentinel is None


def test_configured_builds_real_and_never_the_fake():
    p = make_invoice_provider(account_token="tok", fetch_credential=NO_CRED, allow_fake=True)
    assert isinstance(p, FocusNFeInvoiceProvider)


def test_configured_real_applies_production_guard():
    with pytest.raises(InvoiceNotConfigured):
        make_invoice_provider(
            account_token="tok", environment_credential="producao",
            allow_production_env=False, token_environment="producao", fetch_credential=NO_CRED,
        )
    p = make_invoice_provider(
        account_token="tok", environment_credential="producao",
        allow_production_env=True, token_environment="producao", fetch_credential=NO_CRED,
    )
    assert p._base_url == "https://api.focusnfe.com.br"


def test_token_read_from_platform_credential_when_not_passed():
    creds = {"focusnfe_token": "from-platform"}
    p = make_invoice_provider(fetch_credential=creds.get)
    assert isinstance(p, FocusNFeInvoiceProvider)


def test_unknown_provider():
    with pytest.raises(ValueError):
        make_invoice_provider("nfeio", fetch_credential=NO_CRED)


def test_env_var_is_read_when_not_injected(monkeypatch):
    monkeypatch.setenv("FOCUSNFE_ALLOW_PRODUCTION", "1")
    assert resolve_invoice_environment(
        environment_credential="producao", token_environment="producao", fetch_credential=NO_CRED
    ) is InvoiceEnvironment.PRODUCAO
    monkeypatch.setenv("FOCUSNFE_ALLOW_PRODUCTION", "true")  # only the literal "1" counts
    with pytest.raises(InvoiceNotConfigured):
        resolve_invoice_environment(
            environment_credential="producao", token_environment="producao", fetch_credential=NO_CRED
        )
