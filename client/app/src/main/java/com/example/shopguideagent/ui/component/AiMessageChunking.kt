package com.example.shopguideagent.ui.component

import com.example.shopguideagent.data.model.ProductUiModel

/**
 * AI 消息按段落切分后的渲染单元：一段 markdown 文本 + 段内锚点对应的商品列表。
 * 由 [splitAiMessageChunks] 生成，供 AiMessageBlock 渲染时段落与卡片交替排列使用。
 */
internal data class AiMessageChunk(
    val text: String,
    val products: List<ProductUiModel>,
)

private val anchorRegex = Regex("""\[\[(.+?)#(.+?)]]""")
private val paragraphSplitRegex = Regex("""\n{2,}""")

/**
 * 把 AI 消息文本按空行切成若干段落，并把每段内 `[[name#productId]]` 锚点解析为对应商品。
 *
 * 行为约定：
 * - 空段或仅空白的段落跳过
 * - 锚点 productId 不在 [productMap] 中时，该段 products 为空，文本保留原始锚点字符串
 *   （由 renderMarkdownText 渲染为带颜色的链接，等待商品到达时不丢上下文）
 * - 同一段内重复锚点（同 productId）只挂一次商品，避免重复卡片
 */
internal fun splitAiMessageChunks(
    text: String,
    productMap: Map<String, ProductUiModel>,
): List<AiMessageChunk> {
    if (text.isBlank()) return emptyList()
    return text.split(paragraphSplitRegex)
        .map { it.trim() }
        .filter { it.isNotBlank() }
        .map { paragraph ->
            val products = anchorRegex.findAll(paragraph)
                .map { it.groupValues[2] }
                .distinct()
                .mapNotNull { productMap[it] }
                .toList()
            AiMessageChunk(text = paragraph, products = products)
        }
}
