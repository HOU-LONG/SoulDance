package com.example.shopguideagent.ui.home

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.ui.component.quickActionsForProduct
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
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

    Box(
        modifier = modifier
            .fillMaxSize()
            .testTag("sprite_home"),
    ) {
        // 底层：全屏环境（背景 + 远景道具）
        SpriteRoomBackdrop(modifier = Modifier.fillMaxSize())

        // 浮层：顶栏 + 中央舞台 + 底部 UI，约束在系统安全区内
        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding(),
        ) {
            SpriteTopBar(
                userProfile = state.userProfile,
                speakerEnabled = chatState.isSpeakerEnabled,
                onSpeakerToggle = { onAction(SpriteHomeAction.SpeakerToggled) },
                onChatClick = { onAction(SpriteHomeAction.ChatModeClicked) },
            )

            SpriteStageArea(
                stageState = state.toAvatarStageUiState(),
                avatarStage = avatarStage,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
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
                    .fillMaxWidth()
                    .padding(bottom = 10.dp),
            )

            IntimacyPanel(
                spriteName = state.spiritProgress.spiritName,
                level = state.spiritProgress.level,
                intimacy = state.spiritProgress.currentIntimacy,
                intimacyMax = state.spiritProgress.requiredIntimacy,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 18.dp, end = 18.dp, bottom = 8.dp),
            )

            DailyTaskBar(
                state = state.primaryDailyTask(),
                onAction = onAction,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 16.dp, end = 16.dp, bottom = 8.dp),
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
}

private fun quickActionsForPresentation(state: SpriteHomeUiState) =
    quickActionsForProduct(state.productPresentation.primaryProduct ?: state.presentingProduct)

/** 从任务列表取主每日任务，映射到任务栏所需的展示模型。 */
private fun SpriteHomeUiState.primaryDailyTask(): DailyTaskUiState {
    val task = tasks.firstOrNull { it.taskId == "daily_guide_chat" } ?: tasks.firstOrNull()
    return if (task == null) {
        DailyTaskUiState()
    } else {
        DailyTaskUiState(
            taskId = task.taskId,
            title = task.title,
            description = task.description,
            currentCount = task.currentCount,
            targetCount = task.targetCount,
            rewardFirePoints = task.baseFireReward,
            completed = task.completed,
            claimed = task.claimed,
        )
    }
}

@Preview(name = "Home IDLE 360", showBackground = true, widthDp = 360, heightDp = 800)
@Composable
private fun SpriteHomeScreenIdle360Preview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomePreviewData.idle,
            chatState = ChatUiState(),
            onAction = {},
        )
    }
}

@Preview(name = "Home SEARCHING 393", showBackground = true, widthDp = 393, heightDp = 873)
@Composable
private fun SpriteHomeScreenSearching393Preview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomePreviewData.searching,
            chatState = ChatUiState(),
            onAction = {},
        )
    }
}

@Preview(name = "Home PRESENTING 412", showBackground = true, widthDp = 412, heightDp = 915)
@Composable
private fun SpriteHomeScreenPresenting412Preview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomePreviewData.presenting,
            chatState = ChatUiState(),
            onAction = {},
        )
    }
}
