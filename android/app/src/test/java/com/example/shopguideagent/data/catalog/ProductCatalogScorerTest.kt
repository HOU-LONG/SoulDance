package com.example.shopguideagent.data.catalog

import com.example.shopguideagent.data.model.DerivedAttribute
import com.example.shopguideagent.data.model.ProductDerivedAttributes
import com.example.shopguideagent.data.model.ProductUiModel
import org.junit.Assert.assertTrue
import org.junit.Test

class ProductCatalogScorerTest {
    @Test
    fun scoreRewardsDerivedAttributesThatMatchTheUserNeed() {
        val matched = product(
            id = "matched",
            derivedAttributes = ProductDerivedAttributes(
                effects = listOf(attribute("夜间修护"), attribute("保湿")),
                suitableFor = listOf(attribute("熬夜暗沉")),
                usageScene = listOf(attribute("夜间护肤")),
                skinTypes = listOf(attribute("干皮")),
            ),
        )
        val generic = product(id = "generic")

        assertTrue(
            ProductCatalogScorer.score(matched, "想要熬夜后夜间修护保湿") >
                ProductCatalogScorer.score(generic, "想要熬夜后夜间修护保湿"),
        )
    }

    @Test
    fun scorePenalizesRiskAttributesThatConflictWithTheUserNeed() {
        val carefulMatch = product(
            id = "careful",
            derivedAttributes = ProductDerivedAttributes(
                suitableFor = listOf(attribute("敏感肌")),
                skinTypes = listOf(attribute("敏感肌")),
            ),
            positiveFeedbackSummary = listOf("敏感肌用户反馈温和不刺激"),
        )
        val riskyMatch = product(
            id = "risky",
            derivedAttributes = ProductDerivedAttributes(
                suitableFor = listOf(attribute("敏感肌")),
                skinTypes = listOf(attribute("敏感肌")),
                notRecommendedFor = listOf(attribute("敏感肌慎用")),
            ),
            negativeFeedbackSummary = listOf("敏感肌用户反馈泛红刺痛"),
            riskTags = listOf("泛红刺痛风险", "敏感肌不适风险"),
        )

        assertTrue(
            ProductCatalogScorer.score(carefulMatch, "敏感肌想找温和修护") >
                ProductCatalogScorer.score(riskyMatch, "敏感肌想找温和修护"),
        )
    }

    @Test
    fun scoreRewardsGeneratedTagsThatMatchTheUserNeed() {
        val tagged = product(
            id = "tagged",
            derivedAttributes = ProductDerivedAttributes(
                generatedTags = listOf(attribute("无酒精"), attribute("敏感肌"), attribute("通勤防晒")),
            ),
        )
        val generic = product(id = "generic")

        assertTrue(
            ProductCatalogScorer.score(tagged, "敏感肌想要无酒精通勤防晒") >
                ProductCatalogScorer.score(generic, "敏感肌想要无酒精通勤防晒"),
        )
    }

    private fun product(
        id: String,
        derivedAttributes: ProductDerivedAttributes = ProductDerivedAttributes(),
        positiveFeedbackSummary: List<String> = emptyList(),
        negativeFeedbackSummary: List<String> = emptyList(),
        riskTags: List<String> = emptyList(),
    ) = ProductUiModel(
        productId = id,
        name = "测试商品$id",
        price = 99.0,
        tags = listOf("测试"),
        reason = "用于测试推荐打分",
        derivedAttributes = derivedAttributes,
        positiveFeedbackSummary = positiveFeedbackSummary,
        negativeFeedbackSummary = negativeFeedbackSummary,
        riskTags = riskTags,
    )

    private fun attribute(value: String) = DerivedAttribute(value = value, evidence = value, confidence = 0.9)
}
