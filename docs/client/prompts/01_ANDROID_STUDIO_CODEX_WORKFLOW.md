# Task 01：Android Studio 与 Codex / Claude Code 协作流程

## 目标

建立稳定开发流程，让 Android Studio、Codex / Claude Code、Git 三者分工清楚。

## 推荐协作模式

```text
Android Studio：创建工程、Gradle Sync、真机运行、预览、Logcat 调试。
Codex / Claude Code：批量写代码、补组件、修编译错误、做局部重构。
Git：保存每个阶段的稳定版本。
```

不要把 Android Studio 和 Codex 看成二选一。它们应该围绕同一个 Git 仓库工作。

## 第一次创建工程

用 Android Studio 创建：

```text
New Project
  -> Empty Activity
  -> Language: Kotlin
  -> Minimum SDK: 26 或更高
  -> Use Jetpack Compose: yes
```

创建后确认：

```text
1. 能 Gradle Sync。
2. 能在模拟器或真机启动。
3. 根目录有 gradlew / gradlew.bat。
4. 能运行 ./gradlew :app:assembleDebug。
```

## Codex / Claude Code 接入

在项目根目录放置：

```text
AGENTS.md
prompts/
```

然后在项目根目录启动：

```bash
codex
# 或
claude
```

每次只给一个任务文件，例如：

```text
请先阅读 AGENTS.md 和 prompts/03_TASK_CHAT_UI.md。
只实现该任务，不要实现 WebSocket、购物车、语音、TTS。
完成后运行 ./gradlew :app:assembleDebug 并修复编译错误。
```

## 推荐 Git 分支

```text
main                        稳定可演示版本
dev                         日常集成版本
feature/chat-ui
feature/websocket-stream
feature/product-cards
feature/cart
feature/voice-tts
feature/product-focus
```

## 每日循环

```text
1. 从 dev 拉最新代码。
2. 切 feature 分支。
3. 给 Codex 一个任务 md。
4. Codex 修改并运行 gradlew。
5. Android Studio Sync。
6. 真机运行。
7. 人工看 UI。
8. git diff。
9. commit。
10. 合并到 dev。
```

## 本地电脑与服务器怎么配合

### 可以在 VS Code 服务器里做

```text
1. 写 Kotlin 代码。
2. 运行 gradlew 编译。
3. 跑单元测试。
4. 让 Codex / Claude Code 批量改代码。
5. 生成 APK。
```

### 不适合只在服务器做

```text
1. Android Studio UI 预览。
2. 模拟器图形调试。
3. 真机 USB 调试。
4. Logcat 交互调试。
```

### 最稳方案

```text
本地电脑：Android Studio + 真机调试。
服务器/VS Code：Codex / Claude Code 批量改代码 + gradlew 编译。
Git：同步两边代码。
```

## 网络注意事项

模拟器访问电脑本地后端：

```text
http://10.0.2.2:8000
ws://10.0.2.2:8000
```

真机访问电脑本地后端：

```text
http://电脑局域网IP:8000
ws://电脑局域网IP:8000
```

不要在 Android 真机里写：

```text
localhost
127.0.0.1
```
