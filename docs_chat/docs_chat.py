"""A focused reading and conversation space for the Reflex documentation."""

import reflex as rx

from docs_chat.rag import document_catalog
from docs_chat.state import State, Turn

SOURCE_PRESENTATION = {
    "https://reflex.dev/docs/state/overview/": (
        "layers",
        "Data that follows your users",
    ),
    "https://reflex.dev/docs/events/events-overview/": (
        "zap",
        "Make your interface respond",
    ),
    "https://reflex.dev/docs/library/forms/form/": (
        "text-cursor-input",
        "Turn input into action",
    ),
    "https://reflex.dev/docs/hosting/deploy-quick-start/": (
        "cloud-upload",
        "Take your app live",
    ),
}


def brand_mark(small: bool = False) -> rx.Component:
    """Render the shared product mark."""
    return rx.box(
        rx.icon("braces", size=20 if small else 28),
        class_name="brand-mark small" if small else "brand-mark",
    )


def inline_citation(*children, **props) -> rx.Component:
    """Render citation links as accessible hover previews and dialog buttons."""
    href = rx.Var("props.href", _var_type=str).to(str)
    source = State.citation_lookup.get(href, {})
    return rx.el.span(
        rx.cond(
            State.citation_lookup.contains(href),
            rx.hover_card.root(
                rx.hover_card.trigger(
                    rx.el.span(
                        rx.el.button(
                            *children,
                            type="button",
                            on_click=State.open_citation(href),
                            aria_label="Source "
                            + source.get("number", "")
                            + ": "
                            + source.get("title", ""),
                            aria_haspopup="dialog",
                            class_name="inline-citation",
                        ),
                        class_name="citation-trigger",
                    ),
                ),
                rx.hover_card.content(
                    rx.hstack(
                        rx.icon("file-text", size=17),
                        rx.text(source.get("title", ""), weight="medium"),
                        class_name="citation-preview-heading",
                    ),
                    rx.text("Reflex documentation", class_name="citation-domain"),
                    rx.text(
                        source.get("preview", ""), class_name="citation-preview-text"
                    ),
                    rx.text(
                        "Click to read the full passage",
                        class_name="citation-preview-hint",
                    ),
                    side="top",
                    align="start",
                    side_offset=8,
                    collision_padding=16,
                    class_name="citation-preview",
                ),
                open_delay=200,
                close_delay=100,
            ),
            rx.link(*children, href=href, is_external=True),
        ),
        class_name="inline-link-wrapper",
    )


