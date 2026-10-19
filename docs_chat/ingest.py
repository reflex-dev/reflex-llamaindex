"""Build the Reflex documentation index before starting a conversation."""

from docs_chat.rag import build_index

if __name__ == "__main__":
    print(f"Indexed {build_index()} documents. Start the app with uv run reflex run.")
