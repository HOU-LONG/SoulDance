package com.example.shopguideagent.data.model

data class DerivedAttribute @JvmOverloads constructor(
    val value: String,
    val evidence: String = "",
    val confidence: Double = 0.0,
)

data class ProductDerivedAttributes @JvmOverloads constructor(
    val effects: List<DerivedAttribute> = emptyList(),
    val suitableFor: List<DerivedAttribute> = emptyList(),
    val notRecommendedFor: List<DerivedAttribute> = emptyList(),
    val skinTypes: List<DerivedAttribute> = emptyList(),
    val ingredients: List<DerivedAttribute> = emptyList(),
    val usageScene: List<DerivedAttribute> = emptyList(),
    val cautions: List<DerivedAttribute> = emptyList(),
    val sellingPoints: List<DerivedAttribute> = emptyList(),
    val generatedTags: List<DerivedAttribute> = emptyList(),
)

data class ProductUiModel @JvmOverloads constructor(
    val productId: String,
    val name: String,
    val price: Double,
    val imageUrl: String? = null,
    val tags: List<String> = emptyList(),
    val reason: String? = null,
    val rating: Double? = null,
    val stock: Int? = null,
    val isPrimary: Boolean = false,
    val derivedAttributes: ProductDerivedAttributes = ProductDerivedAttributes(),
    val positiveFeedbackSummary: List<String> = emptyList(),
    val negativeFeedbackSummary: List<String> = emptyList(),
    val riskTags: List<String> = emptyList(),
    val brand: String = "",
)
