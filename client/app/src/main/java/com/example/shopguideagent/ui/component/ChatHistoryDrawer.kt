package com.example.shopguideagent.ui.component

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.config.PresetUser
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.history.ChatHistoryUiState
import com.example.shopguideagent.data.history.ChatSessionUiModel
import com.example.shopguideagent.ui.theme.AppBackground
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.DividerColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import com.example.shopguideagent.ui.theme.TextTertiary

@Composable
fun ChatHistoryDrawer(
    state: ChatHistoryUiState,
    currentUserId: String,
    userAvatarUri: String?,
    onNewSession: () -> Unit,
    onSelectSession: (ChatSessionUiModel) -> Unit,
    onDeleteSession: (ChatSessionUiModel) -> Unit,
    onUserSelected: (String) -> Unit,
    onAvatarChangeRequested: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxHeight()
            .width(304.dp),
        color = AppBackground,
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Header
            Text(
                text = "历史会话",
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleLarge,
            )

            // New session button
            Button(
                onClick = onNewSession,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(AppCornerRadius.Control),
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandPrimary,
                    contentColor = TextOnDark,
                ),
            ) {
                Icon(Icons.Outlined.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(6.dp))
                Text("新建会话")
            }

            Divider(color = DividerColor, thickness = 1.dp)

            if (state.sessions.isEmpty()) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Icon(
                        Icons.Outlined.ChatBubbleOutline,
                        contentDescription = null,
                        tint = TextTertiary,
                        modifier = Modifier.size(40.dp),
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "还没有历史会话",
                        color = TextSecondary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(
                        text = "发送第一条消息后会自动保存",
                        color = TextTertiary,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    itemsIndexed(state.sessions, key = { _, it -> it.sessionId }) { index, session ->
                        val staggerDelay = (index * 40).coerceAtMost(200)
                        AnimatedVisibility(
                            visible = true,
                            enter = fadeIn(tween(250, delayMillis = staggerDelay)) +
                                slideInVertically(tween(300, delayMillis = staggerDelay)) { it / 6 },
                        ) {
                            HistorySessionItem(
                                session = session,
                                selected = session.sessionId == state.currentSessionId,
                                onClick = { onSelectSession(session) },
                                onDelete = { onDeleteSession(session) },
                            )
                        }
                    }
                }
            }

            Divider(color = DividerColor, thickness = 1.dp)

            DrawerUserFooter(
                currentUserId = currentUserId,
                userAvatarUri = userAvatarUri,
                onUserSelected = onUserSelected,
                onAvatarChangeRequested = onAvatarChangeRequested,
            )
        }
    }
}

@Composable
private fun HistorySessionItem(
    session: ChatSessionUiModel,
    selected: Boolean,
    onClick: () -> Unit,
    onDelete: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickableWithScale(onClick),
        color = if (selected) BrandSoft else SurfacePrimary,
        shape = RoundedCornerShape(AppCornerRadius.Card),
        border = BorderStroke(1.dp, if (selected) BrandPrimary.copy(alpha = 0.3f) else BorderColor),
        tonalElevation = if (selected) 2.dp else 1.dp,
        shadowElevation = if (selected) 2.dp else 1.dp,
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                shape = CircleShape,
                color = if (selected) BrandPrimary else BrandSoft,
                modifier = Modifier.size(36.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Outlined.ChatBubbleOutline,
                        contentDescription = null,
                        tint = if (selected) TextOnDark else BrandPrimary,
                        modifier = Modifier.size(18.dp),
                    )
                }
            }
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(
                    text = session.title,
                    color = TextPrimary,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    text = "${session.messages.size} 条消息",
                    color = TextSecondary,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            IconButton(
                onClick = onDelete,
                modifier = Modifier.size(36.dp),
            ) {
                Icon(
                    Icons.Outlined.DeleteOutline,
                    contentDescription = "删除会话",
                    tint = TextTertiary,
                    modifier = Modifier.size(18.dp),
                )
            }
        }
    }
}

@Composable
private fun DrawerUserFooter(
    currentUserId: String,
    userAvatarUri: String?,
    onUserSelected: (String) -> Unit,
    onAvatarChangeRequested: () -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val currentUser = UserSession.PRESET_USERS.find { it.id == currentUserId }

    Box {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .clickableWithScale { expanded = true },
            color = SurfacePrimary,
            shape = RoundedCornerShape(AppCornerRadius.Card),
            border = BorderStroke(1.dp, BorderColor),
            tonalElevation = 1.dp,
            shadowElevation = 1.dp,
        ) {
            Row(
                modifier = Modifier.padding(14.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                AvatarView(
                    kind = AvatarKind.User,
                    avatarUri = userAvatarUri,
                    size = 44.dp,
                )
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(3.dp),
                ) {
                    Text(
                        text = currentUser?.displayName ?: "用户信息",
                        color = TextPrimary,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(
                        text = "点击切换用户",
                        color = TextSecondary,
                        style = MaterialTheme.typography.labelSmall,
                        maxLines = 1,
                    )
                }
                Icon(
                    imageVector = Icons.Outlined.ExpandMore,
                    contentDescription = "展开菜单",
                    tint = TextSecondary,
                    modifier = Modifier.size(20.dp),
                )
            }
        }

        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            UserSession.PRESET_USERS.forEach { user ->
                DropdownMenuItem(
                    text = {
                        Text(
                            text = "${user.displayName}${if (user.id == currentUserId) "（当前）" else ""}",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    },
                    onClick = {
                        expanded = false
                        if (user.id != currentUserId) {
                            onUserSelected(user.id)
                        }
                    },
                )
            }
            Divider()
            DropdownMenuItem(
                text = {
                    Text(
                        text = "点击更换头像",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                },
                onClick = {
                    expanded = false
                    onAvatarChangeRequested()
                },
            )
        }
    }
}
