"""Download a small, explicit selection of official Reflex documentation."""

import json
import re
from datetime import datetime, timezone

import httpx

from docs_chat.rag import DATA

PAGES = [
    ("state.md", "State overview", "https://reflex.dev/docs/state/overview/"),
    ("events.md", "Events overview", "https://reflex.dev/docs/events/events-overview/"),
    ("forms.md", "Forms", "https://reflex.dev/docs/library/forms/form/"),
    (
        "deployment.md",
        "Deployment",
        "https://reflex.dev/docs/hosting/deploy-quick-start/",
    ),
]


def fetch_docs() -> None:
    """Save official Markdown and its title, canonical URL, and retrieval date."""
    fetched_at = datetime.now(timezone.utc).date().isoformat()
    snapshots = {}
    catalog = {}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for filename, title, url in PAGES:
            response = client.get(url.rstrip("/") + ".md")
            response.raise_for_status()
            content = response.text
            if "text/markdown" not in response.headers.get("content-type", ""):
                raise ValueError(f"Expected Markdown documentation from {url}")
            heading = re.search(r"^# .+$", content, flags=re.MULTILINE)
            if heading is None:
                raise ValueError(f"Missing page heading in {url}")
            # Skip the export's navigation notice and page-builder preamble.
            snapshots[filename] = content[heading.start() :]
            catalog[filename] = {
                "title": title,
                "source_url": url,
                "fetched_at": fetched_at,
            }
    DATA.mkdir(exist_ok=True)
    for filename, content in snapshots.items():
        (DATA / filename).write_text(content)
    (DATA / "sources.json").write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Downloaded {len(snapshots)} official Reflex docs pages ({fetched_at}).")
    print("Rebuild embeddings with: uv run python -m docs_chat.ingest")


if __name__ == "__main__":
    fetch_docs()
