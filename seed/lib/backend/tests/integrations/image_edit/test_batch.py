"""Batch ("Econômico") surface of the image_edit organ — Fake + OpenAI Real.

The Real adapter is exercised through its constructor-injected `client`
(a scripted double of `files` / `batches`), never a live call — the OpenAI
account had no credits when this was written. The error-classification
cases raise REAL `openai.*Error` instances from the double.
"""
from __future__ import annotations

import base64
import json
import types

import httpx
import openai
import pytest

from noctusai_lib.integrations.image_edit import (
    BatchEditItem,
    BatchState,
    FakeImageEditAdapter,
    ImageEditAdapter,
    ImageEditBatchNotFound,
    ImageEditBatchNotReady,
    ImageEditBatchUnsupported,
    ImageEditCapabilities,
    ImageEditContentPolicyViolation,
    ImageEditInvalidSize,
    ImageEditRateLimited,
    ImageEditRequest,
    ImageEditServerError,
    ImageEditTimeout,
    OpenAIImageEditAdapter,
)
from noctusai_lib.integrations.image_edit.openai_adapter import BATCH_ENDPOINT
from noctusai_lib.integrations.image_edit.types import BatchItemResult

MODEL = "gpt-image-batchy"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def _caps(model: str) -> ImageEditCapabilities:
    return ImageEditCapabilities(model=model, supports_batch=model == MODEL, known=True)


def _items(n: int = 2) -> list[BatchEditItem]:
    return [
        BatchEditItem(
            custom_id=f"foto-{i}:edicao-{i}",
            request=ImageEditRequest(images=(JPEG,), prompt=f"edit {i}", size="1024x1536"),
        )
        for i in range(n)
    ]


# ── value objects ─────────────────────────────────────────────────────


def test_batch_state_terminality() -> None:
    terminal = {s for s in BatchState if s.is_terminal}
    assert terminal == {
        BatchState.COMPLETED, BatchState.FAILED, BatchState.EXPIRED, BatchState.CANCELLED
    }


def test_item_result_needs_exactly_one_outcome() -> None:
    with pytest.raises(ValueError):
        BatchItemResult(custom_id="x")
    with pytest.raises(ValueError):
        BatchEditItem(custom_id="", request=_items(1)[0].request)


def test_both_adapters_satisfy_the_protocol() -> None:
    assert isinstance(FakeImageEditAdapter(), ImageEditAdapter)
    assert isinstance(OpenAIImageEditAdapter("k"), ImageEditAdapter)


# ── Fake ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_refuses_a_model_without_batch() -> None:
    fake = FakeImageEditAdapter(model="gpt-image-2.5-sunburst")  # catalog: no batch
    with pytest.raises(ImageEditBatchUnsupported):
        await fake.submit_batch(_items())


@pytest.mark.asyncio
async def test_fake_lifecycle_pending_then_completed() -> None:
    fake = FakeImageEditAdapter(model=MODEL, batch_models={MODEL}, batch_pending_polls=2)
    sub = await fake.submit_batch(_items(), org_id="o", metadata={"lote_id": "l"})
    assert (sub.item_count, sub.state, sub.model) == (2, BatchState.VALIDATING, MODEL)
    with pytest.raises(ImageEditBatchNotReady):
        await fake.fetch_batch_results(sub.batch_id)
    states = [(await fake.poll_batch(sub.batch_id)).state for _ in range(3)]
    assert states == [BatchState.IN_PROGRESS, BatchState.IN_PROGRESS, BatchState.COMPLETED]
    results = await fake.fetch_batch_results(sub.batch_id)
    assert [r.custom_id for r in results] == ["foto-0:edicao-0", "foto-1:edicao-1"]
    assert all(r.ok and r.result.usage.image_output_tokens == 100 for r in results)
    assert fake.batch_calls[0]["metadata"] == {"lote_id": "l"}


