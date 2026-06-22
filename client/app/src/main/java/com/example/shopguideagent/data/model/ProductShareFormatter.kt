package com.example.shopguideagent.data.model

object ProductShareFormatter {
    @JvmStatic
    fun shareText(product: ProductUiModel): String = buildString {
        appendLine(product.name)
        appendLine("Price: CNY ${"%.2f".format(product.price)}")
        product.reason
            ?.takeIf { it.isNotBlank() }
            ?.let { appendLine("Why: $it") }
    }.trim()
}
