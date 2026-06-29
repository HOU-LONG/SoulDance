"""ProductMatcher 模糊匹配单元测试。

依赖真实 catalog（server/tests/conftest.py 已把 cwd 切到 repo 根，load_products('ecommerce_agent_dataset') 直接可用）。
"""
from __future__ import annotations

import pytest

from backend.app.data_loader import load_products
from backend.app.embedding_retriever import BM25OnlyRetriever
from backend.app.product_matcher import ProductMatcher


@pytest.fixture()
def matcher() -> ProductMatcher:
    products = load_products("ecommerce_agent_dataset")
    retriever = BM25OnlyRetriever(products)
    return ProductMatcher(retriever, products=products)


def test_match_fuzzy_long_title_with_short_user_query(matcher: ProductMatcher):
    """用户用简称查长标题：'雀巢咖啡' 应命中库内雀巢系列。"""
    result = matcher.match("雀巢咖啡")
    assert result.best is not None, f"应命中库内雀巢商品，candidates={[p.title for p in result.candidates]}"
    assert "雀巢" in result.best.title


def test_match_brand_plus_model_with_close_variant(matcher: ProductMatcher):
    """用户问 'Pura 70 Pro' 但库内只有 'Pura 90 Pro'：仍应模糊命中最接近的型号。"""
    result = matcher.match("华为 Pura 70 Pro")
    assert result.best is not None
    assert "华为" in result.best.title
    assert "Pura" in result.best.title


def test_match_nickname_like_short_alias(matcher: ProductMatcher):
    """用户用昵称 '小棕瓶' 查商品：BM25 应能从评论/卖点中召回雅诗兰黛。"""
    result = matcher.match("小棕瓶")
    assert result.best is not None
    assert "雅诗兰黛" in result.best.title or "小棕瓶" in result.best.title


def test_match_known_in_catalog_full_brand(matcher: ProductMatcher):
    """库内有完全对得上的商品：'李宁 韦德之道' → 命中正确款。"""
    result = matcher.match("李宁 韦德之道")
    assert result.best is not None
    assert "李宁" in result.best.title
    assert "韦德之道" in result.best.title


def test_match_ambiguous_returns_candidates_not_best(matcher: ProductMatcher):
    """用户说 '小米 17' 但库里小米 17 系列有多款（Max/Ultra/Pro）：top1/top2 分差不够 →
    best=None 但 candidates 仍透传供上层提示用户挑选。"""
    result = matcher.match("小米 17")
    # 库里小米 17 多款且分差小，gap 不达阈值
    assert result.best is None
    assert len(result.candidates) >= 2
    # 至少 top2 中应有"小米"商品
    titles = " ".join(p.title for p in result.candidates[:3])
    assert "小米" in titles


def test_match_no_match_returns_empty_or_none(matcher: ProductMatcher):
    """库里完全没有的内容应该返回 best=None；这里用纯随机字符串避免 BM25 误命中。

    注意：BM25 分词后只要任一 token 命中商品 chunk 就有分数，所以"完全无关"必须用
    catalog 词典里没有的字符（asdf, 乱码英文）。
    """
    result = matcher.match("zzqxqxqzzq nonsense alphabet")
    assert result.best is None


def test_match_empty_query_safe(matcher: ProductMatcher):
    """空字符串不应抛异常。"""
    result = matcher.match("")
    assert result.best is None
    assert result.candidates == []
    assert result.confidence == 0.0


def test_match_whitespace_only_query_safe(matcher: ProductMatcher):
    """纯空白也不应抛异常。"""
    result = matcher.match("   \n\t  ")
    assert result.best is None


def test_match_many_processes_each_query(matcher: ProductMatcher):
    """批量匹配：每个 query 独立给出结果。"""
    results = matcher.match_many(["雀巢咖啡", "zzqxqxqzzq nonsense"])
    assert len(results) == 2
    assert results[0].best is not None
    assert results[1].best is None


def test_candidates_always_returned_within_top_k(matcher: ProductMatcher):
    """top_k 控制候选返回上限。"""
    result = matcher.match("华为", top_k=3)
    assert len(result.candidates) <= 3


def test_match_returns_correct_confidence_signal(matcher: ProductMatcher):
    """confidence 反映 top1/top2 分差，模糊场景下 confidence 较低。"""
    confident = matcher.match("雀巢咖啡")
    ambiguous = matcher.match("小米 17")
    # 明确命中的 gap 应该 >= 0.15，模糊的应该 < 0.15
    assert confident.confidence >= 0.15
    assert ambiguous.confidence < 0.15
