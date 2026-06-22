package com.example.shopguideagent.ui.component

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.SurfaceSoft

@Composable
fun ProductSkeletonCard(
    hero: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val transition = rememberInfiniteTransition(label = "productSkeletonPulse")
    val alpha by transition.animateFloat(
        initialValue = 0.5f,
        targetValue = 0.9f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1200),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "skeletonAlpha",
    )

    Surface(
        modifier = modifier.fillMaxWidth().alpha(alpha),
        color = SurfacePrimary,
        shape = RoundedCornerShape(AppCornerRadius.Card),
        border = BorderLight.let { androidx.compose.foundation.BorderStroke(1.dp, it) },
        tonalElevation = 1.dp,
        shadowElevation = 4.dp,
    ) {
        if (hero) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                SkeletonBlock(Modifier.fillMaxWidth().height(150.dp), AppCornerRadius.Card.value.toInt())
                SkeletonBlock(Modifier.fillMaxWidth(0.52f).height(18.dp), 8)
                SkeletonBlock(Modifier.fillMaxWidth(0.82f).height(16.dp), 8)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SkeletonBlock(Modifier.size(width = 64.dp, height = 28.dp), 999)
                    SkeletonBlock(Modifier.size(width = 72.dp, height = 28.dp), 999)
                    SkeletonBlock(Modifier.size(width = 58.dp, height = 28.dp), 999)
                }
                SkeletonBlock(Modifier.fillMaxWidth().height(42.dp), AppCornerRadius.Control.value.toInt())
            }
        } else {
            Column(
                modifier = Modifier.width(204.dp).padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                SkeletonBlock(Modifier.fillMaxWidth().height(108.dp), AppCornerRadius.Card.value.toInt())
                SkeletonBlock(Modifier.fillMaxWidth().height(14.dp), 8)
                SkeletonBlock(Modifier.fillMaxWidth(0.72f).height(14.dp), 8)
                SkeletonBlock(Modifier.width(72.dp).height(20.dp), 8)
            }
        }
    }
}

@Composable
private fun SkeletonBlock(modifier: Modifier, radius: Int) {
    Box(
        modifier = modifier.background(
            color = SurfaceSoft.copy(alpha = 0.85f),
            shape = RoundedCornerShape(radius.dp),
        ),
    )
}
