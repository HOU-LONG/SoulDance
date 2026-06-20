# Task 02：创建 Android Compose 工程骨架

## 目标

建立 ShopGuide Agent Android 客户端的基础工程结构，并确保 App 可运行。

## 输入前提

已有 Android Studio 创建的 Kotlin + Jetpack Compose 工程。

## 需要实现

### 1. 基础包结构

在 `app/src/main/java/com/example/shopguideagent/` 下创建：

```text
config/
data/model/
data/remote/
data/local/
vm/
ui/screen/
ui/component/
ui/theme/
voice/
audio/
navigation/
```

### 2. 配置文件

创建：

```text
config/AppConfig.kt
config/UserSession.kt
```

建议内容：

```kotlin
object AppConfig {
    const val BASE_HTTP_URL = "http://10.0.2.2:8000"
    const val BASE_WS_URL = "ws://10.0.2.2:8000"
}

object UserSession {
    const val USER_ID = "demo_user"
    const val DEFAULT_SESSION_ID = "demo_session_001"
}
```

### 3. Navigation

创建：

```text
navigation/AppNavGraph.kt
```

至少包含：

```text
chat
cart
```

商品详情主流程不强制跳转页面，后续用 BottomSheet 实现。

### 4. MainActivity

`MainActivity.kt` 加载主题和 AppNavGraph。

### 5. Theme

在 `ui/theme/` 中定义基本颜色、字体和主题。

建议颜色：

```text
背景：#F7F8FA
主色：#4F46E5
AI 气泡：#FFFFFF
用户气泡：#4F46E5
价格色：#FF6B35
文字主色：#1F2937
文字弱色：#6B7280
```

## 验收标准

```text
1. App 能启动。
2. ChatScreen 可以显示。
3. 导航不崩溃。
4. ./gradlew :app:assembleDebug 通过。
```

## 不要做

```text
1. 不要接 WebSocket。
2. 不要做购物车业务。
3. 不要做 TTS/ASR。
4. 不要做复杂 DI。
```
