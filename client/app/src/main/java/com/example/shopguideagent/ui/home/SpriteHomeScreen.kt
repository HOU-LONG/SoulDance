package com.example.shopguideagent.ui.home

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.component.quickActionsForProduct
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpriteRoomBottom
import com.example.shopguideagent.ui.theme.SpriteRoomLight
import com.example.shopguideagent.ui.theme.SpriteRoomMiddle
import com.example.shopguideagent.ui.theme.SpriteRoomTop
import com.example.shopguideagent.voice.VoiceInputManager
import com.example.shopguideagent.voice.VoiceInputResult
import com.example.shopguideagent.voice.VoiceInputStateMachine
import com.example.shopguideagent.voice.VoiceInputUiState

@Composable
fun SpriteHomeScreen(
    state: SpriteHomeUiState,
    chatState: ChatUiState,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    val context = LocalContext.current
    val density = LocalDensity.current
    var voiceState by remember { mutableStateOf(VoiceInputUiState.Idle) }
    val voiceStateMachine = remember(density) {
        with(density) {
            VoiceInputStateMachine(cancelThresholdPx = (-80).dp.toPx())
        }
    }

    val voiceManager = remember(context) {
        VoiceInputManager(
            context = context.applicationContext,
            onAmplitude = { /* TODO: wire to waveform if desired */ },
            onFinished = { file ->
                voiceState = VoiceInputUiState.Idle
                onAction(SpriteHomeAction.VoiceFileReady(file))
            },
            onError = { message ->
                voiceState = VoiceInputUiState.Idle
                onAction(SpriteHomeAction.SettingsClicked) // placeholder for error toast
            },
        )
    }

    fun beginVoiceRecording() {
        onAction(SpriteHomeAction.VoiceRecordingStarted)
        voiceState = voiceStateMachine.onPress()
        voiceManager.startRecording()
    }

    val voicePermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            beginVoiceRecording()
        } else {
            onAction(SpriteHomeAction.SettingsClicked) // placeholder
        }
    }

    DisposableEffect(voiceManager) {
        onDispose { voiceManager.release() }
    }

    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
            .testTag("sprite_home")
            .background(RoomBackgroundBrush),
    ) {
        RoomBackgroundDecorations()
        val compact = maxHeight < 720.dp
        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding(),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            SpriteTopBar(
                cartCount = chatState.cartBadgeCount,
                onSettingsClick = { onAction(SpriteHomeAction.SettingsClicked) },
                onChatModeClick = { onAction(SpriteHomeAction.ChatModeClicked) },
                onCartClick = { onAction(SpriteHomeAction.CartClicked) },
            )

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(horizontal = 18.dp),
            ) {
                avatarStage(
                    state.toAvatarStageUiState(),
                    Modifier
                        .align(Alignment.Center)
                        .fillMaxWidth()
                        .height(if (compact) 360.dp else 440.dp),
                )
            }

            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                AnimatedVisibility(visible = state.productPresentation.primaryProduct == null) {
                    IntimacyPanel(
                        spriteName = state.spiritProgress.spiritName,
                        level = state.spiritProgress.level,
                        intimacy = state.spiritProgress.currentIntimacy,
                        intimacyMax = state.spiritProgress.requiredIntimacy,
                        subtitle = state.spiritProgress.subtitle,
                        intimacyLabel = state.spiritProgress.intimacyLabel,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 18.dp, vertical = 8.dp),
                    )
                }
                ProductPresentationSheet(
                    primaryProduct = state.productPresentation.primaryProduct,
                    alternatives = state.productPresentation.alternatives,
                    expectedCount = state.productPresentation.expectedCount,
                    receivedCount = state.productPresentation.receivedCount,
                    completed = state.productPresentation.completed,
                    quickActions = quickActionsForPresentation(state),
                    onProductClick = { onAction(SpriteHomeAction.ProductDetailClicked(it)) },
                    onAddToCart = { onAction(SpriteHomeAction.AddToCartClicked(it)) },
                    onQuickAction = { onAction(SpriteHomeAction.QuickActionClicked(it)) },
                )
                SpriteVoiceBar(
                    enabled = !chatState.isSending,
                    voiceState = voiceState,
                    recognitionState = chatState.voiceRecognitionState,
                    recognitionMessage = chatState.voiceRecognitionMessage,
                    speakerEnabled = chatState.isSpeakerEnabled,
                    onTextSubmit = { onAction(SpriteHomeAction.TextSubmitted(it)) },
                    onVoicePress = {
                        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                            PackageManager.PERMISSION_GRANTED
                        ) {
                            beginVoiceRecording()
                        } else {
                            voicePermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                    onVoiceDrag = { dragY ->
                        voiceState = voiceStateMachine.onDrag(dragY)
                    },
                    onVoiceRelease = {
                        when (voiceStateMachine.onRelease()) {
                            VoiceInputResult.Submit -> voiceManager.finishRecording()
                            VoiceInputResult.Cancel -> {
                                voiceManager.cancelRecording()
                                onAction(SpriteHomeAction.VoiceRecordingCancelled)
                            }
                            VoiceInputResult.None -> Unit
                        }
                        voiceState = VoiceInputUiState.Idle
                    },
                    onSpeakerToggle = { onAction(SpriteHomeAction.SpeakerToggled) },
                )
            }
        }
    }
}

private fun quickActionsForPresentation(state: SpriteHomeUiState): List<QuickActionUiModel> {
    val product = state.productPresentation.primaryProduct ?: state.presentingProduct
    return quickActionsForProduct(product)
}

private val RoomBackgroundBrush = Brush.verticalGradient(
    colors = listOf(SpriteRoomTop, SpriteRoomMiddle, SpriteRoomLight, SpriteRoomBottom),
)

@Composable
private fun RoomBackgroundDecorations() {
    Box(modifier = Modifier.fillMaxSize()) {
        Box(
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(start = 0.dp, top = 80.dp)
                .size(230.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.16f)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .padding(top = 150.dp)
                .size(width = 260.dp, height = 170.dp)
                .clip(RoundedCornerShape(42.dp))
                .background(Color.White.copy(alpha = 0.12f)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 210.dp)
                .size(width = 340.dp, height = 74.dp)
                .clip(CircleShape)
                .background(Color(0x33FFF8E1)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .padding(end = (-52).dp, top = (-40).dp)
                .size(160.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.13f)),
        )
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenIdlePreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomePreviewData.idle,
            chatState = ChatUiState(),
            onAction = {},
        )
    }
}
