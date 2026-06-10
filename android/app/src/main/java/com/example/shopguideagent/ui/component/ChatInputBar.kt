package com.example.shopguideagent.ui.component

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
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
import androidx.compose.material.icons.outlined.Close
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
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.SurfaceSecondary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import com.example.shopguideagent.ui.theme.TextTertiary
import com.example.shopguideagent.ui.theme.WarningColor
import com.example.shopguideagent.voice.VoiceInputUiState

object ChatInputTextPolicy {
    const val singleLine: Boolean = false
    const val minLines: Int = 1
    const val maxLines: Int = 5
}

object VoiceInputTextPolicy {
    const val cancelHint: String = "上滑取消"
    const val listeningHint: String = "正在聆听..."
}

@Composable
fun ChatInputBar(
    enabled: Boolean,
    onSend: (String) -> Unit,
    voiceState: VoiceInputUiState = VoiceInputUiState.Idle,
    voiceTranscript: String = "",
    recognitionState: VoiceRecognitionState = VoiceRecognitionState.Idle,
    recognitionMessage: String? = null,
    onVoicePress: () -> Unit = {},
    onVoiceDrag: (Float) -> Unit = {},
    onVoiceRelease: () -> Unit = {},
    speakerEnabled: Boolean = true,
    onSpeakerToggle: () -> Unit = {},
) {
    var input by remember { mutableStateOf("") }
    val keyboardController = LocalSoftwareKeyboardController.current
    val focusRequester = remember { FocusRequester() }
    val canSend = enabled && input.isNotBlank()

    fun submit() {
        val text = input.trim()
        if (text.isBlank() || !enabled) return
        input = ""
        onSend(text)
    }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .imePadding(),
        color = SurfacePrimary,
        border = BorderStroke(1.dp, BorderLight),
        shape = RoundedCornerShape(topStart = AppCornerRadius.Sheet, topEnd = AppCornerRadius.Sheet),
        tonalElevation = 0.dp,
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            AnimatedVisibility(
                visible = voiceState != VoiceInputUiState.Idle,
                enter = fadeIn(tween(150)) + slideInVertically(tween(200)) { it / 2 },
                exit = fadeOut(tween(120)) + slideOutVertically(tween(180)) { it / 2 },
            ) {
                VoiceCancelIndicator(
                    highlighted = voiceState == VoiceInputUiState.CancelPending,
                    modifier = Modifier.padding(top = 12.dp, bottom = 8.dp),
                )
            }
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
                    .heightIn(min = 68.dp)
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
                SpeakerToggle(
                    enabled = speakerEnabled,
                    onToggle = onSpeakerToggle,
                )
                if (voiceState == VoiceInputUiState.Idle) {
                    TextField(
                        value = input,
                        onValueChange = { input = it },
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 48.dp, max = 132.dp)
                            .animateContentSize()
                            .focusRequester(focusRequester)
                            .onFocusChanged { if (it.isFocused) keyboardController?.show() },
                        placeholder = { Text("说说你想买什么", color = TextTertiary) },
                        enabled = enabled,
                        singleLine = ChatInputTextPolicy.singleLine,
                        minLines = ChatInputTextPolicy.minLines,
                        maxLines = ChatInputTextPolicy.maxLines,
                        shape = RoundedCornerShape(AppCornerRadius.Input),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { submit() }),
                        colors = TextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedContainerColor = SurfaceSecondary,
                            unfocusedContainerColor = SurfaceSecondary,
                            disabledContainerColor = SurfaceSecondary,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            disabledIndicatorColor = Color.Transparent,
                            cursorColor = BrandPrimary,
                        ),
                    )
                } else {
                    VoiceWaveInput(
                        state = voiceState,
                        transcript = voiceTranscript,
                        modifier = Modifier.weight(1f),
                    )
                }
                Surface(
                    onClick = { submit() },
                    enabled = canSend,
                    modifier = Modifier.size(40.dp),
                    shape = CircleShape,
                    color = if (canSend) BrandPrimary else Color.Transparent,
                    contentColor = if (canSend) TextOnBrand else TextTertiary,
                    shadowElevation = if (canSend) 2.dp else 0.dp,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.AutoMirrored.Outlined.Send,
                            contentDescription = "发送",
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }
        }
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
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(150)) + slideInVertically(tween(180)) { it / 2 },
        exit = fadeOut(tween(120)) + slideOutVertically(tween(160)) { it / 2 },
    ) {
        val color = when (state) {
            VoiceRecognitionState.Failed,
            VoiceRecognitionState.Timeout -> WarningColor
            VoiceRecognitionState.Empty -> TextSecondary
            else -> BrandPrimary
        }
        Text(
            text = message.orEmpty(),
            color = color,
            style = MaterialTheme.typography.labelMedium,
            modifier = modifier,
        )
    }
}

@Composable
private fun VoiceHoldButton(
    enabled: Boolean,
    voiceState: VoiceInputUiState,
    onPress: () -> Unit,
    onDrag: (Float) -> Unit,
    onRelease: () -> Unit,
) {
    val active = voiceState != VoiceInputUiState.Idle
    val background = when (voiceState) {
        VoiceInputUiState.Idle -> BrandSoft
        VoiceInputUiState.Recording -> BrandPrimary
        VoiceInputUiState.CancelPending -> WarningColor
    }
    val tint = if (active) TextOnBrand else BrandPrimary

    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(if (enabled) background else SurfaceSecondary)
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
            modifier = Modifier.size(20.dp),
        )
    }
}

@Composable
private fun VoiceWaveInput(
    state: VoiceInputUiState,
    transcript: String,
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
    val color = if (state == VoiceInputUiState.CancelPending) WarningColor else BrandPrimary
    val prompt = when {
        state == VoiceInputUiState.CancelPending -> VoiceInputTextPolicy.cancelHint
        transcript.isNotBlank() -> transcript
        else -> VoiceInputTextPolicy.listeningHint
    }

    Surface(
        modifier = modifier.height(48.dp),
        shape = RoundedCornerShape(AppCornerRadius.Input),
        color = SurfaceSecondary,
        border = BorderStroke(1.dp, BorderLight),
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

@Composable
private fun VoiceCancelIndicator(
    highlighted: Boolean,
    modifier: Modifier = Modifier,
) {
    val scale by animateFloatAsState(
        targetValue = if (highlighted) 1.15f else 1f,
        animationSpec = tween(150),
        label = "cancelScale",
    )
    val color = if (highlighted) WarningColor else TextSecondary

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Surface(
            shape = CircleShape,
            color = if (highlighted) WarningColor.copy(alpha = 0.12f) else SurfaceSecondary,
            modifier = Modifier.scale(scale).size(52.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = Icons.Outlined.Close,
                    contentDescription = VoiceInputTextPolicy.cancelHint,
                    tint = color,
                    modifier = Modifier.size(26.dp),
                )
            }
        }
        Text(
            text = VoiceInputTextPolicy.cancelHint,
            color = color,
            style = MaterialTheme.typography.labelSmall,
        )
    }
}
