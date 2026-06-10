package com.example.shopguideagent.ui.component

import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MarkdownTextFormatterTest {
    @Test
    fun renderMarkdownTextRemovesMarkdownMarkersAndKeepsReadableText() {
        val rendered = renderMarkdownText(
            """
            ## 推荐结论
            我推荐 **雀巢咖啡**，因为 *冲泡方便*。
            - `速溶`
            - [查看详情](https://example.com)
            """.trimIndent(),
            fallback = "",
        )

        assertEquals(
            "推荐结论\n我推荐 雀巢咖啡，因为 冲泡方便。\n• 速溶\n• 查看详情",
            rendered.text,
        )
        assertFalse(rendered.text.contains("**"))
        assertFalse(rendered.text.contains("*冲泡方便*"))
        assertFalse(rendered.text.contains("`"))
        assertFalse(rendered.text.contains("](https://example.com)"))
    }

    @Test
    fun renderMarkdownTextAppliesInlineStyles() {
        val rendered = renderMarkdownText("这款 **很适合**，也可以 *轻度烘焙*，关键词 `速溶`。", fallback = "")

        assertTrue(rendered.spanStyles.any { range -> range.item.fontWeight == FontWeight.Bold })
        assertTrue(rendered.spanStyles.any { range -> range.item.fontStyle == FontStyle.Italic })
        assertTrue(rendered.spanStyles.any { range -> range.item.fontFamily != null })
    }

    @Test
    fun renderMarkdownTextCanAutoSegmentLongAssistantText() {
        val source = "Conclusion: choose A. It fits your budget and avoids the brand you rejected. Alternative: choose B if you want a lighter taste. Next: ask me to compare them."

        val rendered = renderMarkdownText(source, fallback = "", autoSegment = true)

        assertTrue(rendered.text.contains("\n\n"))
        assertEquals(source, rendered.text.replace("\n\n", " "))
    }

    @Test
    fun renderMarkdownTextAutoSegmentsChineseRecommendationAndBoldsLogicLabels() {
        val source = "结论：优先看「东鹏特饮维生素功能饮料」，它更贴近你说的“要一瓶东鹏特饮”。我已按商品名、品牌和品类从商品库里匹配，主推这款，另外给你两款同类饮料作备选。评论摘要：这款适合需要快速补充能量的场景，口味接受度比较高。备选差异：如果你更想要低糖或更小瓶装，可以看第二款；如果你只想要同品牌，请继续告诉我预算。下一步：你可以直接说加入购物车，或者继续说不要这个口味。"

        val rendered = renderMarkdownText(source, fallback = "", autoSegment = true)

        assertTrue(rendered.text.contains("\n\n"))
        assertTrue(rendered.text.split("\n\n").size >= 4)
        assertTrue(rendered.text.contains("结论：优先看"))
        assertTrue(rendered.text.contains("评论摘要：这款"))
        assertTrue(rendered.text.contains("备选差异：如果"))
        assertTrue(rendered.text.contains("下一步：你可以"))
        assertBoldRange(rendered, "结论：")
        assertBoldRange(rendered, "评论摘要：")
        assertBoldRange(rendered, "备选差异：")
        assertBoldRange(rendered, "下一步：")
        assertFalse(rendered.text.contains("**"))
    }

    private fun assertBoldRange(rendered: androidx.compose.ui.text.AnnotatedString, label: String) {
        val start = rendered.text.indexOf(label)
        assertTrue("$label should be present", start >= 0)
        assertTrue(
            "$label should be bold",
            rendered.spanStyles.any { range ->
                range.item.fontWeight == FontWeight.Bold &&
                    range.start <= start &&
                    range.end >= start + label.length
            },
        )
    }
}
