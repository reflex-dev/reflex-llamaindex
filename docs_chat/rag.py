"""Index official Reflex documentation and answer questions with cited evidence."""

import asyncio
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from llama_index.core import (
    Document,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.base.response.schema import AsyncStreamingResponse
from llama_index.core.chat_engine.condense_question import DEFAULT_PROMPT
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.query_engine import CitationQueryEngine
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STORAGE = ROOT / ".storage"


def setting(name: str, default: str = "") -> str:
    """Read configuration without exposing secrets to browser state."""
    return os.environ.get(name) or dotenv_values(ROOT / ".env").get(name) or default


def document_paths() -> list[Path]:
    """Return the Markdown documents included in the shared knowledge base."""
    return [DATA / filename for filename in document_catalog()]


def document_catalog() -> dict[str, dict[str, str]]:
    """Read the titles and canonical URLs for the selected documentation pages."""
    return json.loads((DATA / "sources.json").read_text())


def corpus_fingerprint() -> str:
    """Identify the corpus and embedding model used to build the index."""
    digest = hashlib.sha256(
        setting("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").encode()
    )
    digest.update((DATA / "sources.json").read_bytes())
    for path in document_paths():
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def setup_problem() -> str:
    """Explain the next setup step, or return an empty string when ready."""
    if not setting("OPENAI_API_KEY"):
        return "Add OPENAI_API_KEY to .env, then build the index using the README."
    manifest = STORAGE / "fingerprint.txt"
    if not manifest.exists() or manifest.read_text() != corpus_fingerprint():
        return "Build the document index to enable chat. This sends the four public docs pages to OpenAI for embedding."
    return ""


def embedding_model() -> OpenAIEmbedding:
    """Create the embedding client used for both indexing and retrieval."""
    return OpenAIEmbedding(
        model=setting("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        api_key=setting("OPENAI_API_KEY"),
        timeout=30,
        max_retries=0,
    )


def build_index() -> int:
    """Persist an index of selected docs and return the document count."""
    if not setting("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in .env before indexing.")
    catalog = document_catalog()
    documents = [
        Document(
            text=path.read_text(),
            metadata={"file_name": path.name, **catalog[path.name]},
            excluded_embed_metadata_keys=["source_url", "fetched_at"],
            excluded_llm_metadata_keys=["source_url", "fetched_at"],
        )
        for path in document_paths()
    ]
    if not documents:
        raise ValueError("Add at least one Markdown document to data/.")
    index = VectorStoreIndex.from_documents(
        documents,
        embed_model=embedding_model(),
        transformations=[SentenceSplitter(chunk_size=512, chunk_overlap=40)],
    )
    index.storage_context.persist(persist_dir=str(STORAGE))
    (STORAGE / "fingerprint.txt").write_text(corpus_fingerprint())
    get_index.cache_clear()
    return len(documents)


@lru_cache(maxsize=1)
def get_index(fingerprint: str) -> VectorStoreIndex:
    """Load the persisted index once per corpus version in this process."""
    return load_index_from_storage(
        StorageContext.from_defaults(persist_dir=str(STORAGE)),
        embed_model=embedding_model(),
    )


async def answer(
    question: str, history: list[tuple[str, str]]
) -> AsyncStreamingResponse:
    """Retrieve evidence and stream a cited answer using this session's history."""
    problem = setup_problem()
    if problem:
        raise ValueError(problem)
    llm = OpenAI(
        model=setting("OPENAI_MODEL", "gpt-6-luna"),
        api_key=setting("OPENAI_API_KEY"),
        reasoning_effort="none",
        max_tokens=700,
        timeout=45,
        max_retries=1,
    )
    if history:
        transcript = "\n".join(f"Human: {q}\nAssistant: {a}" for q, a in history[-5:])
        question = await llm.apredict(
            DEFAULT_PROMPT, chat_history=transcript, question=question
        )
    index = await asyncio.to_thread(get_index, corpus_fingerprint())
    engine = CitationQueryEngine.from_args(
        index,
        llm=llm,
        similarity_top_k=3,
        citation_chunk_size=256,
        citation_chunk_overlap=20,
        streaming=True,
        use_async=True,
    )
    return await engine.aquery(question)
