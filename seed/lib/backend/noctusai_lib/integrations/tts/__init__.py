"""TTS seam -- Protocol + Fake + Real (ElevenLabs) + factory.

    from noctusai_lib.integrations.tts import make_tts_client
    client = make_tts_client(out_dir=tmp, org_id=org, consent=my_consent_ledger)
    res = client.synthesize("Ola mundo", voice_id, "eleven_multilingual_v2", consent_ref="termo-123")

`ConsentChecker` is implemented by the product; synthesize/clone refuse with the coded
`consentimento_ausente` when it says no. Vendor-side Avatar/layout adapters are later slices.
"""
from __future__ import annotations

from noctusai_lib.integrations.tts.alignment import palavras_do_alinhamento
from noctusai_lib.integrations.tts.elevenlabs_adapter import ElevenLabsTtsClient
from noctusai_lib.integrations.tts.factory import CREDENTIAL_KEY, make_tts_client
from noctusai_lib.integrations.tts.fake_adapter import FakeTtsClient
from noctusai_lib.integrations.tts.transport import HttpxTransport, Transport
from noctusai_lib.integrations.tts.types import (
    CloneResult,
    ConsentChecker,
    ConsentimentoAusente,
    PalavraTiming,
    Preflight,
    TtsClient,
    TtsError,
    TtsNotConfigured,
    TtsRefused,
    TtsResult,
    TtsUpstreamError,
)

__all__ = [
    "CREDENTIAL_KEY", "CloneResult", "ConsentChecker", "ConsentimentoAusente", "ElevenLabsTtsClient",
    "FakeTtsClient", "HttpxTransport", "PalavraTiming", "Preflight", "TtsClient", "TtsError",
    "TtsNotConfigured", "TtsRefused", "TtsResult", "TtsUpstreamError", "Transport",
    "make_tts_client", "palavras_do_alinhamento",
]
