"""The inbound credential we register, and the URL we register it against.

Both are integrator-wide: there is no agency in the callback config, so a
wrong value here is not one tenant's problem, it is the whole fleet's.
"""

from __future__ import annotations

import base64

import pytest

from noctusai_lib.integrations.imovelweb.types import (
    IMOVELWEB_BASIC_USERNAME,
    basic_credential,
    receiver_url_problems,
)


class TestBasicCredential:
    def test_carries_the_literal_prefix(self):
        # The vendor forwards the string verbatim and our own verifier
        # requires the word — a malformed one fails at OUR end and reads
        # like a vendor problem.
        assert basic_credential("s3cret").startswith("Basic ")

    def test_decodes_to_username_colon_secret(self):
        token = basic_credential("s3cret").removeprefix("Basic ")
        assert base64.b64decode(token).decode() == f"{IMOVELWEB_BASIC_USERNAME}:s3cret"

    def test_is_not_grupo_olx_s_username(self):
        # Reusing `vivareal` would make the two receivers interchangeable,
        # and they verify different secrets on different pipes.
        assert IMOVELWEB_BASIC_USERNAME != "vivareal"

    def test_a_config_built_from_it_validates(self):
        from noctusai_lib.integrations.imovelweb.types import CallbackConfig

        config = CallbackConfig(
            url="https://noc.example.com/api/portals/imovelweb/leads",
            authorization_header_value=basic_credential("s3cret"),
        )
        assert config.validate() == ()


class TestReceiverUrlProblems:
    def test_a_real_public_https_url_is_clean(self):
        assert receiver_url_problems("https://noc.example.com/api/x") == ()

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8000/api",
            "https://127.0.0.1/api",
            "http://[::1]:8000/api",
            "https://noc.local/api",
        ],
    )
    def test_local_hosts_are_refused(self, url):
        assert any("local" in p for p in receiver_url_problems(url))

    @pytest.mark.parametrize(
        "url",
        ["https://10.0.0.4/api", "https://192.168.1.7/api", "https://172.20.0.3/api"],
    )
    def test_private_ranges_are_refused(self, url):
        assert any("private" in p for p in receiver_url_problems(url))

    def test_a_public_ip_is_not_mistaken_for_private(self):
        assert receiver_url_problems("https://172.15.0.3/api") == ()

    @pytest.mark.parametrize(
        "url",
        [
            "https://abc123.ngrok-free.app/api",
            "https://quiet-tree.trycloudflare.com/api",
            "https://x.loca.lt/api",
            "https://y.devtunnels.ms/api",
        ],
    )
    def test_ephemeral_tunnels_are_refused_by_name(self, url):
        problems = receiver_url_problems(url)
        assert any("ephemeral tunnel" in p for p in problems)
        # The reason matters more than the refusal: the config is
        # integrator-wide, so the whole fleet goes down with the tunnel.
        assert any("INTEGRATOR-WIDE" in p for p in problems)

    def test_plaintext_http_on_a_public_host_is_refused(self):
        # There is no signature scheme, so TLS is the only thing
        # protecting a static credential in transit.
        assert any("plaintext" in p for p in receiver_url_problems("http://noc.example.com/api"))

    def test_plaintext_localhost_is_not_double_reported_for_tls(self):
        problems = receiver_url_problems("http://localhost:8000/api")
        assert not any("plaintext" in p for p in problems)

    def test_a_missing_url_says_so(self):
        assert receiver_url_problems(None) == ("no receiver url",)
        assert receiver_url_problems("") == ("no receiver url",)

    def test_a_non_http_scheme_is_refused(self):
        assert any("http://" in p for p in receiver_url_problems("ftp://noc.example.com"))

    def test_credentials_in_the_url_do_not_hide_a_local_host(self):
        # `https://user:pw@localhost/api` — the host is after the '@'.
        assert any("local" in p for p in receiver_url_problems("https://u:p@localhost/api"))