@pytest.mark.asyncio
async def test_fake_item_errors_and_forced_expiry() -> None:
    fake = FakeImageEditAdapter(
        model=MODEL,
        batch_models={MODEL},
        batch_item_errors={"foto-1:edicao-1": ImageEditContentPolicyViolation("nope")},
    )
    sub = await fake.submit_batch(_items())
    polled = await fake.poll_batch(sub.batch_id)
    assert (polled.completed, polled.failed) == (1, 1)
    ok, bad = await fake.fetch_batch_results(sub.batch_id)
    assert ok.ok and isinstance(bad.error, ImageEditContentPolicyViolation)

    other = await fake.submit_batch(_items(1))
    fake.set_batch_state(other.batch_id, BatchState.EXPIRED)
    assert (await fake.poll_batch(other.batch_id)).state is BatchState.EXPIRED
    (expired,) = await fake.fetch_batch_results(other.batch_id)
    assert isinstance(expired.error, ImageEditTimeout) and expired.error.retryable


@pytest.mark.asyncio
async def test_fake_unknown_batch_and_duplicate_ids() -> None:
    fake = FakeImageEditAdapter(model=MODEL, batch_models={MODEL})
    with pytest.raises(ImageEditBatchNotFound):
        await fake.poll_batch("nope")
    with pytest.raises(ValueError, match="duplicate"):
        await fake.submit_batch(_items(1) * 2)


# ── OpenAI Real, scripted client ──────────────────────────────────────


class _Files:
    def __init__(self, contents: dict[str, str]) -> None:
        self.contents = contents
        self.created: list[dict] = []

    async def create(self, *, file, purpose):
        self.created.append({"file": file, "purpose": purpose})
        return types.SimpleNamespace(id="file-in-1")

    async def content(self, file_id):
        return types.SimpleNamespace(text=self.contents[file_id])


class _Batches:
    def __init__(self, retrieve_script: list) -> None:
        self.retrieve_script = retrieve_script
        self.created: list[dict] = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return types.SimpleNamespace(id="batch_abc", status="validating")

    async def retrieve(self, batch_id):
        item = self.retrieve_script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Client:
    def __init__(self, *, retrieve_script=(), contents=None) -> None:
        self.files = _Files(dict(contents or {}))
        self.batches = _Batches(list(retrieve_script))


def _batch_obj(status: str, *, output=None, errors=None, total=2, completed=0, failed=0):
    return types.SimpleNamespace(
        status=status,
        output_file_id=output,
        error_file_id=errors,
        request_counts=types.SimpleNamespace(total=total, completed=completed, failed=failed),
    )


def _ok_line(custom_id: str, payload: bytes) -> str:
    return json.dumps({
        "id": "r1",
        "custom_id": custom_id,
        "response": {
            "status_code": 200,
            "request_id": "req-1",
            "body": {
                "data": [{"b64_json": base64.b64encode(payload).decode("ascii")}],
                "usage": {
                    "input_tokens": 1210,
                    "output_tokens": 4000,
                    "total_tokens": 5210,
                    "input_tokens_details": {"text_tokens": 10, "image_tokens": 1200},
                },
            },
        },
        "error": None,
    })


def _err_line(custom_id: str, status: int | None, code: str, message: str) -> str:
    response = None
    if status is not None:
        response = {"status_code": status, "body": {"error": {"code": code, "message": message}}}
    return json.dumps({
        "custom_id": custom_id,
        "response": response,
        "error": None if status is not None else {"code": code, "message": message},
    })


def _adapter(client) -> OpenAIImageEditAdapter:
    return OpenAIImageEditAdapter("key", model=MODEL, client=client, capabilities=_caps)


@pytest.mark.asyncio
async def test_real_refuses_without_batch_capability_before_any_call() -> None:
    client = _Client()
    adapter = OpenAIImageEditAdapter("key", model="gpt-image-2.5-sunburst", client=client)
    with pytest.raises(ImageEditBatchUnsupported):
        await adapter.submit_batch(_items())
    assert client.files.created == [] and client.batches.created == []


