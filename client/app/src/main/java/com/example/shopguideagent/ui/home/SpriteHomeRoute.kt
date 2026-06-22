package com.example.shopguideagent.ui.home

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.example.shopguideagent.data.model.ChatUiState

@Composable
fun SpriteHomeRoute(
    viewModel: SpriteHomeViewModel,
    chatUiState: ChatUiState,
    onEffect: (SpriteHomeEffect) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    val state by viewModel.uiState.collectAsState()
    var showTaskCenter by remember { mutableStateOf(false) }

    LaunchedEffect(viewModel) {
        viewModel.effects.collect { effect ->
            when (effect) {
                is SpriteHomeEffect.ShowTaskCenter -> showTaskCenter = true
                is SpriteHomeEffect.HideTaskCenter -> showTaskCenter = false
                else -> onEffect(effect)
            }
        }
    }

    SpriteHomeScreen(
        state = state,
        chatState = chatUiState,
        onAction = viewModel::onAction,
        modifier = modifier,
        avatarStage = avatarStage,
    )

    if (showTaskCenter) {
        TaskCenterBottomSheet(
            tasks = state.tasks,
            firePoints = state.userProfile.firePoints,
            level = state.spiritProgress.level,
            onClaim = { taskId -> viewModel.onAction(SpriteHomeAction.TaskClaimed(taskId)) },
            onDismiss = {
                showTaskCenter = false
                viewModel.onAction(SpriteHomeAction.TaskCenterClosed)
            },
        )
    }
}
