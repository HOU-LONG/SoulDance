package com.example.shopguideagent.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.foundation.shape.RoundedCornerShape

private val LightColorScheme = lightColorScheme(
    // NOTE: When changing AppBackground, also update values/styles.xml android:windowBackground
    // and values/colors.xml app_background to match.
    primary = BrandPrimary,
    onPrimary = TextOnBrand,
    primaryContainer = BrandSoft,
    onPrimaryContainer = BrandPrimary,
    secondary = PriceColor,
    onSecondary = TextOnDark,
    secondaryContainer = PriceColorSoft,
    onSecondaryContainer = PriceColor,
    background = AppBackground,
    onBackground = TextPrimary,
    surface = SurfacePrimary,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceSecondary,
    onSurfaceVariant = TextSecondary,
    surfaceTint = BrandPrimary,
    error = ErrorColor,
    onError = TextOnDark,
    errorContainer = ErrorSoft,
    onErrorContainer = ErrorColor,
    outline = BorderColor,
    outlineVariant = BorderLight,
    scrim = TextPrimary.copy(alpha = 0.32f),
)

@Composable
fun ShopGuideAgentTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColorScheme,
        shapes = Shapes(
            extraSmall = RoundedCornerShape(AppCornerRadius.Small),
            small = RoundedCornerShape(AppCornerRadius.Control),
            medium = RoundedCornerShape(AppCornerRadius.Card),
            large = RoundedCornerShape(AppCornerRadius.LargeCard),
            extraLarge = RoundedCornerShape(AppCornerRadius.Sheet),
        ),
        typography = Typography,
        content = content,
    )
}