@pytest.mark.asyncio
async def test_real_submit_uploads_jsonl_and_creates_the_batch() -> None:
    client = _Client()
    sub = await _adapter(client).submit_batch(_items(), org_id="o", metadata={"lote_id": "l"})
    assert (sub.batch_id, sub.state, sub.item_count, sub.input_file_id) == (
        "batch_abc", BatchState.VALIDATING, 2, "file-in-1"
    )
    (upload,) = client.files.created
    assert upload["purpose"] == "batch"
    name, data, mime = upload["file"]
    assert (name, mime) == ("batch.jsonl", "application/jsonl")
    lines = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    assert [line["custom_id"] for line in lines] == ["foto-0:edicao-0", "foto-1:edicao-1"]
    first = lines[0]
    assert (first["method"], first["url"]) == ("POST", BATCH_ENDPOINT)
    body = first["body"]
    assert (body["model"], body["prompt"], body["size"], body["n"]) == (
        MODEL, "edit 0", "1024x1536", 1
    )
    expected = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode("ascii")
    assert body["images"] == [{"image_url": expected}]
    (created,) = client.batches.created
    assert created == {
        "input_file_id": "file-in-1",
        "endpoint": BATCH_ENDPOINT,
        "completion_window": "24h",
        "metadata": {"lote_id": "l"},
    }


@pytest.mark.asyncio
async def test_real_poll_maps_status_and_counts() -> None:
    client = _Client(retrieve_script=[_batch_obj("in_progress", completed=1)])
    polled = await _adapter(client).poll_batch("batch_abc")
    assert (polled.state, polled.total, polled.completed, polled.failed) == (
        BatchState.IN_PROGRESS, 2, 1, 0
    )


@pytest.mark.asyncio
async def test_real_poll_unknown_status_is_loud() -> None:
    client = _Client(retrieve_script=[_batch_obj("teleporting")])
    with pytest.raises(ImageEditServerError, match="unknown batch status"):
        await _adapter(client).poll_batch("batch_abc")


@pytest.mark.asyncio
async def test_real_fetch_before_terminal_is_not_ready() -> None:
    client = _Client(retrieve_script=[_batch_obj("finalizing")])
    with pytest.raises(ImageEditBatchNotReady):
        await _adapter(client).fetch_batch_results("batch_abc")


@pytest.mark.asyncio
async def test_real_fetch_parses_output_and_error_files() -> None:
    output = "\n".join([_ok_line("a", b"edited-a"), _err_line("b", 400, "moderation_blocked",
                                                               "Rejected by the safety system")])
    errors = "\n".join([
        _err_line("c", 429, "rate_limit_exceeded", "slow down"),
        _err_line("d", 500, "server_error", "boom"),
        _err_line("e", 400, "invalid_size", "size not allowed"),
        _err_line("f", None, "batch_expired", "This request could not be executed"),
    ]) + "\n"
    client = _Client(
        retrieve_script=[_batch_obj("expired", output="out-1", errors="err-1")],
        contents={"out-1": output, "err-1": errors},
    )
    results = {r.custom_id: r for r in await _adapter(client).fetch_batch_results("batch_abc")}
    assert set(results) == {"a", "b", "c", "d", "e", "f"}
    ok = results["a"].result
    assert ok.images[0].image_bytes == b"edited-a" and ok.model == MODEL
    assert (ok.usage.prompt_tokens, ok.usage.image_input_tokens,
            ok.usage.image_output_tokens, ok.usage.total_tokens) == (10, 1200, 4000, 5210)
    assert ok.raw["batch_id"] == "batch_abc"
    assert isinstance(results["b"].error, ImageEditContentPolicyViolation)
    assert isinstance(results["c"].error, ImageEditRateLimited)
    assert isinstance(results["d"].error, ImageEditServerError)
    assert isinstance(results["e"].error, ImageEditInvalidSize)
    assert isinstance(results["f"].error, ImageEditTimeout) and results["f"].error.retryable


@pytest.mark.asyncio
async def test_real_fetch_expired_without_files_returns_nothing() -> None:
    client = _Client(retrieve_script=[_batch_obj("expired")])
    assert await _adapter(client).fetch_batch_results("batch_abc") == ()


def _http(status: int) -> httpx.Response:
    request = httpx.Request("GET", "https://api.openai.com/v1/batches/batch_abc")
    return httpx.Response(status, request=request, json={})


@pytest.mark.asyncio
async def test_real_sdk_errors_are_classified() -> None:
    not_found = openai.NotFoundError("gone", response=_http(404), body=None)
    limited = openai.RateLimitError("slow", response=_http(429), body=None)
    client = _Client(retrieve_script=[not_found, limited])
    adapter = _adapter(client)
    with pytest.raises(ImageEditBatchNotFound):
        await adapter.poll_batch("batch_abc")
    with pytest.raises(ImageEditRateLimited):
        await adapter.poll_batch("batch_abc")
