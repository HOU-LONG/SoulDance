package com.example.shopguideagent.data.catalog

import java.net.URI

object ProductImageUrlResolver {
    @JvmStatic
    fun assetUrl(imagePath: String?): String? {
        val normalized = normalizePath(imagePath) ?: return null
        val assetPath = normalized
            .removePrefix("file:///android_asset/")
            .removePrefix("android_asset/")
            .trimStart('/')
        return "file:///android_asset/$assetPath"
    }

    @JvmStatic
    fun remoteUrl(imageUrl: String?, baseHttpUrl: String): String? {
        val normalized = normalizePath(imageUrl) ?: return null
        if (normalized.hasScheme()) {
            val assetPath = privateBackendAssetPath(normalized)
            return if (assetPath != null) {
                "${baseHttpUrl.trimEnd('/')}$assetPath"
            } else {
                normalized
            }
        }
        return if (normalized.startsWith("/")) {
            "${baseHttpUrl.trimEnd('/')}$normalized"
        } else {
            "${baseHttpUrl.trimEnd('/')}/$normalized"
        }
    }

    private fun normalizePath(value: String?): String? {
        val trimmed = value?.trim()?.replace('\\', '/') ?: return null
        if (trimmed.isBlank()) return null
        return repairUtf8Mojibake(trimmed)
    }

    private fun repairUtf8Mojibake(value: String): String {
        val repaired = runCatching {
            String(value.toByteArray(Charsets.ISO_8859_1), Charsets.UTF_8)
        }.getOrNull() ?: return value
        return if (repaired.cjkCharacterCount() > value.cjkCharacterCount()) repaired else value
    }

    private fun String.hasScheme(): Boolean =
        startsWith("http://", ignoreCase = true) ||
            startsWith("https://", ignoreCase = true) ||
            startsWith("file://", ignoreCase = true) ||
            startsWith("content://", ignoreCase = true)

    private fun privateBackendAssetPath(value: String): String? {
        val uri = runCatching { URI(value) }.getOrNull() ?: return null
        val host = uri.host?.lowercase() ?: return null
        val path = uri.rawPath ?: return null
        if (!path.startsWith("/assets/products/")) return null
        return if (host.isPrivateBackendHost()) {
            path + (uri.rawQuery?.let { "?$it" } ?: "")
        } else {
            null
        }
    }

    private fun String.isPrivateBackendHost(): Boolean =
        this == "localhost" ||
            this == "127.0.0.1" ||
            this.startsWith("192.168.") ||
            this.startsWith("10.") ||
            this.matches(Regex("""172\.(1[6-9]|2\d|3[0-1])\..+"""))

    private fun String.cjkCharacterCount(): Int =
        count {
            val block = Character.UnicodeBlock.of(it)
            block == Character.UnicodeBlock.CJK_UNIFIED_IDEOGRAPHS ||
                block == Character.UnicodeBlock.CJK_UNIFIED_IDEOGRAPHS_EXTENSION_A ||
                block == Character.UnicodeBlock.CJK_COMPATIBILITY_IDEOGRAPHS
        }
}
