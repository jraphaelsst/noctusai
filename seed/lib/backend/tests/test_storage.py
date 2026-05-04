"""Tests for `noctusai_lib.integrations.storage`.

Covers Fake + Local + Supabase backends through:
- A parametrized contract suite (put/get round-trip, delete, exists,
  list_keys with prefix filter, signed_url returns a string) running
  against Fake and Local. Supabase has its own dedicated tests with a
  mock client because its semantics around bucket existence differ.
- Edge cases: unicode keys, binary data, missing keys (None / False),
  signed_url respects expires_in_seconds.
- Supabase wire-call assertions: correct `from_(bucket).upload(...)`
  shape with the upsert option set; signed_url; download; remove; list.
- Factory routing.

Tests are network-free: Local uses `tmp_path`; Supabase uses
`unittest.mock.MagicMock` for the client (external-service carve-out
of the no-monkey-patching rule).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.storage import (
    BlobMetadata,
    FakeStorageBackend,
    LocalFilesystemStorageBackend,
    StorageBackend,
    StoredBlob,
    make_storage_backend,
)
from noctusai_lib.integrations.storage.supabase import (
    SupabaseStorageBackend,
    _is_not_found,
)


# ---- Backend fixtures (parametrized contract suite) -------------------------


@pytest.fixture
def fake_backend() -> StorageBackend:
    return FakeStorageBackend()


@pytest.fixture
def local_backend(tmp_path: Path) -> StorageBackend:
    return LocalFilesystemStorageBackend(tmp_path / "local-storage")


@pytest.fixture(params=["fake", "local"])
def backend(
    request: pytest.FixtureRequest,
    fake_backend: StorageBackend,
    local_backend: StorageBackend,
) -> StorageBackend:
    return {"fake": fake_backend, "local": local_backend}[request.param]


# ---- Contract: put / get round-trip -----------------------------------------


@pytest.mark.asyncio
async def test_put_get_round_trip(backend: StorageBackend) -> None:
    meta = await backend.put(
        bucket="docs",
        key="readme.txt",
        data=b"hello world",
        content_type="text/plain",
        metadata={"uploader": "user-42"},
    )

    assert isinstance(meta, BlobMetadata)
    assert meta.bucket == "docs"
    assert meta.key == "readme.txt"
    assert meta.size == len(b"hello world")
    assert meta.content_type == "text/plain"
    assert meta.custom_metadata == {"uploader": "user-42"}
    assert meta.created_at is not None

    blob = await backend.get(bucket="docs", key="readme.txt")
    assert blob is not None
    assert isinstance(blob, StoredBlob)
    assert blob.data == b"hello world"
    assert blob.metadata.bucket == "docs"
    assert blob.metadata.key == "readme.txt"
    assert blob.metadata.size == len(b"hello world")
    assert blob.metadata.content_type == "text/plain"
    assert blob.metadata.custom_metadata == {"uploader": "user-42"}


@pytest.mark.asyncio
async def test_put_overwrites_existing_key(backend: StorageBackend) -> None:
    await backend.put(bucket="b", key="k", data=b"v1")
    await backend.put(bucket="b", key="k", data=b"v2")
    blob = await backend.get(bucket="b", key="k")
    assert blob is not None
    assert blob.data == b"v2"


# ---- Contract: get on missing returns None ---------------------------------


@pytest.mark.asyncio
async def test_get_missing_returns_none(backend: StorageBackend) -> None:
    blob = await backend.get(bucket="docs", key="nope.txt")
    assert blob is None


# ---- Contract: delete -------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_existing_returns_true(backend: StorageBackend) -> None:
    await backend.put(bucket="b", key="k", data=b"x")
    assert await backend.delete(bucket="b", key="k") is True
    assert await backend.get(bucket="b", key="k") is None


@pytest.mark.asyncio
async def test_delete_missing_returns_false(backend: StorageBackend) -> None:
    assert await backend.delete(bucket="b", key="never") is False


# ---- Contract: exists -------------------------------------------------------


@pytest.mark.asyncio
async def test_exists(backend: StorageBackend) -> None:
    assert await backend.exists(bucket="b", key="k") is False
    await backend.put(bucket="b", key="k", data=b"x")
    assert await backend.exists(bucket="b", key="k") is True
    await backend.delete(bucket="b", key="k")
    assert await backend.exists(bucket="b", key="k") is False


# ---- Contract: list_keys + prefix filter ------------------------------------


@pytest.mark.asyncio
async def test_list_keys_prefix_filter(backend: StorageBackend) -> None:
    await backend.put(bucket="b", key="alpha/one.txt", data=b"1")
    await backend.put(bucket="b", key="alpha/two.txt", data=b"2")
    await backend.put(bucket="b", key="beta/three.txt", data=b"3")

    all_keys = await backend.list_keys(bucket="b")
    assert sorted(all_keys) == ["alpha/one.txt", "alpha/two.txt", "beta/three.txt"]

    alpha_keys = await backend.list_keys(bucket="b", prefix="alpha/")
    assert sorted(alpha_keys) == ["alpha/one.txt", "alpha/two.txt"]


@pytest.mark.asyncio
async def test_list_keys_respects_limit(backend: StorageBackend) -> None:
    for i in range(5):
        await backend.put(bucket="b", key=f"item-{i}.txt", data=b"x")
    keys = await backend.list_keys(bucket="b", limit=2)
    assert len(keys) == 2


@pytest.mark.asyncio
async def test_list_keys_empty_bucket(backend: StorageBackend) -> None:
    assert await backend.list_keys(bucket="never-touched") == []


# ---- Contract: signed_url ---------------------------------------------------


@pytest.mark.asyncio
async def test_signed_url_returns_string(backend: StorageBackend) -> None:
    await backend.put(bucket="b", key="k", data=b"x")
    url = await backend.signed_url(bucket="b", key="k")
    assert isinstance(url, str)
    assert url


@pytest.mark.asyncio
async def test_signed_url_reflects_expires_in(backend: StorageBackend) -> None:
    """For Fake + Local, the URL embeds the expiry timestamp so we can
    verify the requested TTL round-trips. (Supabase's URL is opaque and
    asserted via the mock-call shape elsewhere.)"""
    await backend.put(bucket="b", key="k", data=b"x")
    url_short = await backend.signed_url(bucket="b", key="k", expires_in_seconds=60)
    url_long = await backend.signed_url(bucket="b", key="k", expires_in_seconds=3600)

    # Both encode `expires=<int>`; long > short.
    short_ts = int(url_short.rsplit("=", 1)[1])
    long_ts = int(url_long.rsplit("=", 1)[1])
    # The longer expiry should produce a larger timestamp (allowing
    # equal in degenerate clock-tick conditions).
    assert long_ts >= short_ts + (3600 - 60) - 1


# ---- Edge cases: unicode keys, binary data ----------------------------------


@pytest.mark.asyncio
async def test_put_with_unicode_key(backend: StorageBackend) -> None:
    """Keys with emoji / accented characters round-trip cleanly."""
    key = "uploads/ação-relatório-📊.pdf"
    await backend.put(
        bucket="b",
        key=key,
        data=b"%PDF-1.4 unicode test",
        content_type="application/pdf",
    )
    blob = await backend.get(bucket="b", key=key)
    assert blob is not None
    assert blob.data == b"%PDF-1.4 unicode test"
    assert blob.metadata.key == key


@pytest.mark.asyncio
async def test_put_with_binary_data(backend: StorageBackend) -> None:
    """PNG-ish bytes (with high-bit characters) round-trip without corruption."""
    png_header = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    payload = png_header + b"\x00\xFF\x10" * 100
    await backend.put(
        bucket="b", key="img.png", data=payload, content_type="image/png"
    )
    blob = await backend.get(bucket="b", key="img.png")
    assert blob is not None
    assert blob.data == payload
    assert blob.metadata.content_type == "image/png"
    assert blob.metadata.size == len(payload)


@pytest.mark.asyncio
async def test_put_empty_blob_distinct_from_missing(backend: StorageBackend) -> None:
    """An intentionally empty blob is NOT the same as a missing one."""
    await backend.put(bucket="b", key="empty", data=b"")
    blob = await backend.get(bucket="b", key="empty")
    assert blob is not None
    assert blob.data == b""
    assert blob.metadata.size == 0


# ---- Local-specific: file:// URL + multi-bucket isolation ------------------


@pytest.mark.asyncio
async def test_local_signed_url_is_file_scheme(tmp_path: Path) -> None:
    backend = LocalFilesystemStorageBackend(tmp_path / "store")
    await backend.put(bucket="b", key="k", data=b"x")
    url = await backend.signed_url(bucket="b", key="k")
    assert url.startswith("file://")
    assert "expires=" in url


@pytest.mark.asyncio
async def test_local_buckets_are_isolated(tmp_path: Path) -> None:
    backend = LocalFilesystemStorageBackend(tmp_path / "store")
    await backend.put(bucket="b1", key="shared.txt", data=b"one")
    await backend.put(bucket="b2", key="shared.txt", data=b"two")

    blob1 = await backend.get(bucket="b1", key="shared.txt")
    blob2 = await backend.get(bucket="b2", key="shared.txt")
    assert blob1 is not None
    assert blob2 is not None
    assert blob1.data == b"one"
    assert blob2.data == b"two"


@pytest.mark.asyncio
async def test_local_persists_metadata_across_instances(tmp_path: Path) -> None:
    """A second LocalFilesystemStorageBackend pointed at the same root
    sees the previously-written metadata via the sidecar file."""
    root = tmp_path / "store"
    first = LocalFilesystemStorageBackend(root)
    await first.put(
        bucket="b",
        key="k",
        data=b"x",
        content_type="text/markdown",
        metadata={"foo": "bar"},
    )

    second = LocalFilesystemStorageBackend(root)
    blob = await second.get(bucket="b", key="k")
    assert blob is not None
    assert blob.metadata.content_type == "text/markdown"
    assert blob.metadata.custom_metadata == {"foo": "bar"}


# ---- Fake-specific: signed_url shape ----------------------------------------


@pytest.mark.asyncio
async def test_fake_signed_url_shape() -> None:
    backend = FakeStorageBackend()
    await backend.put(bucket="b", key="k", data=b"x")
    url = await backend.signed_url(bucket="b", key="k", expires_in_seconds=120)
    assert url.startswith("fake://storage/b/k?expires=")


# ---- SupabaseStorageBackend: mocked-client wire-call shape ------------------


def _mock_client_with_bucket() -> tuple[MagicMock, MagicMock]:
    """Return `(client_mock, bucket_proxy_mock)` so tests can pre-arm
    return values on the bucket proxy and assert calls."""
    bucket_proxy = MagicMock()
    client = MagicMock()
    client.storage.from_.return_value = bucket_proxy
    return client, bucket_proxy


@pytest.mark.asyncio
async def test_supabase_put_call_shape() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.upload.return_value = MagicMock()
    backend = SupabaseStorageBackend(client)

    meta = await backend.put(
        bucket="docs",
        key="hello.txt",
        data=b"hi",
        content_type="text/plain",
        metadata={"k": "v"},
    )

    client.storage.from_.assert_called_with("docs")
    bucket_proxy.upload.assert_called_once()
    pos_args = bucket_proxy.upload.call_args.args
    assert pos_args[0] == "hello.txt"
    assert pos_args[1] == b"hi"
    file_options = pos_args[2]
    assert file_options["content-type"] == "text/plain"
    # Upsert must be set so put overwrites existing keys per the contract.
    assert file_options.get("x-upsert") == "true"
    # Custom metadata is JSON-serialized.
    assert "metadata" in file_options
    assert '"k"' in file_options["metadata"]

    assert meta.bucket == "docs"
    assert meta.key == "hello.txt"
    assert meta.size == 2


@pytest.mark.asyncio
async def test_supabase_get_call_shape_returns_blob() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.download.return_value = b"payload"
    backend = SupabaseStorageBackend(client)

    blob = await backend.get(bucket="docs", key="x")
    assert blob is not None
    assert blob.data == b"payload"
    bucket_proxy.download.assert_called_once_with("x")


@pytest.mark.asyncio
async def test_supabase_get_translates_404_to_none() -> None:
    client, bucket_proxy = _mock_client_with_bucket()

    bucket_proxy.download.side_effect = Exception(
        {"statusCode": "404", "error": "not_found", "message": "Object not found"}
    )
    backend = SupabaseStorageBackend(client)
    assert await backend.get(bucket="docs", key="missing") is None


@pytest.mark.asyncio
async def test_supabase_delete_call_shape() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.remove.return_value = [{"name": "x"}]
    backend = SupabaseStorageBackend(client)

    assert await backend.delete(bucket="docs", key="x") is True
    bucket_proxy.remove.assert_called_once_with(["x"])


@pytest.mark.asyncio
async def test_supabase_delete_empty_result_returns_false() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.remove.return_value = []
    backend = SupabaseStorageBackend(client)
    assert await backend.delete(bucket="docs", key="missing") is False


@pytest.mark.asyncio
async def test_supabase_signed_url_returns_signedURL() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.create_signed_url.return_value = {
        "signedURL": "https://supabase.example/storage/v1/object/sign/docs/x?token=abc"
    }
    backend = SupabaseStorageBackend(client)

    url = await backend.signed_url(
        bucket="docs", key="x", expires_in_seconds=600
    )
    assert url.startswith("https://supabase.example/")
    bucket_proxy.create_signed_url.assert_called_once_with("x", 600)


@pytest.mark.asyncio
async def test_supabase_signed_url_unexpected_shape_raises() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.create_signed_url.return_value = {"weird": "shape"}
    backend = SupabaseStorageBackend(client)

    with pytest.raises(RuntimeError, match="Unexpected"):
        await backend.signed_url(bucket="docs", key="x")


@pytest.mark.asyncio
async def test_supabase_list_call_shape() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.list.return_value = [
        {"name": "alpha.txt"},
        {"name": "beta.txt"},
    ]
    backend = SupabaseStorageBackend(client)

    keys = await backend.list_keys(bucket="docs", prefix="", limit=50)
    assert sorted(keys) == ["alpha.txt", "beta.txt"]
    # Empty prefix → list bucket root (path=None).
    bucket_proxy.list.assert_called_once_with(None, {"limit": 50})


@pytest.mark.asyncio
async def test_supabase_list_with_nested_prefix() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.list.return_value = [
        {"name": "one.txt"},
        {"name": "two.txt"},
    ]
    backend = SupabaseStorageBackend(client)

    keys = await backend.list_keys(bucket="docs", prefix="folder/", limit=10)
    assert sorted(keys) == ["folder/one.txt", "folder/two.txt"]
    bucket_proxy.list.assert_called_once_with("folder", {"limit": 10})


@pytest.mark.asyncio
async def test_supabase_exists_true_when_listed() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.list.return_value = [{"name": "k"}]
    backend = SupabaseStorageBackend(client)
    assert await backend.exists(bucket="b", key="k") is True


@pytest.mark.asyncio
async def test_supabase_exists_false_when_not_listed() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.list.return_value = []
    backend = SupabaseStorageBackend(client)
    assert await backend.exists(bucket="b", key="k") is False


@pytest.mark.asyncio
async def test_supabase_put_failure_logs_and_raises() -> None:
    client, bucket_proxy = _mock_client_with_bucket()
    bucket_proxy.upload.side_effect = RuntimeError("network down")
    backend = SupabaseStorageBackend(client)

    with pytest.raises(RuntimeError, match="network down"):
        await backend.put(bucket="docs", key="x", data=b"x")


def test_supabase_is_not_found_heuristic() -> None:
    assert _is_not_found(Exception({"statusCode": "404"})) is True
    assert (
        _is_not_found(
            Exception(
                {
                    "statusCode": "400",
                    "error": "not_found",
                    "message": "Object not found",
                }
            )
        )
        is True
    )
    assert _is_not_found(Exception("Object not found in bucket")) is True
    assert _is_not_found(Exception({"statusCode": "500"})) is False
    assert _is_not_found(Exception("permission denied")) is False


# ---- Factory routing --------------------------------------------------------


def test_factory_fake() -> None:
    backend = make_storage_backend(kind="fake")
    assert isinstance(backend, FakeStorageBackend)


def test_factory_local_requires_root_dir() -> None:
    with pytest.raises(ValueError, match="root_dir"):
        make_storage_backend(kind="local")


def test_factory_local(tmp_path: Path) -> None:
    backend = make_storage_backend(kind="local", root_dir=tmp_path / "x")
    assert isinstance(backend, LocalFilesystemStorageBackend)


def test_factory_supabase_requires_client() -> None:
    with pytest.raises(ValueError, match="client"):
        make_storage_backend(kind="supabase")


def test_factory_supabase() -> None:
    client = MagicMock()
    backend = make_storage_backend(kind="supabase", client=client)
    assert isinstance(backend, SupabaseStorageBackend)


def test_factory_unsupported_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported storage backend kind"):
        make_storage_backend(kind="azure")  # type: ignore[arg-type]


# ---- Public surface — `from ... import` should expose the canonical set ----


def test_public_exports_match_canonical_shape() -> None:
    """Public exports mirror Protocol+Fake+Real+factory canonical shape."""
    from noctusai_lib.integrations import storage as storage_pkg

    expected = {
        "BlobMetadata",
        "FakeStorageBackend",
        "LocalFilesystemStorageBackend",
        "StorageBackend",
        "StoredBlob",
        "SupabaseStorageBackend",
        "make_storage_backend",
    }
    assert expected.issubset(set(storage_pkg.__all__))
    # Lazy attribute access works.
    assert storage_pkg.SupabaseStorageBackend is SupabaseStorageBackend
