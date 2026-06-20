package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun SpeechBubble(
    text: String?,
    modifier: Modifier = Modifier,
) {
    AnimatedVisibility(
        visible = !text.isNullOrBlank(),
        enter = fadeIn(),
        exit = fadeOut(),
        modifier = modifier,
    ) {
        Box(contentAlignment = Alignment.BottomCenter) {
            Surface(
                shape = RoundedCornerShape(28.dp),
                color = Color.White.copy(alpha = 0.94f),
                shadowElevation = 8.dp,
                tonalElevation = 2.dp,
            ) {
                Text(
                    text = text.orEmpty(),
                    modifier = Modifier.padding(horizontal = 28.dp, vertical = 14.dp),
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                )
            }
            Surface(
                modifier = Modifier
                    .padding(bottom = 1.dp)
                    .size(18.dp)
                    .rotate(45f),
                color = Color.White.copy(alpha = 0.94f),
                shadowElevation = 0.dp,
            ) {}
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SpeechBubblePreview() {
    ShopGuideAgentTheme {
        SpeechBubble(text = "\u60f3\u6362\u65b0\u88c5\u626e")
    }
}
