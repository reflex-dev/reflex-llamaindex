"""Keep the source library usable when readers replace the bundled corpus."""

import pytest

from docs_chat import docs_chat as ui


def descendants(component):
    """Yield a component and its descendants in display order."""
    yield component
    for child in component.children:
        yield from descendants(child)


@pytest.mark.parametrize("count", [0, 1, 3, 4, 5])
def test_sidebar_renders_every_catalog_document(monkeypatch, count):
    """Render every custom source without relying on the bundled corpus size."""
    catalog = {
        f"custom-{index}.md": {
            "title": f"Custom document {index}",
            "source_url": f"https://example.com/docs/{index}",
            "fetched_at": "2026-10-19",
        }
        for index in range(count)
    }
    monkeypatch.setattr(ui, "document_catalog", lambda: catalog)

    sidebar = ui.sidebar()
    links = [
        component
        for component in descendants(sidebar)
        if getattr(component.class_name, "_var_value", component.class_name)
        == "library-item"
    ]
    assert len(links) == len(catalog)
    for link, page in zip(links, catalog.values(), strict=True):
        assert page["source_url"] in str(link)
        assert page["title"] in str(link)
        assert "Source documentation" in str(link)
    if not catalog:
        assert "No documents configured" in str(sidebar)


def test_sidebar_preserves_source_labels_when_reordered(monkeypatch):
    """Associate bundled presentation with the source URL, not list position."""
    catalog = ui.document_catalog()
    monkeypatch.setattr(
        ui, "document_catalog", lambda: dict(reversed(list(catalog.items())))
    )
    sidebar = ui.sidebar()
    links = [
        str(component)
        for component in descendants(sidebar)
        if getattr(component.class_name, "_var_value", component.class_name)
        == "library-item"
    ]
    forms = next(
        link for link in links if "https://reflex.dev/docs/library/forms/form/" in link
    )
    state = next(
        link for link in links if "https://reflex.dev/docs/state/overview/" in link
    )
    assert "Turn input into action" in forms
    assert "Data that follows your users" in state
