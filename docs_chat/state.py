"""Keep each browser session's conversation separate."""

import asyncio
import logging
from typing import TypedDict

import reflex as rx
from openai import AuthenticationError, RateLimitError

from docs_chat import rag
from docs_chat.citations import excerpt_preview, link_citations

logger = logging.getLogger(__name__)
_index_build_lock = asyncio.Lock()


class Source(TypedDict):
    number: int
    filename: str
    title: str
    url: str
    excerpt: str


class Turn(TypedDict):
    question: str
    answer: str
    answer_markdown: str
    sources: list[Source]
    complete: bool


class State(rx.State):
    """Conversation and progress for one connected user."""

    question: str = ""
    turns: list[Turn] = []
    busy: bool = False
    status: str = ""
    error: str = ""
    setup: str = ""
    setup_feedback: str = ""
    citation_open: bool = False
    selected_source: dict[str, str] = {}

    @rx.var
    def citation_lookup(self) -> dict[str, dict[str, str]]:
        """Map each citation to the source from its own conversation turn."""
        return {
            f"#source-{turn_index}-{source['number']}": {
                "title": source["title"],
                "number": str(source["number"]),
                "url": source["url"],
                "excerpt": source["excerpt"].removeprefix(
                    f"Source {source['number']}:\n"
                ),
                "preview": excerpt_preview(source["excerpt"]),
            }
            for turn_index, turn in enumerate(self.turns)
            for source in turn["sources"]
        }

    @rx.event
    def open_citation(self, reference: str):
        """Open only a known citation from this browser session."""
        if reference in self.citation_lookup:
            self.selected_source = self.citation_lookup[reference]
            self.citation_open = True

    @rx.event
    def set_citation_open(self, value: bool):
        """Handle closing by button, Escape, or outside click."""
        self.citation_open = value

    @rx.event
    def load_setup(self):
        """Read local setup when the page opens."""
        self.setup = rag.setup_problem()

    @rx.event
    async def check_setup(self):
        """Show the result even when the local setup has not changed."""
        if self.busy:
            return
        self.setup_feedback = "Checking local setup…"
        yield
        self.setup = rag.setup_problem()
        self.setup_feedback = (
            f"Checked. {self.setup}" if self.setup else "Setup ready. Ask a question."
        )

    @rx.event(background=True)
    async def prepare_index(self):
        """Build the shared public documentation index and report provider errors."""
        async with self:
            if self.busy:
                return
            self.setup = rag.setup_problem()
            if not rag.setting("OPENAI_API_KEY"):
                self.setup_feedback = self.setup
                return
            self.busy = True
            self.error = self.setup_feedback = ""
            self.status = "Building the documentation index…"
        error = ""
        try:
            async with _index_build_lock:
                if rag.setup_problem():
                    await asyncio.to_thread(rag.build_index)
            async with self:
                self.setup = rag.setup_problem()
                self.setup_feedback = (
                    self.setup or "Index ready. You can now ask a question."
                )
        except RateLimitError as exc:
            if exc.code in {"credit_balance_exhausted", "insufficient_quota"}:
                error = (
                    "OpenAI API credits are exhausted. Add API credits or set a funded "
                    "OPENAI_API_KEY in .env, then click Build / retry index."
                )
            else:
                error = "OpenAI rate limit reached. Wait a moment, then click Build / retry index."
        except AuthenticationError:
            error = "OpenAI rejected the key. Update OPENAI_API_KEY in .env, then click Build / retry index."
        except Exception as exc:
            logger.warning("Indexing failed (%s)", type(exc).__name__)
            error = "Indexing failed. Check your connection and local setup, then click Build / retry index."
        finally:
            async with self:
                self.error = error
                self.busy = False
                self.status = ""

    @rx.event
    def set_question(self, value: str):
        """Update the question input."""
        self.question = value

    @rx.event
    def clear_chat(self):
        """Clear this conversation when no answer is being generated."""
        if not self.busy:
            self.turns = []
            self.citation_open = False
            self.selected_source = {}
            self.error = self.question = ""

    @rx.event(background=True)
    async def ask(self, form_data: dict):
        """Stream a response and preserve only completed turns as chat context."""
        async with self:
            if self.busy:
                return
            question = form_data.get("question", "").strip()
            if not question or len(question) > 2000:
                self.error = "Enter a question between 1 and 2,000 characters."
                return
            self.setup = rag.setup_problem()
            if self.setup:
                return
            history = [
                (t["question"], t["answer"]) for t in self.turns if t["complete"]
            ]
            self.turns.append(
                {
                    "question": question,
                    "answer": "",
                    "answer_markdown": "",
                    "sources": [],
                    "complete": False,
                }
            )
            self.question = self.error = ""
            self.busy = True
            self.status = "Finding relevant passages…"
        try:
            response = await rag.answer(question, history)
            sources = [
                {
                    "number": i,
                    "filename": source.node.metadata.get("file_name", "Document"),
                    "title": source.node.metadata.get("title", "Documentation"),
                    "url": source.node.metadata.get("source_url", ""),
                    "excerpt": source.node.get_content(),
                }
                for i, source in enumerate(response.source_nodes, start=1)
            ]
            async with self:
                self.turns[-1]["sources"] = sources
                self.status = "Writing an answer…"
            async for token in response.async_response_gen():
                async with self:
                    self.turns[-1]["answer"] += token
                    self.turns[-1]["answer_markdown"] = link_citations(
                        self.turns[-1]["answer"],
                        {source["number"] for source in self.turns[-1]["sources"]},
                        len(self.turns) - 1,
                    )
            async with self:
                self.turns[-1]["complete"] = True
        except Exception as exc:
            logger.warning("Answer failed (%s)", type(exc).__name__)
            async with self:
                self.error = "The answer could not finish. Check your API key, quota, and connection, then try again."
        finally:
            async with self:
                self.busy = False
                self.status = ""
