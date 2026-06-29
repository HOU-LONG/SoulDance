package com.example.shopguideagent.ui.component

import com.example.shopguideagent.data.model.ProductUiModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AiMessageChunkingTest {

    @Test
    fun emptyTextProducesNoChunks() {
        val chunks = splitAiMessageChunks("", productMap = emptyMap())
        assertTrue(chunks.isEmpty())
    }

    @Test
    fun blankTextProducesNoChunks() {
        val chunks = splitAiMessageChunks("   \n  \n\n  ", productMap = emptyMap())
        assertTrue(chunks.isEmpty())
    }

    @Test
    fun singleParagraphWithoutAnchorYieldsTextOnlyChunk() {
        val chunks = splitAiMessageChunks(
            text = "夏天选衬衫，核心看面料透气、版型合身、场景适配。",
            productMap = emptyMap(),
        )

        assertEquals(1, chunks.size)
        assertEquals("夏天选衬衫，核心看面料透气、版型合身、场景适配。", chunks[0].text)
        assertTrue(chunks[0].products.isEmpty())
    }

    @Test
    fun anchorInsideParagraphAttachesMatchingProduct() {
        val product = productOf("p_001", "海澜之家 免烫衬衫")
        val chunks = splitAiMessageChunks(
            text = "**商务通勤**：推荐 [[海澜之家 免烫衬衫#p_001]]，机洗免烫省心。",
            productMap = mapOf("p_001" to product),
        )

        assertEquals(1, chunks.size)
        assertEquals(listOf(product), chunks[0].products)
    }

    @Test
    fun anchorWithUnknownProductIdLeavesProductsEmptyAndKeepsText() {
        val chunks = splitAiMessageChunks(
            text = "我推荐 [[未知商品#p_missing]]。",
            productMap = emptyMap(),
        )

        assertEquals(1, chunks.size)
        assertTrue(chunks[0].products.isEmpty())
        assertTrue(
            "原始锚点应保留在文本中以便后续 markdown 渲染为链接",
            chunks[0].text.contains("[[未知商品#p_missing]]"),
        )
    }

    @Test
    fun multipleParagraphsEachAttachOwnAnchorProducts() {
        val p1 = productOf("p_001", "海澜之家 免烫衬衫")
        val p2 = productOf("p_002", "衬衫老罗 桑蚕丝衬衫")
        val chunks = splitAiMessageChunks(
            text = """
                **商务通勤**：推荐 [[海澜之家 免烫衬衫#p_001]]，省心。

                **质感场景**：推荐 [[衬衫老罗 桑蚕丝衬衫#p_002]]，垂感好。
            """.trimIndent(),
            productMap = mapOf("p_001" to p1, "p_002" to p2),
        )

        assertEquals(2, chunks.size)
        assertEquals(listOf(p1), chunks[0].products)
        assertEquals(listOf(p2), chunks[1].products)
    }

    @Test
    fun repeatedAnchorWithinParagraphYieldsSingleProduct() {
        val product = productOf("p_001", "海澜之家 免烫衬衫")
        val chunks = splitAiMessageChunks(
            text = "先看 [[海澜之家 免烫衬衫#p_001]]，再看 [[海澜之家 免烫衬衫#p_001]] 的细节。",
            productMap = mapOf("p_001" to product),
        )

        assertEquals(1, chunks.size)
        assertEquals(listOf(product), chunks[0].products)
    }

    @Test
    fun multipleDistinctAnchorsInOneParagraphAttachInOrder() {
        val p1 = productOf("p_001", "A 衬衫")
        val p2 = productOf("p_002", "B 衬衫")
        val chunks = splitAiMessageChunks(
            text = "可以对比 [[A 衬衫#p_001]] 和 [[B 衬衫#p_002]]，前者透气、后者垂感更好。",
            productMap = mapOf("p_001" to p1, "p_002" to p2),
        )

        assertEquals(1, chunks.size)
        assertEquals(listOf(p1, p2), chunks[0].products)
    }

    @Test
    fun multipleBlankLinesBetweenParagraphsCollapseIntoSplit() {
        val chunks = splitAiMessageChunks(
            text = "第一段。\n\n\n第二段。",
            productMap = emptyMap(),
        )

        assertEquals(2, chunks.size)
        assertEquals("第一段。", chunks[0].text)
        assertEquals("第二段。", chunks[1].text)
    }
}

private fun productOf(productId: String, name: String, brand: String = "演示品牌"): ProductUiModel =
    ProductUiModel(
        productId = productId,
        name = name,
        price = 199.0,
        brand = brand,
    )
