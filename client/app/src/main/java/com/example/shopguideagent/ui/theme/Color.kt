package com.example.shopguideagent.ui.theme

import androidx.compose.ui.graphics.Color

// ============================================================
// Core Palette — Fresh Teal & Warm Accent
// ============================================================

val AppBackground = Color(0xFFF0FDF4)
val AppBackgroundGradientEnd = Color(0xFFECFDF5)

val SurfacePrimary = Color(0xFFFFFFFF)
val SurfaceSecondary = Color(0xFFF0FDFA)
val SurfaceTertiary = Color(0xFFE0F2FE)
val SurfaceSoft = Color(0xFFCCFBF1)
val SurfaceElevated = Color(0xFFFFFFFF)

// Text colors with refined gray scale
val TextPrimary = Color(0xFF111827)
val TextSecondary = Color(0xFF374151)
val TextTertiary = Color(0xFF9CA3AF)
val TextOnDark = Color(0xFFFFFFFF)
val TextOnBrand = Color(0xFFFFFFFF)

// Brand — Fresh teal, trustworthy and approachable
val BrandPrimary = Color(0xFF0D9488)
val BrandPrimaryPressed = Color(0xFF0F766E)
val BrandPrimaryMuted = Color(0xFF5EEAD4)
val BrandSoft = Color(0xFFE6F7F4)
val BrandBorder = Color(0xFF99F6E4)
val BrandGlow = Color(0x330D9488)

// Functional colors
val PriceColor = Color(0xFFF97316)
val PriceColorSoft = Color(0xFFFFF7ED)
val SuccessColor = Color(0xFF22C55E)
val SuccessSoft = Color(0xFFF0FDF4)
val WarningColor = Color(0xFFF59E0B)
val WarningSoft = Color(0xFFFFF8E6)
val ErrorColor = Color(0xFFEF4444)
val ErrorSoft = Color(0xFFFFE8E8)

// Divider & Border — warm neutral
val BorderColor = Color(0xFFE2E8F0)
val BorderLight = Color(0xFFF1F5F9)
val DividerColor = Color(0xFFE2E8F0)

// Shadows — multi-layer for realistic depth
val ShadowColor = Color(0x14111827)
val ShadowColorStrong = Color(0x20111827)
val ShadowColorAmbient = Color(0x0A111827)

// Chip colors
val ChipBackground = Color(0x4DCCFBF1)
val ChipText = Color(0xFF0F766E)
val ChipSelectedBackground = Color(0xFFFFF7ED)
val ChipSelectedText = Color(0xFFC2410C)

// ============================================================
// Gradient Presets
// ============================================================

val GradientBrandStart = Color(0xFF0D9488)
val GradientBrandEnd = Color(0xFF14B8A6)

val GradientSurfaceStart = Color(0xFFFFFFFF)
val GradientSurfaceEnd = Color(0xFFF0FDF4)

// ============================================================
// Sprite Room Warm Palette — unified with app theme
// ============================================================

val SpriteRoomTop = Color(0xFFB87942)
val SpriteRoomMiddle = Color(0xFFF4C282)
val SpriteRoomLight = Color(0xFFFFE3B5)
val SpriteRoomBottom = Color(0xFFE0A86C)
val SpritePanel = Color.White.copy(alpha = 0.72f)
val SpritePanelBorder = Color.White.copy(alpha = 0.7f)
val SpritePrimaryButton = Color(0xFFFFC94D)
val SpriteVoiceBarBackground = Color(0xFF4A3524)
val SpriteVoiceBarTint = Color(0xFFFFF8E1)

// ============================================================
// Legacy aliases (deprecated but kept for compat)
// ============================================================

@Deprecated("Use AppBackground", ReplaceWith("AppBackground"))
val Background = AppBackground
@Deprecated("Use BrandPrimary", ReplaceWith("BrandPrimary"))
val Primary = BrandPrimary
@Deprecated("Use SurfacePrimary", ReplaceWith("SurfacePrimary"))
val AiBubble = SurfacePrimary
@Deprecated("Use BrandPrimary", ReplaceWith("BrandPrimary"))
val UserBubble = BrandPrimary
@Deprecated("Use PriceColor", ReplaceWith("PriceColor"))
val Price = PriceColor
@Deprecated("Use BorderColor", ReplaceWith("BorderColor"))
val Border = BorderColor
