package com.example.shopguideagent.ui.home

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.TextPrimary
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
                onAction(SpriteHomeAction.VoiceError(message))
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
            onAction(SpriteHomeAction.VoiceError("需要麦克风权限才能语音输入，请在系统设置中开启"))
        }
    }

    DisposableEffect(voiceManager) {
        onDispose { voiceManager.release() }
    }

    val onVoicePress = {
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            beginVoiceRecording()
        } else {
            voicePermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .testTag("sprite_home"),
    ) {
        // 底层：全屏环境（背景 + 远景道具）
        SpriteRoomBackdrop(
            backgroundId = state.appearance.backgroundId,
            modifier = Modifier.fillMaxSize(),
        )

        // 浮层：顶栏 + 中央舞台 + 底部 UI，约束在系统安全区内
        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding(),
        ) {
            SpriteTopBar(
                userAvatarUri = state.userProfile.avatarUrl,
                speakerEnabled = chatState.isSpeakerEnabled,
                onSpeakerToggle = { onAction(SpriteHomeAction.SpeakerToggled) },
                onChatClick = { onAction(SpriteHomeAction.ChatModeClicked) },
                onHistoryClick = { onAction(SpriteHomeAction.HistoryDrawerOpened) },
                cartBadgeCount = chatState.cartBadgeCount,
                onWardrobeClick = { onAction(SpriteHomeAction.DressUpClicked) },
                onCartClick = { onAction(SpriteHomeAction.CartClicked) },
            )

            val palmProduct = state.productPresentation.primaryProduct ?: state.presentingProduct
            SpriteStageArea(
                stageState = state.toAvatarStageUiState(),
                avatarStage = avatarStage,
                palmProduct = palmProduct,
                palmProductLoading = state.productPresentation.expectedCount > 0 && palmProduct == null,
                palmProductExpanded = palmProduct?.productId == state.palmExpandedProductId,
                onPalmProductClick = { onAction(SpriteHomeAction.PalmProductClicked(it)) },
                onPalmProductDismiss = { onAction(SpriteHomeAction.PalmProductPanelDismissed) },
                onAddToCart = { onAction(SpriteHomeAction.AddToCartClicked(it)) },
                onRefineProduct = { onAction(SpriteHomeAction.QuickActionClicked(it)) },
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
            )

            // 可编辑的精灵名字徽章
            EditableSpiritName(
                name = state.spiritProgress.spiritName,
                onClick = { onAction(SpriteHomeAction.EditSpiritNameClicked) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 6.dp),
            )

            // Task 12: BottomActionBar 已移除——衣橱和购物车入口迁移至 SpriteTopBar
            DailyTaskBar(
                state = state.primaryDailyTask(),
                onAction = onAction,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 8.dp),
            )

            SpriteVoiceBar(
                enabled = !chatState.isSending,
                voiceState = voiceState,
                recognitionState = chatState.voiceRecognitionState,
                recognitionMessage = chatState.voiceRecognitionMessage,
                onTextSubmit = { onAction(SpriteHomeAction.TextSubmitted(it)) },
                onVoicePress = onVoicePress,
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
                    .padding(start = 16.dp, end = 16.dp, bottom = 12.dp),
                showTextInput = false,
            )
        }
    }
}

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

/** 可点击的精灵名字徽章：点击后通知上层打开编辑对话框。 */
@Composable
private fun EditableSpiritName(
    name: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier,
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.Center,
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Surface(
            onClick = onClick,
            modifier = Modifier.clickableWithScale(onClick),
            shape = RoundedCornerShape(999.dp),
            color = SpritePanel.copy(alpha = 0.78f),
            shadowElevation = 2.dp,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(6.dp),
            ) {
                Text(
                    text = name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                )
            }
        }
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
