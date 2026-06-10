package com.example.shopguideagent.data.catalog

import android.content.res.AssetManager
import com.example.shopguideagent.data.model.DerivedAttribute
import com.example.shopguideagent.data.model.ProductDerivedAttributes
import com.example.shopguideagent.data.model.ProductUiModel
import org.json.JSONArray
import org.json.JSONObject

interface ProductCatalog {
    fun recommend(query: String, limit: Int = 3): List<ProductUiModel>
    fun findById(productId: String): ProductUiModel? = null
}

class AndroidAssetProductCatalog(
    private val assets: AssetManager,
) : ProductCatalog {
    private val products: List<ProductUiModel> by lazy { loadProducts() }

    override fun recommend(query: String, limit: Int): List<ProductUiModel> {
        if (limit <= 0) return emptyList()
        return products
            .take(limit)
            .mapIndexed { index, product -> product.copy(isPrimary = index == 0) }
    }

    override fun findById(productId: String): ProductUiModel? =
        loadProducts().firstOrNull { it.productId == productId }

    private fun loadProducts(): List<ProductUiModel> =
        loadEnrichedProducts().ifEmpty { loadLegacyProducts() }

    private fun loadEnrichedProducts(): List<ProductUiModel> =
        runCatching {
            assets.open(ENRICHED_PRODUCTS_ASSET).bufferedReader(Charsets.UTF_8).useLines { lines ->
                lines
                    .filter { it.isNotBlank() }
                    .mapNotNull { line -> runCatching { parseProduct(JSONObject(line)) }.getOrNull() }
                    .toList()
            }
        }.getOrDefault(emptyList())

    private fun loadLegacyProducts(): List<ProductUiModel> =
        CATEGORY_DIRS.flatMap { category ->
            assets.list("$category/data").orEmpty()
                .filter { it.endsWith(".json") }
                .mapNotNull { fileName -> readProduct("$category/data/$fileName") }
        }

    private fun readProduct(assetPath: String): ProductUiModel? =
        runCatching {
            val raw = assets.open(assetPath).bufferedReader(Charsets.UTF_8).use { it.readText() }
            parseProduct(JSONObject(raw))
        }.getOrNull()

    private fun parseProduct(json: JSONObject): ProductUiModel {
        val derivedJson = json.optJSONObject("derived_attributes")
        val rag = json.optJSONObject("rag_knowledge")
        val description = rag?.optString("marketing_description").orEmpty()
        val derivedAttributes = parseDerivedAttributes(derivedJson)
        val positiveFeedback = derivedJson
            ?.optJSONArray("positive_feedback")
            .toAttributeList()
            .map { it.summaryText() }
            .distinct()
            .take(2)
        val negativeFeedback = derivedJson
            ?.optJSONArray("negative_feedback")
            .toAttributeList()
            .map { it.summaryText() }
            .distinct()
            .take(2)
        val riskTags = derivedJson
            ?.optJSONArray("risk_tags")
            .toAttributeList()
            .map { it.value }
            .filter { it.isNotBlank() }
            .distinct()
            .take(3)

        return ProductUiModel(
            productId = json.getString("product_id"),
            name = json.getString("title"),
            price = json.optDouble("base_price", 0.0),
            imageUrl = ProductImageUrlResolver.assetUrl(json.optString("image_path")),
            tags = deriveTags(
                description = description,
                fallback = json.optString("sub_category"),
                derivedAttributes = derivedAttributes,
                riskTags = riskTags,
            ),
            reason = deriveReason(description, derivedAttributes, positiveFeedback),
            rating = null,
            stock = null,
            isPrimary = false,
            derivedAttributes = derivedAttributes,
            positiveFeedbackSummary = positiveFeedback,
            negativeFeedbackSummary = negativeFeedback,
            riskTags = riskTags,
        )
    }

    private fun parseDerivedAttributes(json: JSONObject?): ProductDerivedAttributes {
        if (json == null) return ProductDerivedAttributes()
        return ProductDerivedAttributes(
            effects = json.optJSONArray("effects").toAttributeList(),
            suitableFor = json.optJSONArray("suitable_for").toAttributeList(),
            notRecommendedFor = json.optJSONArray("not_recommended_for").toAttributeList(),
            skinTypes = json.optJSONArray("skin_types").toAttributeList(),
            ingredients = json.optJSONArray("ingredients").toAttributeList(),
            usageScene = json.optJSONArray("usage_scene").toAttributeList(),
            cautions = json.optJSONArray("cautions").toAttributeList(),
            sellingPoints = json.optJSONArray("selling_points").toAttributeList(),
            generatedTags = json.optJSONArray("generated_tags").toAttributeList(),
        )
    }

    private fun deriveTags(
        description: String,
        fallback: String,
        derivedAttributes: ProductDerivedAttributes,
        riskTags: List<String>,
    ): List<String> {
        val derivedTags = (
            derivedAttributes.generatedTags +
            derivedAttributes.effects +
                derivedAttributes.suitableFor +
                derivedAttributes.usageScene +
                derivedAttributes.skinTypes
            ).map { it.value }
        val generatedTagValues = derivedAttributes.generatedTags
            .filter { it.confidence >= 0.6 }
            .map { it.value }
            .filter { it.isNotBlank() }
            .distinct()
            .take(4)
        if (generatedTagValues.isNotEmpty()) return generatedTagValues
        val matchedKeywords = TAG_KEYWORDS.filter { keyword ->
            description.contains(keyword) || fallback.contains(keyword) || derivedTags.any { it.contains(keyword) }
        }
        return (matchedKeywords + derivedTags.map { it.take(12) } + fallback + riskTags)
            .filter { it.isNotBlank() }
            .distinct()
            .take(3)
    }

    private fun deriveReason(
        description: String,
        derivedAttributes: ProductDerivedAttributes,
        positiveFeedback: List<String>,
    ): String =
        (
            derivedAttributes.suitableFor +
                derivedAttributes.effects +
                derivedAttributes.usageScene +
                derivedAttributes.sellingPoints
            )
            .map { it.summaryText() }
            .firstOrNull { it.isNotBlank() }
            ?: positiveFeedback.firstOrNull()
            ?: description
                .split('。', '；', '，')
                .firstOrNull { it.contains("适合") || it.contains("核心") || it.contains("主打") }
            ?: description.take(72)

    private fun JSONArray?.toAttributeList(): List<DerivedAttribute> {
        if (this == null) return emptyList()
        return (0 until length()).mapNotNull { index ->
            optJSONObject(index)?.let { item ->
                DerivedAttribute(
                    value = item.optString("value").trim(),
                    evidence = item.optString("evidence").trim(),
                    confidence = item.optDouble("confidence", 0.0),
                )
            }
        }.filter { it.value.isNotBlank() || it.evidence.isNotBlank() }
    }

    private fun DerivedAttribute.summaryText(): String =
        evidence.ifBlank { value }.replace(Regex("\\s+"), " ").take(72)

    companion object {
        private const val ENRICHED_PRODUCTS_ASSET = "products_enriched.jsonl"
        private val CATEGORY_DIRS = listOf("1_美妆护肤", "2_数码电子", "3_服饰运动", "4_食品生活")
        private val TAG_KEYWORDS = listOf(
            "敏感肌", "控油", "保湿", "清爽", "防晒", "速干", "通勤", "户外", "学生党", "上班族",
            "高性价比", "无糖", "咖啡", "轻薄", "旗舰", "运动", "温和", "补水", "修护", "夜间",
            "熬夜", "暗沉", "干皮", "油皮",
        )
    }
}

