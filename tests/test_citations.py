"""Check citation targeting without touching code samples or ordinary links."""

from docs_chat.citations import link_citations


def test_citation_targets_preserve_turn_and_source_identity():
    assert link_citations("State [1]. Forms [2, 3]. Unknown [99].", {1, 2, 3}, 4) == (
        "State [1](#source-4-1). Forms [2](#source-4-2) [3](#source-4-3). Unknown [99]."
    )


def test_code_and_existing_links_are_not_rewritten():
    answer = (
        "Use `items[1]`.\n```python\nx[2]\n```\n[1](https://example.com) [2][ref] [3]"
    )
    assert link_citations(answer, {1, 2, 3}, 0) == answer[:-3] + "[3](#source-0-3)"
    assert link_citations("```python\nx[1]", {1}, 0) == "```python\nx[1]"


def test_partial_stream_citation_waits_for_closing_bracket():
    assert link_citations("Answer [1", {1}, 0) == "Answer [1"
    assert link_citations("Answer [1]", {1}, 0) == "Answer [1](#source-0-1)"
