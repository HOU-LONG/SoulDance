package com.example.shopguideagent.ui.component

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.ErrorColor
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnDark
import kotlinx.coroutines.delay

@Composable
fun CartBadge(count: Int, onClick: () -> Unit) {
    var bumped by remember { mutableStateOf(false) }
    var previousCount by remember { mutableStateOf(count) }
    val scale by animateFloatAsState(
        targetValue = if (bumped) 1.2f else 1f,
        animationSpec = tween(durationMillis = 200),
        label = "cartBadgeScale",
    )

    LaunchedEffect(count) {
        if (count > 0 && count != previousCount) {
            bumped = true
            delay(200)
            bumped = false
        }
        previousCount = count
    }

    BadgedBox(
        modifier = Modifier.padding(end = 8.dp),
        badge = {
            if (count > 0) {
                Badge(
                    modifier = Modifier.scale(scale),
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
        Surface(
            modifier = Modifier.clickableWithScale(onClick),
            color = SurfacePrimary,
            shape = RoundedCornerShape(AppCornerRadius.Pill),
            border = BorderStroke(1.dp, BorderLight),
            tonalElevation = 1.dp,
            shadowElevation = 2.dp,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Outlined.ShoppingCart,
                    contentDescription = "购物车",
                    tint = BrandPrimary,
                    modifier = Modifier.size(20.dp),
                )
            }
        }
    }
}