object ProductCatalogScorer {
    @JvmStatic
    fun score(product: ProductUiModel, query: String): Int {
        if (query.isBlank()) return 0
        val positiveScore =
            weightedMatches(query, listOf(product.name), 2) +
                weightedMatches(query, product.tags, 2) +
                weightedMatches(query, listOfNotNull(product.reason), 3) +
                weightedMatches(query, product.derivedAttributes.effects.map { it.value }, 7) +
                weightedMatches(query, product.derivedAttributes.suitableFor.map { it.value }, 8) +
                weightedMatches(query, product.derivedAttributes.usageScene.map { it.value }, 6) +
                weightedMatches(query, product.derivedAttributes.skinTypes.map { it.value }, 6) +
                weightedMatches(query, product.derivedAttributes.generatedTags.map { it.value }, 8) +
                weightedMatches(query, product.positiveFeedbackSummary, 4)
        val riskPenalty =
            weightedMatches(query, product.derivedAttributes.notRecommendedFor.map { it.value }, 10) +
                weightedMatches(query, product.riskTags, 9) +
                weightedMatches(query, product.negativeFeedbackSummary, 7)
        return positiveScore - riskPenalty
    }

    private fun weightedMatches(query: String, fields: List<String>, weight: Int): Int {
        val trimmedQuery = query.trim()
        val tokens = queryTokens(trimmedQuery)
        return fields
            .filter { it.isNotBlank() }
            .sumOf { field ->
                val direct = if (trimmedQuery.contains(field) || field.contains(trimmedQuery)) weight * 2 else 0
                val keyword = NEED_KEYWORDS.count { keyword ->
                    trimmedQuery.contains(keyword) && field.contains(keyword)
                } * weight
                val tokenScore = tokens.count { token -> field.contains(token) } * weight
                direct + keyword + tokenScore
            }
    }

    private fun queryTokens(query: String): List<String> =
        query
            .split(Regex("[\\s,，。；;、!！?？]+"))
            .filter { it.length >= 2 }

    private val NEED_KEYWORDS = listOf(
        "敏感肌", "敏感", "温和", "低刺激", "修护", "保湿", "补水", "夜间", "熬夜", "暗沉", "干皮",
        "油皮", "混油", "控油", "清爽", "防晒", "户外", "通勤", "速干", "透气", "运动", "咖啡",
        "无糖", "便宜", "性价比", "学生", "旗舰", "拍照", "办公",
    )
}

class ListProductCatalog(
    private val products: List<ProductUiModel>,
) : ProductCatalog {
    override fun recommend(query: String, limit: Int): List<ProductUiModel> =
        products.take(limit.coerceAtLeast(0)).mapIndexed { index, product -> product.copy(isPrimary = index == 0) }

    override fun findById(productId: String): ProductUiModel? =
        products.firstOrNull { it.productId == productId }
}
