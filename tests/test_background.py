"""Verify API waits release the state lock and duplicate tasks are rejected."""

import asyncio
import threading
from unittest.mock import AsyncMock

import pytest
from llama_index.core.base.response.schema import AsyncStreamingResponse
from reflex.istate.proxy import StateProxy
from reflex_base.event.context import EventContext

from docs_chat import rag
from docs_chat.state import State


class BackgroundProxy(StateProxy):
    """Use Reflex's mutation guards with a local session lock in unit tests."""

    def __init__(self, state):
        with EventContext(token="test", state_manager=None, enqueue_impl=AsyncMock()):
            super().__init__(state)
        self._self_lock = asyncio.Lock()
        self._self_updates = []

    async def __aenter__(self):
        await self._self_lock.acquire()
        self._self_mutable = True
        return self

    async def __aexit__(self, *exc):
        self._self_updates.append(
            (self.busy, self.status, self.turns[-1]["answer"] if self.turns else "")
        )
        self._self_mutable = False
        self._self_lock.release()


@pytest.mark.parametrize("handler", [State.ask, State.prepare_index])
def test_api_events_are_background_tasks(handler):
    """The framework must dispatch API events without a session lock."""
    assert handler.is_background


async def test_pending_answer_allows_input_and_rejects_duplicate_tasks(monkeypatch):
    """Both retrieval and token waits leave other session events responsive."""
    state = State(_reflex_internal_init=True)
    proxy = BackgroundProxy(state)
    started = asyncio.Event()
    release = asyncio.Event()
    streaming = asyncio.Event()
    finish = asyncio.Event()
    calls = []

    async def answer(question, history):
        assert not proxy._self_lock.locked()
        calls.append(question)
        started.set()
        await release.wait()

        async def tokens():
            assert not proxy._self_lock.locked()
            yield "First"
            streaming.set()
            await finish.wait()
            assert not proxy._self_lock.locked()
            yield " second"

        return AsyncStreamingResponse(response_gen=tokens())

    monkeypatch.setattr(rag, "setup_problem", lambda: "")
    monkeypatch.setattr(rag, "answer", answer)
    task = asyncio.create_task(State.ask.fn(proxy, {"question": "Hello"}))
    try:
        await asyncio.wait_for(started.wait(), 2)
        async with asyncio.timeout(2), proxy:
            State.set_question.fn(proxy, "Next question")
            State.clear_chat.fn(proxy)
            assert len(proxy.turns) == 1
        await State.ask.fn(proxy, {"question": "Duplicate"})
        release.set()
        await asyncio.wait_for(streaming.wait(), 2)
        async with asyncio.timeout(2), proxy:
            State.set_citation_open.fn(proxy, False)
        finish.set()
        await asyncio.wait_for(task, 2)
    finally:
        release.set()
        finish.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert calls == ["Hello"]
    assert state.turns[0]["answer"] == "First second"
    assert state.turns[0]["complete"]
    assert not state.busy


async def test_indexing_releases_session_lock(monkeypatch):
    """Indexing in a worker thread does not block ordinary session updates."""
    state = State(_reflex_internal_init=True)
    proxy = BackgroundProxy(state)
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    ready = False
    calls = []

    def build():
        nonlocal ready
        assert not proxy._self_lock.locked()
        calls.append(True)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)
        ready = True

    monkeypatch.setattr(rag, "build_index", build)
    monkeypatch.setattr(rag, "setting", lambda *args: "test-key")
    monkeypatch.setattr(rag, "setup_problem", lambda: "" if ready else "Missing index")
    task = asyncio.create_task(State.prepare_index.fn(proxy))
    try:
        await asyncio.wait_for(started.wait(), 2)
        async with asyncio.timeout(2), proxy:
            State.set_question.fn(proxy, "Still responsive")
        await State.prepare_index.fn(proxy)
        release.set()
        await asyncio.wait_for(task, 2)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert calls == [True]
    assert state.question == "Still responsive"
    assert state.setup == ""
    assert not state.busy
