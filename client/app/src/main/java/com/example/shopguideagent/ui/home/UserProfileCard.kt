package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import com.example.shopguideagent.ui.theme.TextOnBrand

@Composable
fun UserProfileCard(
    fireValue: Int,
    identity: String,
    identityBadge: String,
    userAvatarUri: String?,
    partnerAvatarUri: String?,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(34.dp),
        color = Color.White.copy(alpha = 0.72f),
        shadowElevation = 8.dp,
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.65f)),
    ) {
        Row(
            modifier = Modifier.padding(start = 8.dp, top = 6.dp, end = 16.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            AvatarPair(userAvatarUri, partnerAvatarUri, identityBadge)
            Spacer(modifier = Modifier.width(10.dp))
            Column(verticalArrangement = Arrangement.spacedBy(0.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "\uD83D\uDD25",
                        modifier = Modifier
                            .clip(CircleShape)
                            .background(Brush.verticalGradient(listOf(Color(0xFFFF8A00), Color(0xFFFF4D2E))))
                            .padding(horizontal = 6.dp, vertical = 2.dp),
                        color = TextOnBrand,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(modifier = Modifier.width(7.dp))
                    Text(
                        text = fireValue.toString(),
                        style = MaterialTheme.typography.headlineSmall,
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text(
                    text = identity,
                    style = MaterialTheme.typography.labelMedium,
                    color = TextSecondary,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

@Composable
private fun AvatarPair(userAvatarUri: String?, partnerAvatarUri: String?, identityBadge: String) {
    Box(modifier = Modifier.size(width = 74.dp, height = 48.dp)) {
        AvatarImage(
            avatarUri = userAvatarUri,
            modifier = Modifier
                .size(48.dp)
                .align(Alignment.CenterStart),
        )
        AvatarImage(
            avatarUri = partnerAvatarUri,
            modifier = Modifier
                .size(44.dp)
                .align(Alignment.CenterEnd),
        )
        Text(
            text = identityBadge,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .offset(x = (-1).dp)
                .clip(RoundedCornerShape(999.dp))
                .background(PriceColor)
                .padding(horizontal = 7.dp, vertical = 1.dp),
            color = TextOnBrand,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun AvatarImage(avatarUri: String?, modifier: Modifier = Modifier) {
    val shape = CircleShape
    if (!avatarUri.isNullOrBlank()) {
        AsyncImage(
            model = avatarUri,
            contentDescription = "\u7528\u6237\u5934\u50cf",
            modifier = modifier
                .clip(shape)
                .border(2.dp, Color.White, shape),
            contentScale = ContentScale.Crop,
        )
    } else {
        Box(
            modifier = modifier
                .clip(shape)
                .background(Color.White)
                .border(2.dp, Color.White, shape),
            contentAlignment = Alignment.Center,
        ) {
            Image(
                painter = painterResource(R.drawable.shopping),
                contentDescription = "\u9ed8\u8ba4\u5934\u50cf",
                modifier = Modifier.size(32.dp),
                contentScale = ContentScale.Crop,
            )
            Icon(
                imageVector = Icons.Outlined.Person,
                contentDescription = null,
                tint = Color(0x553B2B1D),
                modifier = Modifier.size(16.dp),
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun UserProfileCardPreview() {
    ShopGuideAgentTheme {
        UserProfileCard(698, "\u9ed8\u8ba4\u8bc1\u4ef6", "V2", null, null)
    }
}
