package com.example.shopguideagent.ui.component

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun MessageBubble(
    message: ChatMessageUiModel,
    userAvatarUri: String?,
    onUserAvatarClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val isUser = message.role == MessageRole.User
    Column(
        modifier = modifier,
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start,
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Surface(
            modifier = Modifier
                .widthIn(max = 420.dp)
                .animateContentSize(
                    animationSpec = spring(
                        dampingRatio = Spring.DampingRatioMediumBouncy,
                        stiffness = Spring.StiffnessLow,
                    ),
                ),
            color = if (isUser) BrandPrimary else SurfacePrimary,
            contentColor = if (isUser) TextOnBrand else TextPrimary,
            shape = RoundedCornerShape(
                topStart = AppCornerRadius.Card,
                topEnd = AppCornerRadius.Card,
                bottomStart = if (isUser) AppCornerRadius.Card else 4.dp,
                bottomEnd = if (isUser) 4.dp else AppCornerRadius.Card,
            ),
            border = if (isUser) null else BorderStroke(1.dp, BorderLight),
            tonalElevation = if (isUser) 0.dp else 1.dp,
            shadowElevation = if (isUser) 2.dp else 3.dp,
        ) {
            SelectionContainer {
                val fallback = if (message.isStreaming) "我正在帮你整理推荐..." else ""
                Text(
                    text = renderMarkdownText(
                        markdown = message.text,
                        fallback = fallback,
                        autoSegment = !isUser,
                    ),
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                    style = MaterialTheme.typography.bodyMedium.copy(
                        lineHeightStyle = LineHeightStyle(
                            alignment = LineHeightStyle.Alignment.Center,
                            trim = LineHeightStyle.Trim.None,
                        ),
                    ),
                )
            }
        }
    }
}
