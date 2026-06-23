package com.example.shopguideagent.ui.home

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.ui.component.quickActionsForProduct
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
            onAmplitude = { /* 可接入波形动画 */ },
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

    Column(
        modifier = modifier
            .fillMaxSize()
            .testTag("sprite_home")
            .safeDrawingPadding()
            .background(RoomBackgroundBrush),
    ) {
        SpriteTopBar(
            userProfile = state.userProfile,
            speakerEnabled = chatState.isSpeakerEnabled,
            onSpeakerToggle = { onAction(SpriteHomeAction.SpeakerToggled) },
            onChatClick = { onAction(SpriteHomeAction.ChatModeClicked) },
        )

        BoxWithConstraints(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .padding(horizontal = 18.dp),
        ) {
            val compact = maxHeight < 720.dp
            avatarStage(
                state.toAvatarStageUiState(),
                Modifier
                    .align(Alignment.Center)
                    .fillMaxWidth()
                    .height(if (compact) 340.dp else 420.dp),
            )

            ProductPresentationSheet(
                primaryProduct = state.productPresentation.primaryProduct,
                alternatives = state.productPresentation.alternatives,
                expectedCount = state.productPresentation.expectedCount,
                receivedCount = state.productPresentation.receivedCount,
                completed = state.productPresentation.completed,
                quickActions = quickActionsForPresentation(state),
                firePoints = state.userProfile.firePoints,
                onProductClick = { onAction(SpriteHomeAction.ProductDetailClicked(it)) },
                onAddToCart = { onAction(SpriteHomeAction.AddToCartClicked(it)) },
                onQuickAction = { onAction(SpriteHomeAction.QuickActionClicked(it)) },
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 12.dp),
            )
        }

        IntimacyPanel(
            spriteName = state.spiritProgress.spiritName,
            level = state.spiritProgress.level,
            intimacy = state.spiritProgress.currentIntimacy,
            intimacyMax = state.spiritProgress.requiredIntimacy,
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 18.dp, top = 4.dp, end = 18.dp, bottom = 8.dp),
        )

        BottomActionBar(
            earnedStars = state.earnedStars,
            cartCount = chatState.cartBadgeCount,
            onAction = onAction,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
        )

        SpriteVoiceBar(
            enabled = !chatState.isSending,
            voiceState = voiceState,
            recognitionState = chatState.voiceRecognitionState,
            recognitionMessage = chatState.voiceRecognitionMessage,
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
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, top = 10.dp, end = 16.dp, bottom = 12.dp),
        )
    }
}

private fun quickActionsForPresentation(state: SpriteHomeUiState) =
    quickActionsForProduct(state.productPresentation.primaryProduct ?: state.presentingProduct)

private val RoomBackgroundBrush = Brush.verticalGradient(
    colors = listOf(SpriteRoomTop, SpriteRoomMiddle, SpriteRoomLight, SpriteRoomBottom),
)

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
