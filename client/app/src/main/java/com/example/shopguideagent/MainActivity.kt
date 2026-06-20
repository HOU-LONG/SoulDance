package com.example.shopguideagent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.example.shopguideagent.navigation.AppNavGraph
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            ShopGuideAgentTheme {
                AppNavGraph()
            }
        }
    }
}
