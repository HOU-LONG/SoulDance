"""锚点校验器（流式模式）— 逐 chunk 检测 [[product_id]]，循环状态机微缓冲校验后透传。"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

from .models import FactContext, FactRecord

logger = logging.getLogger(__name__)


class AnchorValidator:
    """流式锚点校验器。

    普通文本: 立即透传（零延迟）
    遇到 `[[`: 循环消费直到没有 `]]`，命中 → 展开为 "**商品名**"
                                     未命中 → 替换为 "该商品" + yield anchor_warning
    流式结束: deferred 裸奔名检测（记 warning + yield stray_warning 事件）
    """

    ANCHOR_PATTERN = re.compile(r'\[\[([A-Za-z0-9_-]+)\]\]')

    @staticmethod
    def extract_anchors(text: str) -> list[str]:
        return AnchorValidator.ANCHOR_PATTERN.findall(text)

    def resolve(self, anchor_id: str, fact_ctx: FactContext) -> FactRecord | None:
        return fact_ctx.product_index.get(anchor_id)

    def expand_anchor(self, anchor_id: str, fact_ctx: FactContext) -> str:
        record = self.resolve(anchor_id, fact_ctx)
        if record is not None:
            return f"**{record.title}**"
        logger.warning(f"[anchor_validator] unresolved anchor: {anchor_id}")
        return "该商品"

    async def stream_process(
        self,
        chunks: list[str] | AsyncIterator,
        fact_ctx: FactContext,
    ) -> AsyncIterator[dict]:
        """流式处理 LLM 输出 chunks。

        循环状态机：每个 chunk 内重复扫描直到没有 `[[` 为止，
        正确处理同 chunk 内的多个锚点（如 "推荐 [[P1]]，备选 [[P2]]"）。
        `[` 后缀缓冲处理跨 chunk 的 `[[` 分割（如 chunk1="["，chunk2="[P1]"）。
        """
        collected_text: list[str] = []
        pending = ""  # 跨 chunk 的未闭合锚点缓冲 + `[` 后缀缓冲

        if hasattr(chunks, '__aiter__'):
            async_iter = chunks
        else:
            async def _list_iter():
                for c in chunks:
                    yield c
            async_iter = _list_iter()

        async for chunk in async_iter:
            if not chunk:
                continue
            collected_text.append(chunk)
            text = pending + chunk
            pending = ""

            # 循环处理：同一 chunk 内可能包含多个 [[...]] 锚点
            while '[[' in text:
                before, rest = text.split('[[', 1)
                if before:
                    yield {"type": "text_delta", "text": before}

                if ']]' in rest:
                    anchor_id, after = rest.split(']]', 1)
                    anchor_id = anchor_id.strip()
                    record = self.resolve(anchor_id, fact_ctx)
                    if record is not None:
                        yield {"type": "text_delta", "text": f"**{record.title}**"}
                    else:
                        logger.warning(f"[anchor_validator] unresolved anchor: {anchor_id}")
                        yield {"type": "anchor_warning", "anchor_id": anchor_id}
                        yield {"type": "text_delta", "text": "该商品"}
                    text = after  # 继续循环
                else:
                    pending = '[[' + rest  # `]]` 在后续 chunk 中
                    break
            else:
                # 没有更多 `[[`
                # 关键: 如果 text 以 `[` 结尾，保留到 pending，
                # 防止 `[[` 跨 chunk 分割（如 chunk1="["，chunk2="[P1]"）
                if text and text[-1] == '[':
                    pending = '['
                    text = text[:-1]
                if text:
                    yield {"type": "text_delta", "text": text}

        # 流结束：pending 中剩余的文本（截断锚点或孤立的 `[`）
        if pending:
            yield {"type": "text_delta", "text": pending}

        # deferred 裸奔检测：在原始文本上检测未被锚点覆盖的商品名
        if fact_ctx.product_index:
            full_text = "".join(collected_text)
            strays = self.detect_stray_names(full_text, fact_ctx)
            if strays:
                logger.warning(f"[anchor_validator] stray names detected: {strays}")
                yield {
                    "type": "stray_warning",
                    "stray_names": strays,
                }

    def detect_stray_names(self, original_text: str, fact_ctx: FactContext) -> list[str]:
        """在原始 LLM 文本上检测未用锚点标记的商品名。

        注意: 必须在 expand 之前、原始文本上执行。
        已被 [[product_id]] 锚点覆盖的 title 自动排除。
        """
        strays: list[str] = []
        anchored_ids = set(self.extract_anchors(original_text))

        for pid, record in fact_ctx.product_index.items():
            if pid in anchored_ids:
                continue
            title = record.title
            if len(title) >= 4 and title in original_text:
                strays.append(title)
        return strays
