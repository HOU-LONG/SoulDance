# server/tests/test_anchor_validator.py
from __future__ import annotations
import pytest
from server.backend.app.models import FactContext, FactRecord
from server.backend.app.anchor_validator import AnchorValidator


def _mk_ctx() -> FactContext:
    r1 = FactRecord(product_id="P1", title="小米 14 Ultra", brand="小米", price=5999.0,
                    category="手机", sub_category="智能机")
    r2 = FactRecord(product_id="P2", title="华为 Mate 70", brand="华为", price=6999.0,
                    category="手机", sub_category="智能机")
    return FactContext(
        prompt_block="",
        product_index={"P1": r1, "P2": r2},
        brand_index={"小米": ["P1"], "华为": ["P2"]},
    )


def test_extract_anchors_from_text():
    text = "推荐 [[P1]]，备选 [[P2]]"
    assert AnchorValidator.extract_anchors(text) == ["P1", "P2"]


def test_extract_anchors_none():
    assert AnchorValidator.extract_anchors("纯文本无锚点") == []


def test_resolve_valid():
    ctx = _mk_ctx()
    v = AnchorValidator()
    resolved = v.resolve("P1", ctx)
    assert resolved is not None
    assert resolved.title == "小米 14 Ultra"


def test_resolve_invalid():
    ctx = _mk_ctx()
    v = AnchorValidator()
    assert v.resolve("FAKE_ID", ctx) is None


def test_expand_anchor():
    ctx = _mk_ctx()
    v = AnchorValidator()
    result = v.expand_anchor("P1", ctx)
    assert result == "**小米 14 Ultra**"


def test_expand_anchor_invalid():
    ctx = _mk_ctx()
    v = AnchorValidator()
    result = v.expand_anchor("FAKE_ID", ctx)
    assert result == "该商品"


def test_detect_stray_names_on_original_text():
    """裸奔检测应在原始 LLM 输出上执行（expand 之前）。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    original_text = "我推荐小米 14 Ultra，它拍照很好"
    strays = v.detect_stray_names(original_text, ctx)
    assert len(strays) >= 1
    assert any("小米 14 Ultra" in s for s in strays)


def test_detect_stray_names_excludes_anchored():
    """被锚点覆盖的 title 不应被检测为 stray。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    original_text = "我推荐 [[P1]]，拍照很好。备选 [[P2]]。"
    strays = v.detect_stray_names(original_text, ctx)
    assert all("小米 14 Ultra" not in s for s in strays)


@pytest.mark.asyncio
async def test_stream_process_normal_text():
    """普通文本应逐 chunk 立即透传。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["推荐一款", "手机给", "你"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    assert "".join(text_parts) == "推荐一款手机给你"


@pytest.mark.asyncio
async def test_stream_process_with_anchor():
    """含锚点的 chunk 应展开后透传。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["我推荐 ", "[[P1]]", "，它拍照很好"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "小米 14 Ultra" in full
    assert "[[" not in full


@pytest.mark.asyncio
async def test_stream_process_with_invalid_anchor():
    """无效锚点应替换为「该商品」并产生 anchor_warning 事件。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["看看 ", "[[FAKE_ID]]", " 怎么样"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "该商品" in full
    # 应有 warning 事件
    warnings = [e for e in results if e["type"] == "anchor_warning"]
    assert len(warnings) >= 1


@pytest.mark.asyncio
async def test_stream_process_split_anchor():
    """锚点跨越两个 chunk 时应正确缓冲拼接。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["推荐 ", "[", "[P1]", "] 不错"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "小米 14 Ultra" in full
    assert "[[" not in full


@pytest.mark.asyncio
async def test_stream_process_same_chunk_anchor():
    """同一 chunk 内的锚点应被正确处理（如 "推荐 [[P1]]，备选 [[P2]]"）。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["推荐 [[P1]]，备选 [[P2]]，都不错"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "小米 14 Ultra" in full
    assert "华为 Mate 70" in full
    assert "[[" not in full


@pytest.mark.asyncio
async def test_stream_process_stray_detection_at_end():
    """流式结束时执行 deferred 裸奔检测。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["推荐 小米 14 Ultra，拍照不错"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    assert "小米 14 Ultra" in "".join(text_parts)
    strays = [e for e in results if e["type"] == "stray_warning"]
    assert len(strays) >= 1
