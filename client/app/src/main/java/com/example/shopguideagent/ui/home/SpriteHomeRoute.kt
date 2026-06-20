package com.example.shopguideagent.ui.home

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier

@Composable
fun SpriteHomeRoute(
    viewModel: SpriteHomeViewModel,
    onEffect: (SpriteHomeEffect) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(viewModel) {
        viewModel.effects.collect { onEffect(it) }
    }

    SpriteHomeScreen(
        state = state,
        onAction = viewModel::onAction,
        modifier = modifier,
        avatarStage = avatarStage,
    )
}
