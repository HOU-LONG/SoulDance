package com.example.shopguideagent.data.model

data class BundleUiModel(
    val bundleId: String,
    val scenario: String,
    val title: String,
    val groups: List<BundleGroupUiModel> = emptyList(),
    val actions: List<String> = emptyList(),
    val isStreaming: Boolean = false,
)

data class BundleGroupUiModel(
    val name: String,
    val items: List<BundleItemUiModel> = emptyList(),
)

data class BundleItemUiModel(
    val slot: String,
    val product: ProductUiModel,
)
