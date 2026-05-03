"""Shared FakeRedis fixture for conversation tests.

Implements the `RedisBufferClient` Protocol with in-memory state.
Reused across `test_buffer.py` (Phase 3) and `test_worker.py` (Phase 4).
Mirrors the sibling test fixture at
`whatsapp-google-scheduling/tests/test_conversation_buffer_service.py:FakeRedis`.
"""

from __future__ import annotations

import pytest


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.expirations: dict[str, int] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.next_stream_id = 1

    def rpush(self, name: str, *values: str) -> int:
        self.lists.setdefault(name, []).extend(values)
        return len(self.lists[name])

    def ltrim(self, name: str, start: int, end: int) -> bool:
        items = self.lists.get(name, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        self.lists[name] = items[start : end + 1]
        return True

    def expire(self, name: str, time: int) -> bool:
        self.expirations[name] = time
        return True

    def delete(self, *names: str) -> int:
        removed = 0
        for name in names:
            if name in self.lists:
                del self.lists[name]
                removed += 1
            self.expirations.pop(name, None)
        return removed

    def lrange(self, name: str, start: int, end: int) -> list[str]:
        items = self.lists.get(name, [])
        if end == -1:
            end = len(items) - 1
        return items[start : end + 1]

    def xadd(
        self,
        name: str,
        fields: dict[str, str],
        id: str = "*",
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        stream_id = f"{self.next_stream_id}-0"
        self.next_stream_id += 1
        stream = self.streams.setdefault(name, [])
        stream.append((stream_id, fields))
        if maxlen is not None and len(stream) > maxlen:
            del stream[: len(stream) - maxlen]
        return stream_id

    def zadd(self, name: str, mapping: dict[str, float]) -> int:
        self.sorted_sets.setdefault(name, {}).update(mapping)
        return len(mapping)

    def zrangebyscore(
        self,
        name: str,
        min: float | str,
        max: float | str,
        start: int | None = None,
        num: int | None = None,
    ) -> list[str]:
        minimum = float("-inf") if min == "-inf" else float(min)
        maximum = float("inf") if max == "+inf" else float(max)
        values = [
            value
            for value, score in sorted(
                self.sorted_sets.get(name, {}).items(), key=lambda item: item[1]
            )
            if minimum <= score <= maximum
        ]
        if start is not None and num is not None:
            return values[start : start + num]
        return values

    def zrem(self, name: str, *values: str) -> int:
        sorted_set = self.sorted_sets.get(name, {})
        removed = 0
        for value in values:
            if value in sorted_set:
                del sorted_set[value]
                removed += 1
        return removed

    def zscore(self, name: str, value: str) -> float | None:
        return self.sorted_sets.get(name, {}).get(value)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
