"""Exercise streaming, evidence, failed requests, and user isolation offline."""

import json

import pytest
from llama_index.core.base.response.schema import AsyncStreamingResponse
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM
from llama_index.core.schema import NodeWithScore, TextNode
from test_background import BackgroundProxy

from docs_chat import rag
from docs_chat.state import State


async def test_setup_check_reports_result_when_nothing_changed(monkeypatch):
    """Rechecking missing setup gives feedback even when the warning is unchanged."""
    monkeypatch.setattr(rag, "setup_problem", lambda: "Build the document index")
    state = new_state()
    state.setup = "Build the document index"
    updates = []
    async for _ in State.check_setup.fn(state):
        updates.append(state.setup_feedback)
    assert updates == ["Checking local setup…"]
    assert state.setup_feedback == "Checked. Build the document index"


async def test_index_button_builds_and_clears_setup(monkeypatch):
    """Building yields progress and clears the warning after a successful index."""
    ready = False

    def build():
        nonlocal ready
        ready = True
        return 4

    monkeypatch.setattr(rag, "build_index", build)
    monkeypatch.setattr(rag, "setting", lambda name, default="": "test-key")
    monkeypatch.setattr(rag, "setup_problem", lambda: "" if ready else "Missing index")
    state = new_state()
    proxy = BackgroundProxy(state)
    await State.prepare_index.fn(proxy)
    assert proxy._self_updates[0][:2] == (True, "Building the documentation index…")
    assert ready
    assert not state.busy
    assert not state.setup
    assert state.setup_feedback == "Index ready. You can now ask a question."


async def test_index_credit_error_is_actionable_and_retryable(monkeypatch):
    """Failed indexing exposes no provider details and can be retried."""
    import httpx
    from openai import RateLimitError

    def failed():
        raise RateLimitError(
            "sensitive-provider-details",
            response=httpx.Response(
                429, request=httpx.Request("POST", "https://example.com")
            ),
            body={"code": "credit_balance_exhausted"},
        )

    monkeypatch.setattr(rag, "build_index", failed)
    monkeypatch.setattr(rag, "setting", lambda name, default="": "test-key")
    monkeypatch.setattr(rag, "setup_problem", lambda: "Missing index")
    state = new_state()
    await State.prepare_index.fn(BackgroundProxy(state))
    assert not state.busy
    assert state.setup == "Missing index"
    assert "credits" in state.error
    assert "sensitive-provider-details" not in state.error


def new_state():
    """Create a state instance without starting a web server."""
    return State(_reflex_internal_init=True)


async def drain(state, question):
    """Consume a Reflex event and capture the state after each streamed update."""
    proxy = BackgroundProxy(state)
    await State.ask.fn(proxy, {"question": question})
    return [answer for _, _, answer in proxy._self_updates]


async def test_streaming_sources_and_isolated_history(monkeypatch):
    """Each session sees its own completed conversation and source numbers."""
    monkeypatch.setattr(rag, "setup_problem", lambda: "")
    histories = []

    async def answer(question, history):
        histories.append(list(history))

        async def tokens():
            yield "Five days"
            yield " [1]."

        return AsyncStreamingResponse(
            response_gen=tokens(),
            source_nodes=[
                NodeWithScore(
                    node=TextNode(
                        text="Source 1: Five days carry over.",
                        metadata={
                            "file_name": "time-off.md",
                            "title": "Test page",
                            "source_url": "https://reflex.dev/docs/state/overview/",
                        },
                    )
                )
            ],
        )

    monkeypatch.setattr(rag, "answer", answer)
    alice, bob = new_state(), new_state()
    snapshots = await drain(alice, "How much can I carry over?")
    assert "Five days" in snapshots
    assert alice.turns[0]["answer"] == "Five days [1]."
    assert alice.turns[0]["answer_markdown"] == "Five days [1](#source-0-1)."
    State.open_citation.fn(alice, "#source-0-1")
    assert alice.citation_open
    assert alice.selected_source["title"] == "Test page"
    assert alice.selected_source["number"] == "1"
    State.open_citation.fn(bob, "#source-0-1")
    assert not bob.citation_open
    State.set_citation_open.fn(alice, False)
    assert not alice.citation_open
    assert alice.turns[0]["sources"][0]["number"] == 1
    assert alice.turns[0]["sources"][0]["filename"] == "time-off.md"
    assert (
        alice.turns[0]["sources"][0]["url"] == "https://reflex.dev/docs/state/overview/"
    )
    assert alice.turns[0]["complete"]
    assert not alice.busy
    await drain(alice, "When does it expire?")
    await drain(bob, "What is the vacation allowance?")
    assert histories == [[], [("How much can I carry over?", "Five days [1].")], []]
    State.clear_chat.fn(alice)
    assert not alice.turns
    assert len(bob.turns) == 1


