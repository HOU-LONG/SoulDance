package com.example.shopguideagent.ui.component

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration

private val headingPattern = Regex("""^(#{1,6})\s+(.*)$""")
private val unorderedListPattern = Regex("""^[-*+]\s+(.*)$""")
private val orderedListPattern = Regex("""^\d+[.)]\s+(.*)$""")
private val quotePattern = Regex("""^>\s?(.*)$""")
private val horizontalRulePattern = Regex("""^([-*_])(\s*\1){2,}\s*$""")
private val tableSeparatorPattern = Regex("""^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$""")
private val logicalLabelTerms = listOf(
    "推荐结论",
    "评论摘要",
    "备选差异",
    "适合场景",
    "商品亮点",
    "怎么选",
    "为什么",
    "下一步",
    "主推",
    "结论",
    "原因",
    "备选",
    "注意",
).sortedByDescending { it.length }
private val logicalLabelPattern = Regex(
    """(?<![\p{L}\p{N}_*])(${logicalLabelTerms.joinToString("|") { Regex.escape(it) }})([：:])""",
)
private val sentenceBoundaryPattern = Regex("""(?<=[。！？])\s*|(?<=[.!?])\s+""")

fun renderMarkdownText(
    markdown: String,
    fallback: String,
    autoSegment: Boolean = false,
): AnnotatedString {
    val source = markdown.ifBlank { fallback }
        .replace("\r\n", "\n")
        .replace('\r', '\n')
        .let { if (autoSegment) autoSegmentAssistantText(it) else it }
    if (source.isBlank()) return AnnotatedString("")

    val builder = AnnotatedString.Builder()
    var inCodeFence = false
    source.lines().forEach { rawLine ->
        val trimmed = rawLine.trim()
        if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) {
            inCodeFence = !inCodeFence
            return@forEach
        }

        if (inCodeFence) {
            appendBlockLine(
                builder = builder,
                text = rawLine.trimEnd(),
                blockStyle = SpanStyle(fontFamily = FontFamily.Monospace),
                parseInline = false,
            )
            return@forEach
        }

        val line = markdownBlockLine(rawLine) ?: return@forEach
        appendBlockLine(
            builder = builder,
            text = line.text,
            blockStyle = line.style,
            parseInline = true,
        )
    }
    return builder.toAnnotatedString()
}

private fun autoSegmentAssistantText(source: String): String {
    val trimmed = source.trim()
    if (trimmed.contains("\n\n")) return source
    val lines = trimmed.lines()
    if (lines.size > 1 && lines.any { raw ->
            val line = raw.trim()
            headingPattern.matches(line) ||
                unorderedListPattern.matches(line) ||
                orderedListPattern.matches(line) ||
                quotePattern.matches(line)
        }
    ) {
        return source
    }

    val segmentedByLabels = segmentLogicalLabels(trimmed)
    if (segmentedByLabels != trimmed) return segmentedByLabels

    if (trimmed.length < 100) return source

    val sentences = sentenceBoundaryPattern
        .split(trimmed)
        .map { it.trim() }
        .filter { it.isNotBlank() }
    if (sentences.size < 3) return source

    return sentences
        .chunked(2)
        .joinToString("\n\n") { chunk -> joinSentenceChunk(chunk) }
}

private fun segmentLogicalLabels(source: String): String {
    var changed = false
    val segmented = logicalLabelPattern.replace(source) { match ->
        changed = true
        val start = match.range.first
        val prefix = if (start == 0 || source[start - 1] == '\n') "" else "\n\n"
        "$prefix**${match.groupValues[1]}${match.groupValues[2]}**"
    }
    if (!changed) return source
    return segmented
        .replace(Regex("""[ \t]*\n{3,}[ \t]*"""), "\n\n")
        .trim()
}

private fun joinSentenceChunk(sentences: List<String>): String =
    sentences.foldIndexed("") { index, acc, sentence ->
        if (index == 0) {
            sentence
        } else {
            acc + sentenceSeparator(acc, sentence) + sentence
        }
    }

private fun sentenceSeparator(previous: String, next: String): String {
    val previousEnd = previous.lastOrNull() ?: return ""
    val nextStart = next.firstOrNull() ?: return ""
    return if (previousEnd in ".!?" && nextStart.isAsciiLetterOrDigit()) " " else ""
}

private fun Char.isAsciiLetterOrDigit(): Boolean =
    code in 'A'.code..'Z'.code ||
        code in 'a'.code..'z'.code ||
        code in '0'.code..'9'.code

private data class MarkdownLine(
    val text: String,
    val style: SpanStyle? = null,
)

