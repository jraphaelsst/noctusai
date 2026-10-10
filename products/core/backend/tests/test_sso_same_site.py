"""Same-site predicate for the SSO launch guard (roadmap P2.2 follow-up).

The SameSite=Strict bind cookie reaches redeem only when the product host is
same-site with core. Scheme and port never change the site.
"""
import pytest

from app.sso_regime import (
    LaunchNotSameSite, assert_launch_same_site, is_same_site, origin_same_site, site_of,
)

CORE = "https://noctusai.com"

# Measured in prod noctus-core env, 2026-10-10: PRODUCT_URL_* are all *.noctusai.com,
# PRODUCT_URL_CORE=https://noctusai.com, PRODUCT_URL_PATTERN=https://{slug}.noctusai.com.
PROD_LAUNCH_URLS = [
    "https://noctusai.com",
    "https://erp.noctusai.com",
    "https://social.noctusai.com",
    "https://core.noctusai.com",
    "https://academia-de-reciclagem.noctusai.com",
    "https://p-studio.noctusai.com",
    "https://orbity.noctusai.com",
    "https://igig.noctusai.com",
    "https://agents.noctusai.com",
    "https://{slug}.noctusai.com".replace("{slug}", "any-future-slug"),
]


@pytest.mark.parametrize("url", PROD_LAUNCH_URLS)
def test_prod_urls_pass_against_prod_core(url):
    assert is_same_site(url, CORE)


@pytest.mark.parametrize("url", PROD_LAUNCH_URLS)
def test_prod_urls_do_not_raise_guard(url, monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_CORE", CORE)
    assert_launch_same_site(url)


@pytest.mark.parametrize("a,b,expected", [
    ("https://erp.noctusai.com", "https://noctusai.com", True),        # subdomain <-> apex
    ("https://noctusai.com", "https://erp.noctusai.com", True),
    ("https://a.noctusai.com", "https://b.noctusai.com", True),        # siblings
    ("https://a.b.noctusai.com", "https://noctusai.com", True),        # deep subdomain
    ("https://academiadareciclagem.eco", "https://noctusai.com", False),  # .eco vs .com
    ("https://noctusai.eco", "https://noctusai.com", False),           # same label, other TLD
    ("https://evilnoctusai.com", "https://noctusai.com", False),       # suffix-string trap
    ("https://noctusai.com.evil.io", "https://noctusai.com", False),
    ("http://erp.noctusai.com", "https://noctusai.com", True),         # scheme ignored
    ("https://erp.noctusai.com:8443", "https://noctusai.com", True),   # port ignored
    ("https://ERP.NoctusAI.com.", "https://noctusai.com", True),       # case + trailing dot
    ("http://localhost:8080", "http://localhost:8000", True),          # localhost, any port
    ("http://localhost", "http://localhost:3000", True),
    ("http://localhost:8080", "https://noctusai.com", False),
    ("https://noctusai.com", "http://localhost:8000", False),
    ("http://127.0.0.1:8001", "http://127.0.0.1:8000", True),          # IP exact host
    ("http://127.0.0.1:8001", "http://localhost:8000", False),         # different site for cookies
    ("http://10.0.0.5", "http://10.0.0.6", False),                     # IPs never share a site
    ("http://[::1]:8000", "http://[::1]:9000", True),
    ("https://a.foo.com.br", "https://b.bar.com.br", False),           # multi-label suffix
    ("https://a.foo.com.br", "https://b.foo.com.br", True),
])
def test_is_same_site(a, b, expected):
    assert is_same_site(a, b) is expected
    assert is_same_site(b, a) is expected


@pytest.mark.parametrize("bad", ["", "   ", "https://", "not a url://"])
def test_unparseable_is_never_same_site(bad):
    assert is_same_site(bad, CORE) is False


def test_site_of_bare_host_and_none():
    assert site_of("erp.noctusai.com") == "noctusai.com"
    assert site_of("") is None


def test_cross_site_raises(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_CORE", CORE)
    with pytest.raises(LaunchNotSameSite):
        assert_launch_same_site("https://academiadareciclagem.eco")


def test_unresolvable_core_fails_closed(monkeypatch):
    for k in [k for k in __import__("os").environ if k.startswith("PRODUCT_URL_")]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(LaunchNotSameSite):
        assert_launch_same_site("https://erp.noctusai.com")


def test_origin_same_site(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_CORE", CORE)
    assert origin_same_site("https://erp.noctusai.com") is True
    assert origin_same_site("https://academiadareciclagem.eco") is False
    assert origin_same_site(None) is None