async def test_interrupted_stream_recovers_without_reusing_partial_answer(monkeypatch):
    """A failed provider stream releases busy state and keeps partial text out of history."""
    monkeypatch.setattr(rag, "setup_problem", lambda: "")

    async def broken(question, history):
        async def tokens():
            yield "Partial answer"
            raise TimeoutError("provider timed out")

        return AsyncStreamingResponse(response_gen=tokens())

    monkeypatch.setattr(rag, "answer", broken)
    state = new_state()
    await drain(state, "First question")
    assert not state.busy
    assert state.status == ""
    assert state.error
    assert not state.turns[-1]["complete"]

    async def recovered(question, history):
        assert history == []

        async def tokens():
            yield "Recovered"

        return AsyncStreamingResponse(response_gen=tokens())

    monkeypatch.setattr(rag, "answer", recovered)
    await drain(state, "Try again")
    assert state.turns[-1]["complete"]
    assert state.error == ""


@pytest.mark.parametrize("question", ["   ", "x" * 2001])
async def test_invalid_input_never_calls_provider(question, monkeypatch):
    """Reject invalid questions before indexing or generation."""

    def unexpected():
        pytest.fail("Provider setup should not be reached")

    monkeypatch.setattr(rag, "setup_problem", unexpected)
    state = new_state()
    await drain(state, question)
    assert state.error
    assert not state.turns


async def test_setup_and_busy_guards(monkeypatch):
    """A missing setup or duplicate submission cannot add a conversation turn."""
    monkeypatch.setattr(rag, "setup_problem", lambda: "Missing key")
    state = new_state()
    await drain(state, "Hello")
    assert state.setup == "Missing key"
    assert not state.turns
    state.busy = True
    await drain(state, "Hello again")
    assert not state.turns


async def test_real_llamaindex_index_retrieval_and_streaming_with_test_models(
    tmp_path, monkeypatch
):
    """Run real LlamaIndex persistence, retrieval, citation numbering, and streaming offline."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "vacation.md").write_text(
        "Employees can carry over five vacation days until March 31."
    )
    (data / "sources.json").write_text(
        json.dumps(
            {
                "vacation.md": {
                    "title": "Test document",
                    "source_url": "https://reflex.dev/docs/state/overview/",
                    "fetched_at": "2026-10-19",
                }
            }
        )
    )
    monkeypatch.setattr(rag, "DATA", data)
    monkeypatch.setattr(rag, "STORAGE", tmp_path / "storage")
    monkeypatch.setattr(
        rag,
        "setting",
        lambda name, default="": "test-key" if name == "OPENAI_API_KEY" else default,
    )
    monkeypatch.setattr(rag, "embedding_model", lambda: MockEmbedding(embed_dim=8))
    monkeypatch.setattr(rag, "OpenAI", lambda **kwargs: MockLLM())
    rag.get_index.cache_clear()
    try:
        assert rag.build_index() == 1
        assert rag.setup_problem() == ""
        response = await rag.answer("What is the carry-over policy?", [])
        tokens = [token async for token in response.async_response_gen()]
        assert len(tokens) > 1
        assert "five vacation days" in "".join(tokens)
        assert response.source_nodes[0].node.metadata["file_name"] == "vacation.md"
        assert (
            response.source_nodes[0].node.metadata["source_url"]
            == "https://reflex.dev/docs/state/overview/"
        )
        assert response.source_nodes[0].node.get_content().startswith("Source 1:")
        (data / "vacation.md").write_text("A changed policy.")
        assert "Build the document index" in rag.setup_problem()
    finally:
        rag.get_index.cache_clear()


async def test_luna_stream_and_followup_send_supported_api_parameters(monkeypatch):
    """Exercise the real client serializer for streaming and follow-up requests."""
    import httpx
    from llama_index.llms.openai import OpenAI

    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == "gpt-6-luna"
        assert payload["reasoning_effort"] == "none"
        assert payload["max_completion_tokens"] == 700
        assert "max_tokens" not in payload
        if payload.get("stream"):
            chunk = {
                "id": "test-stream",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-6-luna",
                "choices": [{"index": 0, "delta": {"content": "Use a form [1]."}}],
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                "id": "test-rewrite",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "How do Reflex forms submit?",
                        },
                    }
                ],
            },
        )

    class Engine:
        async def aquery(self, question):
            return await self.llm.astream_complete(question)

    def engine_from_args(index, *, llm, **kwargs):
        engine = Engine()
        engine.llm = llm
        return engine

    monkeypatch.setattr(rag, "setup_problem", lambda: "")
    monkeypatch.setattr(rag, "corpus_fingerprint", lambda: "test")
    monkeypatch.setattr(rag, "get_index", lambda _: None)
    monkeypatch.setattr(
        rag,
        "setting",
        lambda name, default="": "test-key" if name == "OPENAI_API_KEY" else default,
    )
    monkeypatch.setattr(rag.CitationQueryEngine, "from_args", engine_from_args)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            rag, "OpenAI", lambda **kwargs: OpenAI(**kwargs, async_http_client=client)
        )
        for history in ([], [("What handles inputs?", "A form [1].")]):
            stream = await rag.answer("How does it submit?", history)
            assert "".join([part.delta async for part in stream]) == "Use a form [1]."
    assert [request.get("stream", False) for request in requests] == [True, False, True]
