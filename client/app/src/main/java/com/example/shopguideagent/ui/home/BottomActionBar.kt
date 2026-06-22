package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Checkroom
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.ErrorColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun BottomActionBar(
    earnedStars: Int,
    cartCount: Int,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        ActionButton(
            label = "装扮",
            icon = Icons.Outlined.Checkroom,
            testTag = "action_dress_up",
            onClick = { onAction(SpriteHomeAction.DressUpClicked) },
            modifier = Modifier.weight(1f),
        )
        EarnFireButton(
            earnedStars = earnedStars,
            onClick = { onAction(SpriteHomeAction.EarnFireClicked) },
            modifier = Modifier.weight(1.45f),
        )
        CartActionButton(
            count = cartCount,
            onClick = { onAction(SpriteHomeAction.CartClicked) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun ActionButton(
    label: String,
    icon: ImageVector,
    testTag: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(112.dp)
            .testTag(testTag)
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(34.dp),
        color = Color.White.copy(alpha = 0.58f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.7f)),
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(icon, contentDescription = null, tint = Color(0xFF5B422A), modifier = Modifier.size(36.dp))
            Spacer(Modifier.height(10.dp))
            Text(label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
        }
    }
}

@Composable
private fun CartActionButton(
    count: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(112.dp)
            .testTag("action_cart")
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(34.dp),
        color = Color.White.copy(alpha = 0.58f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.7f)),
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            BadgedBox(
                badge = {
                    if (count > 0) {
                        Badge(
                            containerColor = ErrorColor,
                            contentColor = TextOnDark,
                        ) {
                            Text(
                                count.coerceAtMost(99).toString(),
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                },
            ) {
                Icon(
                    Icons.Outlined.ShoppingCart,
                    contentDescription = null,
                    tint = Color(0xFF5B422A),
                    modifier = Modifier.size(36.dp),
                )
            }
            Spacer(Modifier.height(10.dp))
            Text("购物车", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
        }
    }
}

@Composable
private fun EarnFireButton(
    earnedStars: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(126.dp)
            .testTag("action_earn_fire")
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(36.dp),
        color = Color(0xFFFFF0BB),
        border = BorderStroke(1.5.dp, Color.White.copy(alpha = 0.9f)),
        shadowElevation = 12.dp,
    ) {
        Box(
            modifier = Modifier.background(
                Brush.radialGradient(
                    colors = listOf(Color(0xFFFFF4A9), Color(0xFFFFCC5C)),
                ),
            ),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    imageVector = Icons.Outlined.Star,
                    contentDescription = null,
                    tint = Color(0xFFFFD12F),
                    modifier = Modifier.size(48.dp),
                )
                Text("领火星", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = TextPrimary)
                Text(
                    text = "★ $earnedStars",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = TextSecondary,
                )
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun BottomActionBarPreview() {
    ShopGuideAgentTheme {
        BottomActionBar(earnedStars = 886, cartCount = 2, onAction = {})
    }
}
