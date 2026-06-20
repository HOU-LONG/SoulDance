package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun NewOutfitHintCard(
    state: NewOutfitHintUiState,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .testTag("new_outfit_hint")
            .clickableWithScale { onAction(SpriteHomeAction.NewOutfitClicked) },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(contentAlignment = Alignment.TopEnd) {
            Surface(
                modifier = Modifier.size(82.dp),
                shape = RoundedCornerShape(24.dp),
                color = Color(0xFF8FD1FF),
                border = BorderStroke(1.dp, Color.White.copy(alpha = 0.85f)),
                shadowElevation = 9.dp,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Outlined.ShoppingCart, contentDescription = null, tint = Color.White, modifier = Modifier.size(42.dp))
                }
            }
            Text(
                text = state.badge,
                modifier = Modifier
                    .offset(x = 10.dp, y = (-8).dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(Color(0xFFFF4B45))
                    .padding(horizontal = 8.dp, vertical = 5.dp),
                color = TextOnBrand,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
            )
        }
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = Color(0xFFFFF1AF),
            shadowElevation = 4.dp,
            modifier = Modifier.padding(top = 6.dp),
        ) {
            Text(
                text = state.title,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                color = TextPrimary,
                style = MaterialTheme.typography.labelLarge,
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun NewOutfitHintCardPreview() {
    ShopGuideAgentTheme {
        NewOutfitHintCard(NewOutfitHintUiState(), onAction = {})
    }
}
