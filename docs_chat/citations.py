"""Turn valid answer citations into links without changing the stored answer."""

import re

# Protect code and existing Markdown links before matching bare citation numbers.
_TOKENS = re.compile(
    r"```[\s\S]*?(?:```|\Z)|~~~[\s\S]*?(?:~~~|\Z)|`+[^`\n]*`+"
    r"|!?\[[^\]\n]*\]\([^\n)]*\)|\[[^\]\n]*\]\[[^\]\n]*\]"
    r"|\[(\d+(?:\s*,\s*\d+)*)\]"
)


def link_citations(answer: str, numbers: set[int], turn: int) -> str:
    """Link known citation numbers while leaving code and ordinary links intact."""

    def replace(match: re.Match) -> str:
        if match.group(1) is None:
            return match.group(0)
        return " ".join(
            f"[{number}](#source-{turn}-{number})"
            if int(number) in numbers
            else f"[{number}]"
            for number in re.split(r"\s*,\s*", match.group(1))
        )

    return _TOKENS.sub(replace, answer)


def excerpt_preview(excerpt: str) -> str:
    """Make a short readable preview from a retrieved Markdown passage."""
    text = re.sub(r"^Source \d+:\s*", "", excerpt)
    text = re.sub(r"[#`*]", "", text)
    text = " ".join(text.split())
    return text[:280].rsplit(" ", 1)[0] + "…" if len(text) > 280 else text