private fun markdownBlockLine(rawLine: String): MarkdownLine? {
    val trimmed = rawLine.trim()
    if (trimmed.isBlank()) return MarkdownLine("")
    if (horizontalRulePattern.matches(trimmed)) return null
    if (tableSeparatorPattern.matches(trimmed)) return null

    headingPattern.matchEntire(trimmed)?.let { match ->
        return MarkdownLine(
            text = match.groupValues[2].trim(),
            style = SpanStyle(fontWeight = FontWeight.Bold),
        )
    }
    unorderedListPattern.matchEntire(trimmed)?.let { match ->
        return MarkdownLine("• ${match.groupValues[1].trim()}")
    }
    orderedListPattern.matchEntire(trimmed)?.let { match ->
        return MarkdownLine(match.groupValues[1].trim())
    }
    quotePattern.matchEntire(trimmed)?.let { match ->
        return MarkdownLine(
            text = match.groupValues[1].trim(),
            style = SpanStyle(fontStyle = FontStyle.Italic),
        )
    }
    if (trimmed.contains("|") && trimmed.trim('|').contains("|")) {
        val cells = trimmed
            .trim('|')
            .split('|')
            .map { it.trim() }
            .filter { it.isNotBlank() }
        if (cells.size > 1) return MarkdownLine(cells.joinToString("  "))
    }
    return MarkdownLine(trimmed)
}

private fun appendBlockLine(
    builder: AnnotatedString.Builder,
    text: String,
    blockStyle: SpanStyle?,
    parseInline: Boolean,
) {
    if (builder.length > 0) builder.append('\n')
    if (text.isEmpty()) return
    if (blockStyle != null) builder.pushStyle(blockStyle)
    if (parseInline) {
        appendMarkdownInline(builder, text)
    } else {
        builder.append(text)
    }
    if (blockStyle != null) builder.pop()
}

private fun appendMarkdownInline(builder: AnnotatedString.Builder, source: String) {
    var index = 0
    while (index < source.length) {
        when {
            source[index] == '\\' && index + 1 < source.length -> {
                builder.append(source[index + 1])
                index += 2
            }
            source[index] == '[' -> {
                val next = appendMarkdownLink(builder, source, index)
                index = next ?: run {
                    builder.append(source[index])
                    index + 1
                }
            }
            source.startsWith("**", index) -> {
                index = appendDelimited(
                    builder = builder,
                    source = source,
                    startIndex = index,
                    delimiter = "**",
                    style = SpanStyle(fontWeight = FontWeight.Bold),
                    parseNested = true,
                )
            }
            source.startsWith("__", index) -> {
                index = appendDelimited(
                    builder = builder,
                    source = source,
                    startIndex = index,
                    delimiter = "__",
                    style = SpanStyle(fontWeight = FontWeight.Bold),
                    parseNested = true,
                )
            }
            source.startsWith("~~", index) -> {
                index = appendDelimited(
                    builder = builder,
                    source = source,
                    startIndex = index,
                    delimiter = "~~",
                    style = SpanStyle(textDecoration = TextDecoration.LineThrough),
                    parseNested = true,
                )
            }
            source[index] == '`' -> {
                index = appendDelimited(
                    builder = builder,
                    source = source,
                    startIndex = index,
                    delimiter = "`",
                    style = SpanStyle(fontFamily = FontFamily.Monospace),
                    parseNested = false,
                )
            }
            source[index] == '*' -> {
                index = appendDelimited(
                    builder = builder,
                    source = source,
                    startIndex = index,
                    delimiter = "*",
                    style = SpanStyle(fontStyle = FontStyle.Italic),
                    parseNested = true,
                )
            }
            source[index] == '_' -> {
                index = appendDelimited(
                    builder = builder,
                    source = source,
                    startIndex = index,
                    delimiter = "_",
                    style = SpanStyle(fontStyle = FontStyle.Italic),
                    parseNested = true,
                )
            }
            else -> {
                builder.append(source[index])
                index += 1
            }
        }
    }
}

private fun appendMarkdownLink(
    builder: AnnotatedString.Builder,
    source: String,
    startIndex: Int,
): Int? {
    val labelEnd = findClosing(source, "]", startIndex + 1)
    if (labelEnd < 0 || labelEnd + 1 >= source.length || source[labelEnd + 1] != '(') return null
    val urlEnd = findClosing(source, ")", labelEnd + 2)
    if (urlEnd < 0) return null

    val label = source.substring(startIndex + 1, labelEnd)
    builder.pushStyle(SpanStyle(textDecoration = TextDecoration.Underline))
    appendMarkdownInline(builder, label)
    builder.pop()
    return urlEnd + 1
}

private fun appendDelimited(
    builder: AnnotatedString.Builder,
    source: String,
    startIndex: Int,
    delimiter: String,
    style: SpanStyle,
    parseNested: Boolean,
): Int {
    val contentStart = startIndex + delimiter.length
    val endIndex = findClosing(source, delimiter, contentStart)
    if (endIndex < 0) return contentStart

    builder.pushStyle(style)
    val content = source.substring(contentStart, endIndex)
    if (parseNested) {
        appendMarkdownInline(builder, content)
    } else {
        builder.append(content)
    }
    builder.pop()
    return endIndex + delimiter.length
}

private fun findClosing(source: String, delimiter: String, startIndex: Int): Int {
    var index = source.indexOf(delimiter, startIndex)
    while (index >= 0) {
        if (!source.isEscapedAt(index)) return index
        index = source.indexOf(delimiter, index + delimiter.length)
    }
    return -1
}

private fun String.isEscapedAt(index: Int): Boolean {
    var slashCount = 0
    var cursor = index - 1
    while (cursor >= 0 && this[cursor] == '\\') {
        slashCount += 1
        cursor -= 1
    }
    return slashCount % 2 == 1
}
