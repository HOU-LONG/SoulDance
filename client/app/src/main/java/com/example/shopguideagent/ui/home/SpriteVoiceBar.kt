package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.SpritePrimaryButton
import com.example.shopguideagent.ui.theme.SpriteVoiceBarBackground
import com.example.shopguideagent.ui.theme.SpriteVoiceBarTint
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import com.example.shopguideagent.ui.theme.TextTertiary
import com.example.shopguideagent.ui.theme.WarningColor
import com.example.shopguideagent.voice.VoiceInputUiState

/**
 * 精灵空间语音输入条。
 *
 * @param showTextInput 为 `true` 时显示完整输入条（语音 + 文字输入 + 发送）；
 *                      为 `false` 时仅显示按住说话的麦克风按钮，用于首页精简模式。
 */
@Composable
fun SpriteVoiceBar(
    enabled: Boolean,
    voiceState: VoiceInputUiState,
    recognitionState: VoiceRecognitionState,
    recognitionMessage: String?,
    onTextSubmit: (String) -> Unit,
    onVoicePress: () -> Unit,
    onVoiceDrag: (Float) -> Unit,
    onVoiceRelease: () -> Unit,
    modifier: Modifier = Modifier,
    showTextInput: Boolean = true,
) {
    if (showTextInput) {
        FullVoiceBar(
            enabled = enabled,
            voiceState = voiceState,
            recognitionState = recognitionState,
            recognitionMessage = recognitionMessage,
            onTextSubmit = onTextSubmit,
            onVoicePress = onVoicePress,
            onVoiceDrag = onVoiceDrag,
            onVoiceRelease = onVoiceRelease,
            modifier = modifier,
        )
    } else {
        CompactVoiceButton(
            enabled = enabled,
            voiceState = voiceState,
            recognitionState = recognitionState,
            recognitionMessage = recognitionMessage,
            onVoicePress = onVoicePress,
            onVoiceDrag = onVoiceDrag,
            onVoiceRelease = onVoiceRelease,
            modifier = modifier,
        )
    }
}

@Composable
private fun FullVoiceBar(
    enabled: Boolean,
    voiceState: VoiceInputUiState,
    recognitionState: VoiceRecognitionState,
    recognitionMessage: String?,
    onTextSubmit: (String) -> Unit,
    onVoicePress: () -> Unit,
    onVoiceDrag: (Float) -> Unit,
    onVoiceRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var input by remember { mutableStateOf("") }
    val canSend = enabled && input.isNotBlank() && voiceState == VoiceInputUiState.Idle

    fun submit() {
        val text = input.trim()
        if (text.isBlank() || !enabled) return
        input = ""
        onTextSubmit(text)
    }

    Surface(
        modifier = modifier
            .fillMaxWidth()
            .imePadding(),
        color = Color.White.copy(alpha = 0.72f),
        shape = RoundedCornerShape(34.dp),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.78f)),
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            VoiceRecognitionStatus(
                state = recognitionState,
                message = recognitionMessage,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp, vertical = 6.dp),
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 72.dp)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                VoiceHoldButton(
                    enabled = enabled,
                    voiceState = voiceState,
                    onPress = onVoicePress,
                    onDrag = onVoiceDrag,
                    onRelease = onVoiceRelease,
                )
                if (voiceState == VoiceInputUiState.Idle) {
                    TextField(
                        value = input,
                        onValueChange = { input = it },
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 48.dp, max = 120.dp)
                            .animateContentSize()
                            .clip(RoundedCornerShape(AppCornerRadius.Input)),
                        placeholder = { Text("说说你想买什么", color = TextTertiary) },
                        enabled = enabled,
                        singleLine = false,
                        minLines = 1,
                        maxLines = 4,
                        shape = RoundedCornerShape(AppCornerRadius.Input),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { submit() }),
                        colors = TextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedContainerColor = SpritePanel,
                            unfocusedContainerColor = SpritePanel,
                            disabledContainerColor = SpritePanel,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            disabledIndicatorColor = Color.Transparent,
                            cursorColor = SpriteVoiceBarBackground,
                        ),
                    )
                } else {
                    VoiceWaveInput(
                        state = voiceState,
                        modifier = Modifier.weight(1f),
                    )
                }
                Surface(
                    onClick = { submit() },
                    enabled = canSend,
                    modifier = Modifier.size(44.dp),
                    shape = CircleShape,
                    color = if (canSend) SpritePrimaryButton else Color.Transparent,
                    contentColor = if (canSend) SpriteVoiceBarBackground else TextTertiary,
                    shadowElevation = if (canSend) 2.dp else 0.dp,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.AutoMirrored.Outlined.Send,
                            contentDescription = "发送",
                            modifier = Modifier.size(22.dp),
                        )
                    }
                }
            }
        }
    }
}

