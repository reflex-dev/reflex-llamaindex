# Chat with the Reflex docs

A small document-chat app with streamed answers, numbered source passages, and
follow-up questions. Reflex handles the interface and per-session state;
LlamaIndex handles indexing, retrieval, and cited answer generation.

The knowledge base is a dated snapshot of four official Reflex documentation pages:

- [State overview](https://reflex.dev/docs/state/overview/)
- [Events overview](https://reflex.dev/docs/events/events-overview/)
- [Forms](https://reflex.dev/docs/library/forms/form/)
- [Deployment quickstart](https://reflex.dev/docs/hosting/deploy-quick-start/)

The app does not search the entire Reflex site or browse live during a chat.
Each source passage links to its original page. `data/sources.json` records titles,
canonical URLs, and the date the snapshot was fetched. The document text comes
from the official Markdown exports, with the export's navigation notice and
page-builder preamble before the first heading removed. Code examples are kept.
The copied documentation remains the work of its original authors.

## Run it

Requires Python 3.12+ and uv. The locked environment was tested with Python 3.14.6,
Reflex 0.10.0, and LlamaIndex core 0.14.25.

```bash
git clone --branch v0.1.0 https://github.com/reflex-dev/reflex-llamaindex.git
cd reflex-llamaindex
uv sync --locked
cp .env.example .env
```

If `.env` already exists, edit it instead of replacing it. Set `OPENAI_API_KEY`
there. Answers and follow-up rewriting use `gpt-6-luna` with reasoning effort
set to `none`; embeddings use `text-embedding-3-small`. Changing only the chat
model does not require rebuilding the index.
Environment variables take precedence over `.env`. API calls incur provider usage
charges. Indexing sends document text to OpenAI; answering sends the question,
retrieved passages, and recent conversation context. The bundled corpus contains public Reflex documentation.

Build the index once, then start the app:

```bash
uv run python -m docs_chat.ingest
uv run reflex run --env prod --single-port
```

Open the URL printed by Reflex. The app displays a setup message if the key or
index is missing. You can also use **Build / retry index** in the local app instead
of running the indexing command. It shows progress and reports missing API credits,
invalid credentials, or connection failures. **Check setup** only rechecks the
local configuration and index files; it does not verify API credit or build the
index. Never put the key in browser state or commit `.env`.

For editing the app with hot reload, use `uv run reflex run` instead.

## Try the complete flow

1. Ask **How is state kept separate for each user?**
2. Ask **Where is that state stored?** The follow-up should retain the state topic.
3. Hover an inline citation for a preview. Click or tap it to read the passage in a dialog, then use **Open original documentation** to verify it.
4. Ask **How do I handle form submissions?** Check the named inputs and submit handler.
5. Ask **How do I deploy a Reflex app?** Compare the answer with the deployment page.
6. Ask about a topic outside these four pages, such as a particular enterprise
   authentication provider. The app should acknowledge missing information.
7. Open a separate browser session. Its conversation should start empty.
8. Click **New conversation** to clear that session's conversation context.

Citation numbers identify retrieved passages; they do not prove the model's
claim. Check the actual text. Answer quality needs testing with a real API key.

## How it works

- `data/*.md`: the selected official documentation, with provenance in `sources.json`.
- `docs_chat/fetch_docs.py`: downloads the four explicit Markdown URLs and refreshes the snapshot.
- `docs_chat/ingest.py`: an explicit indexing command. Documents are split into
  chunks, embedded, and saved in `.storage/`. This avoids repeated embedding
  calls every time someone opens the app.
- `docs_chat/rag.py`: loads the index, rewrites a follow-up question using up to
  five completed turns, and calls LlamaIndex's `CitationQueryEngine`. Models are
  passed explicitly; there is no process-global chat memory.
- `docs_chat/state.py`: stores each browser session's messages and streams actual
  provider tokens from a background event. API waits happen outside the state
  lock; short `async with self` blocks publish updates. Indexing also runs in
  the background, with duplicate work guarded separately. Source passages retain the engine's numbering.
  Incomplete responses are displayed but excluded from future chat context.
- `docs_chat/docs_chat.py`: renders the document list, suggested questions,
  conversation, composer, and expandable evidence.

The index is shared because all four documentation pages are public. Conversations live
in Reflex state and are not a durable account-based history. This example does
not provide authentication, private document uploads, or document access control.
Add those controls before adapting it to private team information or exposing a
paid API-backed demo publicly.

To refresh the selected documentation:

```bash
uv run python -m docs_chat.fetch_docs
uv run python -m docs_chat.ingest
```

The fingerprint includes both document content and source metadata, so a changed
snapshot requires rebuilding the index. Restart the app after refreshing to update
the sidebar date. Do not rebuild while requests are in flight. To expand coverage,
add an explicit official page to `PAGES` in `fetch_docs.py`, then refresh and rebuild.

## Checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run reflex compile --dry
```

Tests use test-only embedding and language models. They exercise the real
LlamaIndex persistence/retrieval/citation pipeline, streamed UI state, interrupted
responses, invalid input, and session isolation. They do not establish OpenAI
connectivity or generated-answer accuracy. The running app has no mock-answer
mode.

## Source references

- [Reflex background events](https://reflex.dev/docs/events/background-events/)
- [LlamaIndex citation engine](https://developers.llamaindex.ai/python/framework-api-reference/query_engine/citation/)
- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