def citation_dialog() -> rx.Component:
    """Show a selected passage without changing the conversation's scroll position."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.box(
                    rx.icon("file-text", size=22), class_name="citation-dialog-icon"
                ),
                rx.box(
                    rx.text(
                        "Source " + State.selected_source.get("number", ""),
                        class_name="citation-domain",
                    ),
                    rx.dialog.title(
                        State.selected_source.get("title", ""),
                        class_name="citation-dialog-title",
                    ),
                ),
                rx.spacer(),
                rx.dialog.close(
                    rx.el.button(
                        rx.icon("x", size=19),
                        aria_label="Close source",
                        class_name="citation-close",
                    )
                ),
                class_name="citation-dialog-header",
            ),
            rx.dialog.description(
                "Supporting passage from the Reflex documentation.",
                class_name="citation-dialog-description",
            ),
            rx.box(
                rx.markdown(
                    State.selected_source.get("excerpt", ""),
                    component_map={
                        "a": lambda *children, **props: rx.el.span(*children)
                    },
                    class_name="citation-full-text",
                ),
                class_name="citation-dialog-body",
                tab_index=0,
                role="region",
                aria_label="Source passage",
            ),
            rx.cond(
                State.selected_source.get("url", ""),
                rx.link(
                    "Open original documentation",
                    rx.icon("arrow-up-right", size=15),
                    href=State.selected_source.get("url", ""),
                    is_external=True,
                    class_name="citation-original-link",
                ),
            ),
            class_name="citation-dialog",
            max_width="640px",
        ),
        open=State.citation_open,
        on_open_change=State.set_citation_open,
    )


def conversation_turn(turn: Turn) -> rx.Component:
    """Present the answer with evidence available on demand."""
    return rx.box(
        rx.box(
            rx.text("You", class_name="speaker"),
            rx.heading(turn["question"], size="5"),
            class_name="question-block",
        ),
        rx.hstack(
            brand_mark(True),
            rx.text("Reflex Docs", weight="medium"),
            class_name="answer-byline",
        ),
        rx.cond(
            turn["answer"],
            rx.markdown(
                turn["answer_markdown"],
                component_map={"a": inline_citation},
                class_name="answer-copy",
            ),
            rx.text(
                rx.cond(
                    State.busy,
                    "Reading the documentation…",
                    "No answer received. Try your question again.",
                ),
                class_name="muted",
            ),
        ),
        class_name="conversation-turn",
    )


def suggestion(title: str, question: str, icon: str) -> rx.Component:
    """Offer a useful starting question without submitting it automatically."""
    return rx.button(
        rx.hstack(
            rx.icon(icon, size=17),
            rx.text(title),
            rx.spacer(),
            rx.icon("arrow-up-right", size=14),
        ),
        rx.text(question, class_name="suggestion-question"),
        on_click=State.set_question(question),
        disabled=State.busy,
        class_name="suggestion",
    )


def introduction() -> rx.Component:
    """Invite the reader to ask a question about the selected documentation."""
    return rx.box(
        rx.box(
            brand_mark(),
            rx.el.span("Your Python app starts here."),
            class_name="intro-mark",
        ),
        rx.heading("Less searching.\nMore building.", class_name="hero-title"),
        rx.text(
            "A conversation with the Reflex docs. Ask a question, follow the sources, and get back to your code.",
            class_name="hero-description",
        ),
        class_name="introduction",
    )


def source_library_item(page: dict[str, str]) -> rx.Component:
    """Render a source link with fallback presentation for custom documents.

    Args:
        page: Catalog metadata containing the document title and source URL.

    Returns:
        A link to the document with its icon, title, and description.
    """
    icon, description = SOURCE_PRESENTATION.get(
        page["source_url"], ("file-text", "Source documentation")
    )
    return rx.link(
        rx.box(rx.icon(icon, size=18), class_name="library-icon"),
        rx.box(
            rx.text(page["title"], class_name="library-title"),
            rx.text(description, class_name="library-description"),
        ),
        rx.icon("arrow-up-right", size=13, class_name="library-arrow"),
        href=page["source_url"],
        is_external=True,
        class_name="library-item",
    )


def sidebar() -> rx.Component:
    """Show the actual source library and a conversation reset action."""
    pages = list(document_catalog().values())
    return rx.el.aside(
        rx.link(
            brand_mark(True),
            rx.text("reflex", class_name="wordmark"),
            rx.el.span("Docs", class_name="brand-suffix"),
            href="https://reflex.dev/",
            is_external=True,
            class_name="brand",
        ),
        rx.button(
            rx.icon("plus", size=17),
            "New conversation",
            on_click=State.clear_chat,
            disabled=State.busy,
            class_name="new-chat",
        ),
        rx.box(
            rx.icon("messages-square", size=17),
            rx.text("Ask the docs"),
            rx.el.span(class_name="active-dot"),
            class_name="active-nav",
        ),
        rx.box(
            rx.hstack(
                rx.text("Source library", weight="medium"),
                rx.spacer(),
                rx.el.span(str(len(pages)), class_name="library-count"),
            ),
            rx.text("The pages behind every answer.", class_name="library-caption"),
            *[source_library_item(page) for page in pages],
            class_name="library",
        ),
        rx.box(
            rx.icon("book-open-check", size=21),
            rx.text("Go straight to the source.", weight="medium"),
            rx.text(
                "Every answer includes passages you can open and check for yourself."
            ),
            class_name="library-note",
        ),
        rx.box(
            rx.hstack(
                rx.el.span(class_name="public-dot"), rx.text("Public documentation")
            ),
            rx.text(
                f"Snapshot updated {pages[0]['fetched_at']}"
                if pages
                else "No documents configured",
                class_name="snapshot",
            ),
            class_name="sidebar-footer",
        ),
        class_name="sidebar",
    )


def setup_messages() -> rx.Component:
    """Keep setup and failure actions visible near the composer."""
    return rx.box(
        rx.cond(
            State.setup,
            rx.callout(
                rx.vstack(
                    rx.text(State.setup),
                    rx.hstack(
                        rx.button(
                            "Build / retry index",
                            on_click=State.prepare_index,
                            disabled=State.busy,
                            size="1",
                        ),
                        rx.button(
                            "Check setup",
                            on_click=State.check_setup,
                            disabled=State.busy,
                            size="1",
                            variant="soft",
                        ),
                        wrap="wrap",
                    ),
                    align="start",
                ),
                icon="settings",
                color_scheme="amber",
                width="100%",
            ),
        ),
        rx.cond(
            State.setup_feedback,
            rx.text(State.setup_feedback, role="status", class_name="setup-feedback"),
        ),
        rx.cond(
            State.error,
            rx.callout(
                State.error,
                icon="circle-alert",
                color_scheme="red",
                role="alert",
                width="100%",
            ),
        ),
        rx.cond(
            State.busy,
            rx.hstack(
                rx.spinner(size="1"),
                rx.text(State.status),
                role="status",
                class_name="progress",
            ),
        ),
        class_name="setup-messages",
    )


def composer() -> rx.Component:
    """Render the question field and submit action as the main point of focus."""
    return rx.box(
        setup_messages(),
        rx.form(
            rx.input(
                name="question",
                aria_label="Ask the Reflex docs",
                placeholder="What would you like to build?",
                value=State.question,
                on_change=State.set_question,
                disabled=State.busy,
                max_length=2000,
                required=True,
                class_name="question-input",
            ),
            rx.hstack(
                rx.hstack(
                    rx.icon("book-open", size=15),
                    rx.text("Reflex documentation"),
                    class_name="composer-context",
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("arrow-up", size=19),
                    type="submit",
                    aria_label="Send question",
                    disabled=State.busy | (State.question.strip() == ""),
                    class_name="send-button",
                ),
                class_name="composer-bottom",
            ),
            on_submit=State.ask,
            class_name="composer",
        ),
        rx.text(
            "Grounded in four guides. Check the sources for the details.",
            class_name="composer-note",
        ),
        class_name="composer-area",
    )


def index() -> rx.Component:
    """Render the responsive documentation workspace."""
    return rx.box(
        sidebar(),
        citation_dialog(),
        rx.box(
            rx.el.header(
                rx.hstack(
                    rx.icon("messages-square", size=17),
                    rx.text("Documentation assistant"),
                ),
                rx.hstack(
                    rx.link(
                        "Open docs",
                        rx.icon("arrow-up-right", size=14),
                        href="https://reflex.dev/docs/getting-started/introduction/",
                        is_external=True,
                        class_name="header-link",
                    ),
                    rx.button(
                        rx.icon("plus", size=16),
                        "New chat",
                        on_click=State.clear_chat,
                        disabled=State.busy,
                        class_name="mobile-new-chat",
                    ),
                ),
                class_name="topbar",
            ),
            rx.box(
                rx.box(
                    rx.cond(
                        State.turns.length() == 0,
                        introduction(),
                        rx.box(
                            rx.foreach(State.turns, conversation_turn),
                            class_name="conversation",
                        ),
                    ),
                    rx.cond(
                        State.turns.length() == 0,
                        rx.box(
                            rx.text(
                                "A few places to start", class_name="suggestion-label"
                            ),
                            rx.box(
                                suggestion(
                                    "Understand state",
                                    "How is state kept separate for each user?",
                                    "layers",
                                ),
                                suggestion(
                                    "Work with forms",
                                    "How do I handle form submissions?",
                                    "text-cursor-input",
                                ),
                                suggestion(
                                    "Ship your app",
                                    "How do I deploy a Reflex app?",
                                    "cloud-upload",
                                ),
                                class_name="suggestion-grid",
                            ),
                            class_name="suggestions",
                        ),
                    ),
                    class_name=rx.cond(
                        State.turns.length() == 0,
                        "workspace empty",
                        "workspace chatting",
                    ),
                ),
                class_name="conversation-scroll",
            ),
            rx.box(composer(), class_name="composer-dock"),
            class_name="main-panel",
        ),
        class_name="docs-app",
    )


app = rx.App(stylesheets=["/design.css"])
app.add_page(
    index,
    title="Reflex Docs · A conversation with your documentation",
    on_load=State.load_setup,
)
