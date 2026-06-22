package com.example.shopguideagent.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.home.FireRewardCalculator
import com.example.shopguideagent.ui.theme.PriceColor

@Composable
fun FireDiscountLabel(
    firePoints: Int,
    price: Double,
    modifier: Modifier = Modifier,
) {
    val discount = FireRewardCalculator.discountAmount(firePoints, price)
    if (discount <= 0) return
    Text(
        text = "可用 ⭐ 抵扣 ¥${"%.2f".format(discount)}",
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(PriceColor.copy(alpha = 0.12f))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        color = PriceColor,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
    )
}
