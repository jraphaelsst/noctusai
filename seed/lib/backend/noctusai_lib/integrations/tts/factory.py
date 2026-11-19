"""`make_tts_client` -- key via the platform credential chain, never env-only.

Missing key => `TtsNotConfigured` (a declared refusal) unless the caller opts into the
Fake with `allow_fake=True` (a test/dev setting the consumer owns).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.integrations.tts.elevenlabs_adapter import DEFAULT_MAX_CHARS, ElevenLabsTtsClient
from noctusai_lib.integrations.tts.fake_adapter import FakeTtsClient
from noctusai_lib.integrations.tts.transport import DEFAULT_BASE_URL, Transport
from noctusai_lib.integrations.tts.types import ConsentChecker, TtsClient, TtsNotConfigured

CREDENTIAL_KEY = "elevenlabs_api_key"


def _resolve_key(org_id: Optional[str]) -> Optional[str]:
    from noctusai_lib.config.credentials import resolve_credential  # lazy: needs the DB client only when called

    return resolve_credential(CREDENTIAL_KEY, org_id)


def _refuse() -> TtsClient:
    raise TtsNotConfigured()


def make_tts_client(
    *,
    out_dir: Path,
    org_id: Optional[str] = None,
    consent: Optional[ConsentChecker] = None,
    api_key: Optional[str] = None,
    allow_fake: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    max_chars: int = DEFAULT_MAX_CHARS,
    zero_retention: bool = True,
    transport: Optional[Transport] = None,
    wpm: float = 165.0,
    key_resolver: Callable[[Optional[str]], Optional[str]] = _resolve_key,
) -> TtsClient:
    key = api_key or (None if transport else key_resolver(org_id))
    return resolve_fake_or_refuse(
        configured=bool(key) or transport is not None,
        build_real=lambda: ElevenLabsTtsClient(
            key, out_dir=out_dir, org_id=org_id, consent=consent, base_url=base_url, max_chars=max_chars,
            zero_retention=zero_retention, transport=transport),
        build_fake=lambda: FakeTtsClient(out_dir=out_dir, org_id=org_id, consent=consent, wpm=wpm),
        allow_fake=allow_fake,
        unconfigured=_refuse,
    )
