package com.example.shopguideagent.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
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
import androidx.compose.ui.draw.clip
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

@Composable
fun BottomActionBar(
    firePoints: Int,
    cartCount: Int,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        HomeActionButton(
            label = "装扮",
            icon = Icons.Outlined.Checkroom,
            testTag = "action_dress_up",
            accentColor = Color(0xFFC084D4),
            onClick = { onAction(SpriteHomeAction.DressUpClicked) },
            modifier = Modifier.weight(1f),
        )
        EarnFireButton(
            firePoints = firePoints,
            onClick = { onAction(SpriteHomeAction.EarnFireClicked) },
            modifier = Modifier.weight(1f),
        )
        CartActionButton(
            count = cartCount,
            onClick = { onAction(SpriteHomeAction.CartClicked) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun HomeActionButton(
    label: String,
    icon: ImageVector,
    testTag: String,
    accentColor: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    badge: @Composable (() -> Unit)? = null,
) {
    Surface(
        modifier = modifier
            .height(44.dp)
            .testTag(testTag)
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(999.dp),
        color = Color(0xFF2A1F1A).copy(alpha = 0.72f),
        shadowElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
        ) {
            Box(contentAlignment = Alignment.Center) {
                if (badge != null) {
                    BadgedBox(
                        badge = { badge() },
                        modifier = Modifier.size(18.dp),
                    ) {
                        Icon(
                            imageVector = icon,
                            contentDescription = null,
                            tint = TextOnDark,
                            modifier = Modifier.size(18.dp),
                        )
                    }
                } else {
                    Icon(
                        imageVector = icon,
                        contentDescription = null,
                        tint = TextOnDark,
                        modifier = Modifier.size(18.dp),
                    )
                }
                // 彩色标识点
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .offset(x = 3.dp, y = (-3).dp)
                        .size(6.dp)
                        .clip(CircleShape)
                        .background(accentColor),
                )
            }
            Text(
                text = label,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = TextOnDark,
            )
        }
    }
}

@Composable
private fun EarnFireButton(
    firePoints: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    HomeActionButton(
        label = "领火星",
        icon = Icons.Outlined.Star,
        testTag = "action_earn_fire",
        accentColor = Color(0xFFF4B942),
        onClick = onClick,
        modifier = modifier,
    ) {
        Text(
            text = firePoints.coerceAtLeast(0).toString(),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = TextPrimary,
            modifier = Modifier
                .offset(x = (-2).dp, y = (-2).dp)
                .clip(RoundedCornerShape(999.dp))
                .background(Color(0xFFFFF4A9))
                .padding(horizontal = 4.dp, vertical = 1.dp),
        )
    }
}

@Composable
private fun CartActionButton(
    count: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    HomeActionButton(
        label = "购物车",
        icon = Icons.Outlined.ShoppingCart,
        testTag = "action_cart",
        accentColor = Color(0xFF7BC67E),
        onClick = onClick,
        modifier = modifier,
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
    )
}

@Preview(showBackground = true)
@Composable
private fun BottomActionBarPreview() {
    ShopGuideAgentTheme {
        BottomActionBar(firePoints = 886, cartCount = 2, onAction = {})
    }
}
