package com.example.shopguideagent.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.VolumeOff
import androidx.compose.material.icons.outlined.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun SpeakerToggle(enabled: Boolean, onToggle: () -> Unit) {
    Surface(
        onClick = onToggle,
        shape = RoundedCornerShape(AppCornerRadius.Pill),
        color = if (enabled) BrandPrimary else SurfacePrimary,
        contentColor = if (enabled) TextOnBrand else TextSecondary,
        border = if (enabled) null else BorderStroke(1.dp, BorderLight),
        shadowElevation = if (enabled) 2.dp else 0.dp,
    ) {
        Icon(
            imageVector = if (enabled) Icons.Outlined.VolumeUp else Icons.Outlined.VolumeOff,
            contentDescription = if (enabled) "TTS 开启" else "TTS 关闭",
            modifier = Modifier
                .padding(horizontal = 12.dp, vertical = 8.dp)
                .size(18.dp),
        )
    }
}