/**
 * 精简版语音入口：仅保留按住说话的麦克风按钮，用于首页无文字输入模式。
 */
@Composable
private fun CompactVoiceButton(
    enabled: Boolean,
    voiceState: VoiceInputUiState,
    recognitionState: VoiceRecognitionState,
    recognitionMessage: String?,
    onVoicePress: () -> Unit,
    onVoiceDrag: (Float) -> Unit,
    onVoiceRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        VoiceRecognitionStatus(
            state = recognitionState,
            message = recognitionMessage,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp),
        )
        VoiceHoldButton(
            enabled = enabled,
            voiceState = voiceState,
            size = 56.dp,
            onPress = onVoicePress,
            onDrag = onVoiceDrag,
            onRelease = onVoiceRelease,
        )
    }
}

@Composable
private fun VoiceRecognitionStatus(
    state: VoiceRecognitionState,
    message: String?,
    modifier: Modifier = Modifier,
) {
    val visible = state == VoiceRecognitionState.Transcribing ||
        state == VoiceRecognitionState.Empty ||
        state == VoiceRecognitionState.Failed ||
        state == VoiceRecognitionState.Timeout
    if (!visible) return
    val color = when (state) {
        VoiceRecognitionState.Failed, VoiceRecognitionState.Timeout -> WarningColor
        VoiceRecognitionState.Empty -> TextSecondary
        else -> SpritePrimaryButton
    }
    Text(
        text = message.orEmpty(),
        color = color,
        style = MaterialTheme.typography.labelMedium,
        modifier = modifier,
    )
}

@Composable
private fun VoiceHoldButton(
    enabled: Boolean,
    voiceState: VoiceInputUiState,
    onPress: () -> Unit,
    onDrag: (Float) -> Unit,
    onRelease: () -> Unit,
    modifier: Modifier = Modifier,
    size: androidx.compose.ui.unit.Dp = 48.dp,
) {
    val active = voiceState != VoiceInputUiState.Idle
    val background = when (voiceState) {
        VoiceInputUiState.Idle -> SpritePrimaryButton
        VoiceInputUiState.Recording -> Color(0xFFFF6B6B)
        VoiceInputUiState.CancelPending -> WarningColor
    }
    val tint = if (active) Color.White else SpriteVoiceBarBackground

    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(if (enabled) background else SpritePanel)
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    onPress()
                    var totalDragY = 0f
                    do {
                        val event = awaitPointerEvent()
                        event.changes.forEach { change ->
                            totalDragY += change.positionChange().y
                            change.consume()
                        }
                        onDrag(totalDragY)
                    } while (event.changes.any { it.pressed })
                    onRelease()
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            Icons.Outlined.Mic,
            contentDescription = "按住说话",
            tint = tint,
            modifier = Modifier.size(size * 0.5f),
        )
    }
}

@Composable
private fun VoiceWaveInput(
    state: VoiceInputUiState,
    modifier: Modifier = Modifier,
) {
    val transition = rememberInfiniteTransition(label = "voiceWave")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 720),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "voiceWavePhase",
    )
    val color = if (state == VoiceInputUiState.CancelPending) WarningColor else SpritePrimaryButton
    val prompt = if (state == VoiceInputUiState.CancelPending) "上滑取消" else "正在聆听..."

    Surface(
        modifier = modifier.height(48.dp),
        shape = RoundedCornerShape(AppCornerRadius.Input),
        color = SpritePanel,
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.5f)),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.width(54.dp),
                horizontalArrangement = Arrangement.spacedBy(3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                repeat(5) { index ->
                    val height = 10.dp + (phase * (index + 1) * 2).dp
                    Box(
                        modifier = Modifier
                            .width(4.dp)
                            .height(height)
                            .clip(CircleShape)
                            .background(color),
                    )
                }
            }
            Text(
                prompt,
                color = if (state == VoiceInputUiState.CancelPending) WarningColor else TextPrimary,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteVoiceBarPreview() {
    ShopGuideAgentTheme {
        SpriteVoiceBar(
            enabled = true,
            voiceState = VoiceInputUiState.Idle,
            recognitionState = VoiceRecognitionState.Idle,
            recognitionMessage = null,
            onTextSubmit = {},
            onVoicePress = {},
            onVoiceDrag = {},
            onVoiceRelease = {},
        )
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun CompactVoiceButtonPreview() {
    ShopGuideAgentTheme {
        SpriteVoiceBar(
            enabled = true,
            voiceState = VoiceInputUiState.Idle,
            recognitionState = VoiceRecognitionState.Idle,
            recognitionMessage = null,
            onTextSubmit = {},
            onVoicePress = {},
            onVoiceDrag = {},
            onVoiceRelease = {},
            showTextInput = false,
        )
    }
}
