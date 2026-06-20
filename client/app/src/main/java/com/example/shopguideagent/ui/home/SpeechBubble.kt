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
    state: SpeechBubbleUiState,
    modifier: Modifier = Modifier,
) {
    AnimatedVisibility(
        visible = state.visible && state.text.isNotBlank(),
        enter = fadeIn(),
        exit = fadeOut(),
        modifier = modifier,
    ) {
        val bubbleColor = when (state.style) {
            SpeechBubbleStyle.ERROR -> Color(0xFFFFF1F0)
            SpeechBubbleStyle.SUCCESS -> Color(0xFFFFFAE8)
            else -> Color.White.copy(alpha = 0.94f)
        }
        Box(contentAlignment = Alignment.BottomCenter) {
            Surface(
                shape = RoundedCornerShape(28.dp),
                color = bubbleColor,
                shadowElevation = 8.dp,
                tonalElevation = 2.dp,
            ) {
                Text(
                    text = state.text,
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
                color = bubbleColor,
                shadowElevation = 0.dp,
            ) {}
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SpeechBubblePreview() {
    ShopGuideAgentTheme {
        SpeechBubble(state = SpeechBubbleUiState("想换新装扮"))
    }
}

@Preview(showBackground = true)
@Composable
private fun SpeechBubbleErrorPreview() {
    ShopGuideAgentTheme {
        SpeechBubble(state = SpeechBubbleUiState("刚才没听清", style = SpeechBubbleStyle.ERROR))
    }
}
