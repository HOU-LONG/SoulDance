package com.example.shopguideagent.ui.home

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.history.ChatHistoryUiState
import com.example.shopguideagent.data.history.ChatSessionUiModel
import com.example.shopguideagent.ui.component.ChatHistoryDrawer
import com.example.shopguideagent.data.model.ChatUiState
import kotlinx.coroutines.launch

@Composable
fun SpriteHomeRoute(
    viewModel: SpriteHomeViewModel,
    chatUiState: ChatUiState,
    historyState: ChatHistoryUiState,
    currentUserId: String,
    userAvatarUri: String?,
    onEffect: (SpriteHomeEffect) -> Unit,
    onSwitchUser: (String) -> Unit,
    onUserSelected: (String) -> Unit,
    onAvatarChangeRequested: () -> Unit,
    onNewSession: () -> Unit,
    onSelectSession: (ChatSessionUiModel) -> Unit,
    onDeleteSession: (ChatSessionUiModel) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    val state by viewModel.uiState.collectAsState()
    var showTaskCenter by remember { mutableStateOf(false) }
    var showEditNameDialog by remember { mutableStateOf(false) }
    var editedName by remember(state.spiritProgress.spiritName) { mutableStateOf(state.spiritProgress.spiritName) }
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) {
        viewModel.effects.collect { effect ->
            when (effect) {
                is SpriteHomeEffect.ShowTaskCenter -> showTaskCenter = true
                is SpriteHomeEffect.HideTaskCenter -> showTaskCenter = false
                is SpriteHomeEffect.OpenHistoryDrawer -> scope.launch { drawerState.open() }
                is SpriteHomeEffect.SwitchUser -> {
                    scope.launch { drawerState.close() }
                    onSwitchUser(effect.userId)
                }
                is SpriteHomeEffect.SelectSession -> {
                    scope.launch { drawerState.close() }
                    val session = historyState.sessions.find { it.sessionId == effect.sessionId }
                    session?.let { onSelectSession(it) }
                }
                SpriteHomeEffect.CreateNewSession -> {
                    scope.launch { drawerState.close() }
                    onNewSession()
                }
                SpriteHomeEffect.ShowEditSpiritName -> {
                    editedName = state.spiritProgress.spiritName
                    showEditNameDialog = true
                }
                else -> onEffect(effect)
            }
        }
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ChatHistoryDrawer(
                state = historyState,
                currentUserId = currentUserId,
                userAvatarUri = userAvatarUri,
                onNewSession = { viewModel.onAction(SpriteHomeAction.NewSessionRequested) },
                onSelectSession = { viewModel.onAction(SpriteHomeAction.SessionSelected(it.sessionId)) },
                onDeleteSession = onDeleteSession,
                onUserSelected = { viewModel.onAction(SpriteHomeAction.UserSelected(it)) },
                onAvatarChangeRequested = onAvatarChangeRequested,
            )
        },
        modifier = modifier,
    ) {
        SpriteHomeScreen(
            state = state,
            chatState = chatUiState,
            onAction = viewModel::onAction,
            avatarStage = avatarStage,
        )
    }

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

    if (showEditNameDialog) {
        AlertDialog(
            onDismissRequest = { showEditNameDialog = false },
            icon = { Icon(Icons.Outlined.Edit, contentDescription = null) },
            title = { Text("给精灵换个名字") },
            text = {
                OutlinedTextField(
                    value = editedName,
                    onValueChange = { editedName = it },
                    label = { Text("精灵名字") },
                    singleLine = true,
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.onAction(SpriteHomeAction.SpiritNameChanged(editedName))
                        showEditNameDialog = false
                    },
                ) {
                    Text("保存")
                }
            },
            dismissButton = {
                TextButton(onClick = { showEditNameDialog = false }) {
                    Text("取消")
                }
            },
        )
    }
}
