package com.example.shopguideagent.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.theme.BrandBorder
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.SurfaceElevated
import com.example.shopguideagent.ui.theme.TextOnBrand

enum class AvatarKind {
    Ai,
    User,
}

@Composable
fun AvatarView(
    kind: AvatarKind,
    avatarUri: String? = null,
    modifier: Modifier = Modifier,
    size: Dp = 40.dp,
    onClick: (() -> Unit)? = null,
) {
    val clickableModifier = if (onClick != null) {
        Modifier.clickableWithScale(onClick)
    } else {
        Modifier
    }

    Surface(
        modifier = modifier
            .size(size)
            .then(clickableModifier),
        shape = CircleShape,
        border = BorderStroke(1.5.dp, if (kind == AvatarKind.Ai) BrandBorder else BrandPrimary.copy(alpha = 0.3f)),
        color = if (kind == AvatarKind.Ai) SurfaceElevated else BrandPrimary,
        tonalElevation = 2.dp,
        shadowElevation = if (kind == AvatarKind.Ai) 2.dp else 0.dp,
    ) {
        if (kind == AvatarKind.Ai) {
            Image(
                painter = painterResource(R.drawable.shopping),
                contentDescription = "AI 导购头像",
                modifier = Modifier.clip(CircleShape),
                contentScale = ContentScale.Crop,
            )
        } else if (!avatarUri.isNullOrBlank()) {
            AsyncImage(
                model = avatarUri,
                contentDescription = "用户头像",
                modifier = Modifier.clip(CircleShape),
                contentScale = ContentScale.Crop,
            )
        } else {
            Box(
                modifier = Modifier.background(BrandPrimary),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Outlined.Person,
                    contentDescription = "选择头像",
                    tint = TextOnBrand,
                )
            }
        }
    }
}
