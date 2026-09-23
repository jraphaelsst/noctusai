"""``detect_actor_kind`` / ``client_hint_from_ua`` — pure-function tests."""
from __future__ import annotations

from noctusai_lib.api.audit.detect import client_hint_from_ua, detect_actor_kind

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADLESS_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HeadlessChrome/120.0.0.0 Safari/537.36"
)
_PLAYWRIGHT_UA = "Mozilla/5.0 ... Playwright/1.40.0"


class TestDetectActorKind:
    def test_defaults_to_user_with_no_signal(self) -> None:
        assert detect_actor_kind(x_noctus_client=None, user_agent=None) == "user"

    def test_web_header_is_user(self) -> None:
        assert detect_actor_kind(x_noctus_client="web", user_agent=_CHROME_UA) == "user"

    def test_agent_prefixed_header_wins(self) -> None:
        assert detect_actor_kind(x_noctus_client="agent:webdriver", user_agent=_CHROME_UA) == "agent"

    def test_service_header_wins_over_agent_looking_ua(self) -> None:
        # Explicit `service` header is authoritative even against an
        # automation-shaped UA — a service caller's UA is whatever the
        # HTTP client library sets, never meaningful.
        assert detect_actor_kind(x_noctus_client="service", user_agent=_HEADLESS_UA) == "service"

    def test_headless_chrome_ua_alone_is_agent(self) -> None:
        assert detect_actor_kind(x_noctus_client=None, user_agent=_HEADLESS_UA) == "agent"

    def test_playwright_ua_alone_is_agent(self) -> None:
        assert detect_actor_kind(x_noctus_client=None, user_agent=_PLAYWRIGHT_UA) == "agent"

    def test_header_is_case_insensitive(self) -> None:
        assert detect_actor_kind(x_noctus_client="SERVICE", user_agent=None) == "service"
        assert detect_actor_kind(x_noctus_client="Agent:foo", user_agent=None) == "agent"


class TestClientHintFromUa:
    def test_unknown_for_missing_ua(self) -> None:
        assert client_hint_from_ua(None) == "unknown"
        assert client_hint_from_ua("") == "unknown"

    def test_extracts_headless_chrome_before_chrome(self) -> None:
        # HeadlessChrome UAs also contain the substring "Chrome" — the
        # family regex must match the more specific alternative first.
        assert client_hint_from_ua(_HEADLESS_UA) == "HeadlessChrome"

    def test_extracts_chrome_family(self) -> None:
        assert client_hint_from_ua(_CHROME_UA) == "Chrome"

    def test_falls_back_to_truncated_raw_string(self) -> None:
        hint = client_hint_from_ua("SomeExoticClient/9.9 unrecognised-format")
        assert hint == "SomeExoticClient/9.9 unrecognised-format"[:40]
        assert len(hint) <= 40
