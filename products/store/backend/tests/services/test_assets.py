import asyncio

import pytest

from app.services.assets import BUCKET, KIT_KEY, MAX_KIT_BYTES, AssetRejected, AssetService
from noctusai_lib.integrations.storage.fake import FakeStorageBackend


def run(c):
    return asyncio.run(c)


def test_bucket_and_layout_are_the_contract_ones():
    assert BUCKET == "store-produtos" and KIT_KEY == "contrato-blindado/kit.zip"


def test_kit_over_cap_is_413():
    with pytest.raises(AssetRejected) as exc:
        run(AssetService(FakeStorageBackend()).put_kit(b"PK\x03\x04" + b"0" * MAX_KIT_BYTES))
    assert exc.value.status_code == 413


def test_signed_urls_are_never_public():
    storage = FakeStorageBackend()
    svc = AssetService(storage)
    run(svc.put_kit(b"PK\x03\x04x"))
    url = run(svc.kit_signed_url(expires_in_seconds=300))
    assert "expires=" in url and url.startswith("fake://")
