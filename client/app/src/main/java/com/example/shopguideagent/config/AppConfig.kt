package com.example.shopguideagent.config

object AppConfig {
    // === 选项 1: Cloudflare Tunnel 公网地址 (推荐，真机直接访问) ===
    // const val BASE_HTTP_URL = "https://continually-replication-allowing-editions.trycloudflare.com/"
    // const val BASE_WS_URL = "wss://continually-replication-allowing-editions.trycloudflare.com"

    // === 选项 2: Android 模拟器 -> 本机 localhost ===
    // const val BASE_HTTP_URL = "http://10.0.2.2:8000"
    // const val BASE_WS_URL = "ws://10.0.2.2:8000"

    // === 选项 3: 真机局域网 / adb reverse 桥接 ===
    const val BASE_HTTP_URL = "http://localhost:8001"
    const val BASE_WS_URL = "ws://localhost:8001"

    const val WS_CHAT_PATH = "/ws/chat"
}
