package com.example.shopguideagent.ui.component

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.widget.Toast
import com.example.shopguideagent.data.model.ProductShareFormatter
import com.example.shopguideagent.data.model.ProductUiModel

object ProductShareActions {
    fun copyProductInfo(context: Context, product: ProductUiModel) {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(
            ClipData.newPlainText("Product info", ProductShareFormatter.shareText(product)),
        )
        Toast.makeText(context, "Product info copied", Toast.LENGTH_SHORT).show()
    }

    fun shareProduct(context: Context, product: ProductUiModel) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, ProductShareFormatter.shareText(product))
        }
        val chooser = Intent.createChooser(intent, "Share product")
        if (context !is Activity) {
            chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(chooser)
    }
}
