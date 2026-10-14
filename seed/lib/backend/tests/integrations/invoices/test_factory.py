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


@pytest.fixture
def env(monkeypatch):
    """(cred, allow_env_flag, tier) -> environment, through the REAL gates only:
    the platform-credential lookup seam + the process env var."""

    def _env(cred, allow, tier):
        if allow:
            monkeypatch.setenv("FOCUSNFE_ALLOW_PRODUCTION", "1")
        else:
            monkeypatch.delenv("FOCUSNFE_ALLOW_PRODUCTION", raising=False)
        creds = {"focusnfe_environment": cred, "focusnfe_token_environment": tier}
        return resolve_invoice_environment(fetch_credential=creds.get)

    return _env


def test_default_is_homologacao(env):
    assert env(None, False, None) is InvoiceEnvironment.HOMOLOGACAO
    assert env("homologacao", True, "homologacao") is InvoiceEnvironment.HOMOLOGACAO


def test_producao_needs_both_gates_and_declared_tier(env):
    assert env("producao", True, "producao") is InvoiceEnvironment.PRODUCAO
    with pytest.raises(InvoiceNotConfigured) as exc:
        env("producao", False, "producao")  # credential alone is not enough
    assert exc.value.code == "production_not_allowed"
    with pytest.raises(InvoiceNotConfigured) as exc:
        env("producao", True, None)  # undeclared tier is refused in production
    assert exc.value.code == "token_tier_undeclared"


def test_env_flag_alone_does_not_enable_producao(env):
    assert env(None, True, None) is InvoiceEnvironment.HOMOLOGACAO
    assert env("homologacao", True, None) is InvoiceEnvironment.HOMOLOGACAO


@pytest.mark.parametrize("cred,tier", [("producao", "homologacao"), ("homologacao", "producao")])
def test_token_tier_environment_mismatch_refused(env, cred, tier):
    with pytest.raises(InvoiceNotConfigured) as exc:
        env(cred, True, tier)
    assert exc.value.code == "token_environment_mismatch"


def test_invalid_environment_value(env):
    with pytest.raises(InvoiceNotConfigured) as exc:
        env("staging", True, None)
    assert exc.value.code == "environment_invalid"


def test_no_argument_can_assert_production_allowed():
    import inspect

    params = set(inspect.signature(make_invoice_provider).parameters) | set(
        inspect.signature(resolve_invoice_environment).parameters
    )
    assert not params & {"allow_production_env", "environment_credential", "token_environment"}


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


def test_configured_real_applies_production_guard(monkeypatch):
    creds = {"focusnfe_environment": "producao", "focusnfe_token_environment": "producao"}
    monkeypatch.delenv("FOCUSNFE_ALLOW_PRODUCTION", raising=False)
    with pytest.raises(InvoiceNotConfigured):
        make_invoice_provider(account_token="tok", fetch_credential=creds.get)
    monkeypatch.setenv("FOCUSNFE_ALLOW_PRODUCTION", "1")
    p = make_invoice_provider(account_token="tok", fetch_credential=creds.get)
    assert p._base_url == "https://api.focusnfe.com.br"


def test_token_read_from_platform_credential_when_not_passed():
    creds = {"focusnfe_token": "from-platform"}
    p = make_invoice_provider(fetch_credential=creds.get)
    assert isinstance(p, FocusNFeInvoiceProvider)


def test_unknown_provider():
    with pytest.raises(ValueError):
        make_invoice_provider("nfeio", fetch_credential=NO_CRED)


def test_only_the_literal_one_counts(monkeypatch):
    creds = {"focusnfe_environment": "producao", "focusnfe_token_environment": "producao"}
    monkeypatch.setenv("FOCUSNFE_ALLOW_PRODUCTION", "true")
    with pytest.raises(InvoiceNotConfigured):
        resolve_invoice_environment(fetch_credential=creds.get)
