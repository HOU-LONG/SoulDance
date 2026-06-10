# Task 04：接入 WebSocket 流式聊天协议

## 目标

使用 OkHttp WebSocket 连接后端 `/api/chat/realtime`，接收流式事件并更新 ChatScreen。

## 需要创建/修改文件

```text
data/model/RealtimeEvent.kt
data/remote/RealtimeChatWebSocketClient.kt
vm/ChatViewModel.kt
ui/screen/ChatScreen.kt
config/AppConfig.kt
```

## Android 发送事件

普通用户消息：

```json
{
  "type": "user_message",
  "session_id": "demo_session_001",
  "message": "推荐一款适合油皮的洗面奶，预算100以内",
  "input_type": "text",
  "tts_enabled": true,
  "voice": "default_female"
}
```

商品级追问消息在 Task 09 实现。

## 需要支持的基础后端事件

### text_delta

```json
{
  "type": "text_delta",
  "message_id": "assistant_001",
  "text": "我"
}
```

行为：

```text
找到当前 assistant message，追加 text。
如果不存在，则创建新的 assistant message。
```

### done

```json
{
  "type": "done",
  "message_id": "assistant_001"
}
```

行为：

```text
停止当前消息 streaming 状态。
```

### error

```json
{
  "type": "error",
  "message": "服务暂时不可用"
}
```

行为：

```text
显示 Snackbar/Toast，不得崩溃。
```

## RealtimeEvent 模型建议

```kotlin
sealed class RealtimeEvent {
    data class TextDelta(val messageId: String, val text: String) : RealtimeEvent()
    data class Done(val messageId: String?) : RealtimeEvent()
    data class Error(val message: String) : RealtimeEvent()
    data class Unknown(val raw: String) : RealtimeEvent()
}
```

后续任务会扩展 Product、Bundle、Audio、Cart、Focus 事件。

## 验收标准

```text
1. 能连接后端 WebSocket。
2. 用户发送文本后，后端 text_delta 能逐字显示。
3. done 后 loading 停止。
4. error 时有提示。
5. WebSocket 断开时不崩溃。
6. ./gradlew :app:assembleDebug 通过。
```
