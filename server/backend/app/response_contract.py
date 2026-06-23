from __future__ import annotations

from collections.abc import Iterable

MarkdownSection = tuple[str, str | None]


def compose_markdown_sections(sections: Iterable[MarkdownSection]) -> str:
    blocks: list[str] = []
    for label, body in sections:
        text = (body or "").strip()
        if not text:
            continue
        blocks.append(f"**{label}：** {text}")
    return "\n\n".join(blocks)


def recommendation_contract_text(
    *,
    understanding: str,
    conclusion: str,
    primary_reason: str,
    next_step: str,
    review_summary: str | None = None,
    alternatives: str | None = None,
) -> str:
    return compose_markdown_sections(
        [
            ("理解", understanding),
            ("结论", conclusion),
            ("主推", primary_reason),
            ("评论摘要", review_summary),
            ("备选", alternatives),
            ("下一步", next_step),
        ]
    )


def action_message(text: str) -> str:
    return " ".join((text or "").split())
