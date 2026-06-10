package com.example.shopguideagent.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.LocalMall
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import coil.request.CachePolicy
import coil.request.ImageRequest
import coil.size.Precision
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.SurfaceSoft
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun ProductImage(
    imageUrl: String?,
    productName: String,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val request = remember(context, imageUrl) {
        ImageRequest.Builder(context)
            .data(imageUrl)
            .crossfade(false)
            .memoryCachePolicy(CachePolicy.ENABLED)
            .diskCachePolicy(CachePolicy.ENABLED)
            .memoryCacheKey(imageUrl)
            .diskCacheKey(imageUrl)
            .size(720, 720)
            .precision(Precision.INEXACT)
            .build()
    }
    var loadFailed by remember(imageUrl) {
        mutableStateOf(imageUrl.isNullOrBlank())
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(AppCornerRadius.Card))
            .background(if (imageUrl.isNullOrBlank()) BrandSoft else SurfaceSoft),
        contentAlignment = Alignment.Center,
    ) {
        if (!imageUrl.isNullOrBlank()) {
            AsyncImage(
                model = request,
                contentDescription = productName,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
                onSuccess = { loadFailed = false },
                onError = { loadFailed = true },
            )
        }
        if (loadFailed) {
            ProductImageFallback(productName)
        }
    }
}

@Composable
private fun ProductImageFallback(productName: String) {
    Box(contentAlignment = Alignment.Center) {
        Icon(
            imageVector = Icons.Outlined.LocalMall,
            contentDescription = null,
            tint = BrandPrimary,
            modifier = Modifier
                .fillMaxSize(0.36f)
                .padding(4.dp),
        )
        Text(
            text = productName.take(2),
            color = TextSecondary,
            fontWeight = FontWeight.Medium,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 14.dp),
        )
    }
}
