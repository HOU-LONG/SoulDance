# AGENTS.md - ShopGuide Agent Android 客户端开发规则

## 项目目标

开发 Android 原生客户端，用 Kotlin + Jetpack Compose 实现 ShopGuide Agent 的低压力流式导购体验。

客户端需要支持：

```text
1. 聊天 UI
2. WebSocket 流式事件
3. 主推商品卡片渐进式渲染
4. 场景组合推荐展示
5. 以商品为锚点的详情浮层和多轮追问
6. 购物车 CRUD
7. 语音输入 ASR
8. 流式 TTS 播放
9. 商品详情 BottomSheet
```

## 技术栈

```text
Language: Kotlin
UI: Jetpack Compose
Architecture: MVVM
State: StateFlow
Network: OkHttp + WebSocket
Image: Coil
Local storage: DataStore 或 SharedPreferences
ASR: Android SpeechRecognizer
TTS playback: AudioTrack
Build: Gradle Wrapper
```

## 推荐目录结构

```text
app/src/main/java/com/example/shopguideagent/
  MainActivity.kt
  config/
    AppConfig.kt
    UserSession.kt
  data/
    model/
      ChatMessage.kt
      Product.kt
      Cart.kt
      BundleModels.kt
      FocusModels.kt
      RealtimeEvent.kt
    remote/
      RealtimeChatWebSocketClient.kt
      ProductApiClient.kt
      CartApiClient.kt
    local/
      SessionStore.kt
  vm/
    ChatViewModel.kt
    CartViewModel.kt
    ProductFocusViewModel.kt
  ui/
    screen/
      ChatScreen.kt
      CartScreen.kt
    component/
      MessageBubble.kt
      TypingIndicator.kt
      ChatInputBar.kt
      ProductCarousel.kt
      ProductCard.kt
      ProductSkeletonCard.kt
      ProductDetailBottomSheet.kt
      ProductFocusInputBar.kt
      ReplacementProductCard.kt
      BundleSection.kt
      BundleGroupCard.kt
      CartBadge.kt
      CartItemCard.kt
      CartSummaryBar.kt
      CheckoutBottomSheet.kt
      EmptyCartView.kt
      VoiceInputButton.kt
      SpeakerToggle.kt
    theme/
      Color.kt
      Theme.kt
      Type.kt
  voice/
    VoiceInputManager.kt
  audio/
    StreamingAudioPlayer.kt
    AudioQueue.kt
  navigation/
    AppNavGraph.kt
```

## 核心产品原则

```text
1. 不做搜索引擎式“给一堆结果”。
2. 默认给一个主推商品，必要时给 1-2 个备选。
3. 文字回复先理解用户动机，再解释推荐结论。
4. 商品卡片点击后使用 BottomSheet 浮层，不强制跳转离开聊天流。
5. 商品详情浮层底部必须支持“围绕当前商品继续问”。
6. product_followup 必须携带 focus_product_id，避免上下文污染。
7. Android 端只展示真实后端返回的商品，不在客户端编造推荐逻辑。
8. TTS/LLM API Key 永远不写在客户端。
```

## 构建命令

在项目根目录运行：

```bash
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest
```

Windows：

```bat
gradlew.bat :app:assembleDebug
gradlew.bat :app:testDebugUnitTest
```

## 每次任务完成后的自检

```text
1. Gradle 是否能编译。
2. App 是否能启动。
3. ChatScreen 是否能显示。
4. 无网络时是否有错误提示。
5. 商品图片失败时是否有 fallback。
6. WebSocket 断开是否不崩溃。
7. 商品详情 BottomSheet 是否能关闭并回到聊天流。
8. product_followup 是否带 focus_product_id。
9. 购物车数量是否正确。
10. 页面销毁时是否释放 SpeechRecognizer / AudioTrack / WebSocket。
```

## 禁止事项

```text
1. 禁止用 Flutter 或 WebView 替代 Android 原生 Compose 主流程。
2. 禁止把商品推荐逻辑写死在 Android。
3. 禁止把 TTS/LLM API Key 写到客户端。
4. 禁止让商品详情跳到外部网页作为主要体验。
5. 禁止忽略错误处理。
6. 禁止每个 token 都强制大幅滚动导致 UI 抖动。
7. 禁止让 Codex 一次性实现所有任务。
```
