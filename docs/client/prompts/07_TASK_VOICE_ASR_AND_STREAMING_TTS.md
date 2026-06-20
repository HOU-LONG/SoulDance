# Task 07：实现语音输入 ASR 与流式 TTS 播放

## 目标

实现：

```text
1. Android 原生语音输入 SpeechRecognizer。
2. 后端 audio_delta PCM 音频流播放。
```

## 需要创建/修改文件

```text
voice/VoiceInputManager.kt
ui/component/VoiceInputButton.kt
audio/StreamingAudioPlayer.kt
audio/AudioQueue.kt
ui/component/SpeakerToggle.kt
data/model/RealtimeEvent.kt
vm/ChatViewModel.kt
ui/screen/ChatScreen.kt
AndroidManifest.xml
```

## Manifest 权限

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />

<queries>
    <intent>
        <action android:name="android.speech.RecognitionService" />
    </intent>
</queries>
```

## ASR：VoiceInputManager

建议接口：

```kotlin
class VoiceInputManager(
    private val context: Context,
    private val onPartialResult: (String) -> Unit,
    private val onFinalResult: (String) -> Unit,
    private val onError: (String) -> Unit,
    private val onStateChanged: (VoiceState) -> Unit
) {
    fun startListening()
    fun stopListening()
    fun cancel()
    fun destroy()
}

enum class VoiceState {
    Idle,
    Listening,
    Recognizing,
    Error
}
```

## TTS：audio_delta 事件

```json
{
  "type": "audio_delta",
  "message_id": "assistant_001",
  "segment_id": 1,
  "audio_format": "pcm_s16le",
  "sample_rate": 24000,
  "channels": 1,
  "audio_base64": "..."
}
```

## StreamingAudioPlayer

要求：

```text
1. base64 decode audio_base64。
2. 使用 AudioTrack 播放 pcm_s16le。
3. sample_rate 默认 24000。
4. channels 默认 mono。
5. 先缓存 200-500ms 音频再开始播放。
6. 支持 stop。
7. 新一轮对话开始时停止上一轮音频。
8. 页面销毁时 release。
```

## 验收标准

```text
1. 首次点击麦克风会请求权限。
2. 能识别中文语音并填入输入框。
3. 识别失败不崩溃。
4. audio_delta 到来后能播放声音。
5. 播放可停止。
6. 新消息开始时停止旧音频。
7. 页面销毁时释放 SpeechRecognizer 和 AudioTrack。
8. ./gradlew :app:assembleDebug 通过。
```
