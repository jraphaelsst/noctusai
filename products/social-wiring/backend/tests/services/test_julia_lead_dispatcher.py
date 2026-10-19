"""LeadTurnDispatcher: a slow lead turn never blocks the operator path, leads of different
chats overlap (bounded), one chat stays serial, shutdown drains / cancels. Event-driven --
no sleeps decide any outcome."""
from __future__ import annotations

import asyncio
import threading

from noctusai_lib.domain.chatbot import ConversationBufferService, ConversationWorker
from noctusai_lib.domain.chatbot.buffer import make_in_memory_buffer_client

from app.services.julia_lead_dispatcher import LeadTurnDispatcher

K1, K2, K3 = "lead:c1:chat1", "lead:c1:chat2", "lead:c1:chat3"


def _run(coro):
    return asyncio.run(coro)


class TestConcurrency:
    def test_different_chats_overlap(self):
        async def go():
            started = {K1: asyncio.Event(), K2: asyncio.Event()}
            release = asyncio.Event()

            async def runner(key, memory):
                started[key].set()
                await release.wait()

            d = LeadTurnDispatcher(runner, max_concurrent=4)
            d.submit(K1, [])
            d.submit(K2, [])
            await asyncio.wait_for(asyncio.gather(started[K1].wait(), started[K2].wait()), 5)
            assert d.in_flight == 2
            release.set()
            await d.shutdown(5)

        _run(go())

    def test_bound_is_respected(self):
        async def go():
            running = 0
            peak = 0
            first_two = asyncio.Event()
            release = asyncio.Event()
            done: list[str] = []

            async def runner(key, memory):
                nonlocal running, peak
                running += 1
                peak = max(peak, running)
                if running == 2:
                    first_two.set()
                await release.wait()
                running -= 1
                done.append(key)

            d = LeadTurnDispatcher(runner, max_concurrent=2)
            for k in (K1, K2, K3):
                d.submit(k, [])
            await asyncio.wait_for(first_two.wait(), 5)
            await asyncio.sleep(0)  # let the third reach the semaphore
            assert peak == 2 and running == 2
            release.set()
            await d.shutdown(5)
            assert sorted(done) == [K1, K2, K3] and peak == 2

        _run(go())

    def test_same_chat_is_serial_and_ordered(self):
        async def go():
            order: list[str] = []
            gate = asyncio.Event()
            first_started = asyncio.Event()
            active = 0
            overlap = False

            async def runner(key, memory):
                nonlocal active, overlap
                active += 1
                overlap = overlap or active > 1
                tag = memory[0]
                order.append(f"start-{tag}")
                if tag == "a":
                    first_started.set()
                    await gate.wait()
                order.append(f"end-{tag}")
                active -= 1

            d = LeadTurnDispatcher(runner, max_concurrent=4)
            d.submit(K1, ["a"])
            await first_started.wait()
            d.submit(K1, ["b"])
            await asyncio.sleep(0)
            assert order == ["start-a"]  # b is waiting on the key lock, not running
            gate.set()
            await d.shutdown(5)
            assert order == ["start-a", "end-a", "start-b", "end-b"] and not overlap

        _run(go())

    def test_queued_turn_rereads_memory_under_the_lock(self):
        async def go():
            seen: list[object] = []
            gate = asyncio.Event()
            started = asyncio.Event()

            async def runner(key, memory):
                seen.append(memory)
                started.set()
                await gate.wait()

            d = LeadTurnDispatcher(runner, max_concurrent=2, reload_memory=lambda k: ["fresh"])
            d.submit(K1, ["stale1"])
            await started.wait()
            d.submit(K1, ["stale2"])
            gate.set()
            await d.shutdown(5)
            assert seen == [["fresh"], ["fresh"]]

        _run(go())

    def test_failure_is_contained_and_lock_released(self):
        async def go():
            calls: list[str] = []

            async def runner(key, memory):
                calls.append(key)
                if len(calls) == 1:
                    raise RuntimeError("boom")

            d = LeadTurnDispatcher(runner)
            d.submit(K1, [])
            d.submit(K1, [])
            await d.shutdown(5)
            assert calls == [K1, K1] and not d._locks and not d._pending

        _run(go())


class TestShutdown:
    def test_drains_inflight_within_grace(self):
        async def go():
            finished = asyncio.Event()
            started = asyncio.Event()

            async def runner(key, memory):
                started.set()
                await asyncio.sleep(0)
                finished.set()

            d = LeadTurnDispatcher(runner)
            d.submit(K1, [])
            await started.wait()
            await d.shutdown(5)
            assert finished.is_set()
            assert d.submit(K2, []) is None  # closed

        _run(go())

    def test_cancels_a_stuck_turn_after_grace(self):
        async def go():
            started = asyncio.Event()
            cancelled = asyncio.Event()

            async def runner(key, memory):
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

            d = LeadTurnDispatcher(runner)
            d.submit(K1, [])
            await started.wait()
            await d.shutdown(0.01)
            assert cancelled.is_set() and d.in_flight == 0

        _run(go())


class TestOperatorNotBlockedByLead:
    def test_operator_batch_completes_while_a_lead_turn_is_blocked(self):
        """The REAL ConversationWorker: a lead key and an operator key are both due; the
        lead turn blocks on an event the operator processor sets once it has run."""
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            buf = ConversationBufferService(redis_client=make_in_memory_buffer_client())
            lead_started = threading.Event()
            operator_done = threading.Event()
            lead_finished = threading.Event()

            async def lead_run(key, memory):
                lead_started.set()
                # blocked until the operator batch has completed
                await asyncio.get_running_loop().run_in_executor(None, operator_done.wait, 10)
                lead_finished.set()

            d = LeadTurnDispatcher(lead_run, max_concurrent=4)

            def processor(conversation_id, memory):
                if conversation_id.startswith("lead:"):
                    d.submit_threadsafe(loop, conversation_id, memory)
                    return
                assert lead_started.wait(5), "lead must be in flight first"
                operator_done.set()

            # lead first (lower score), so the operator batch is queued BEHIND it
            for score, cid in enumerate(("lead:c1:chatX", "+5511999990000")):
                buf.append_to_memory(_msg(cid))
                buf.redis.zadd(buf.due_set_key, {cid: score})
            worker = ConversationWorker(buffer_service=buf, processor=processor)
            t = threading.Thread(target=worker.process_due_once)
            t.start()
            t.join(10)
            assert not t.is_alive() and operator_done.is_set()
            assert lead_finished.wait(10)
            asyncio.run_coroutine_threadsafe(d.shutdown(5), loop).result(10)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(5)
            loop.close()


def _msg(cid):
    from noctusai_lib.domain.chatbot.buffer import QueuedConversationMessage

    return QueuedConversationMessage(conversation_id=cid, text="oi", direction="inbound", provider_message_id="m1")
