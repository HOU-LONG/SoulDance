# Codex / Claude Code 执行 Prompt 索引

## 通用执行模板

每个任务都按这个格式提交给 Codex / Claude Code：

```text
请先阅读：
1. AGENTS.md
2. prompts/<TASK_FILE>.md

只实现 <TASK_FILE> 中要求的内容。
不要实现后续任务，不要做无关重构。
完成后请：
1. 运行 ./gradlew :app:assembleDebug
2. 修复所有编译错误
3. 总结修改了哪些文件
4. 说明还有哪些未完成
```

## 推荐执行顺序

```text
1. 02_TASK_PROJECT_SCAFFOLD.md
2. 03_TASK_CHAT_UI.md
3. 04_TASK_WEBSOCKET_STREAMING.md
4. 05_TASK_PRODUCT_CARDS_AND_BUNDLE.md
5. 06_TASK_CART_CRUD.md
6. 07_TASK_VOICE_ASR_AND_STREAMING_TTS.md
7. 09_TASK_PRODUCT_FOCUS_GUIDANCE.md
8. 10_TASK_BACKEND_CONTRACT_AND_MOCK_SERVER.md
9. 08_TASK_TESTING_AND_DEMO_ACCEPTANCE.md
```

## 不要一次性让 Codex 做所有任务

错误做法：

```text
请你把整个 Android 客户端都实现出来。
```

正确做法：

```text
请只完成 Task 03 聊天 UI，不要实现 WebSocket、商品卡片和购物车。
```

## 每次任务完成后人工检查

```text
1. git diff
2. ./gradlew :app:assembleDebug
3. Android Studio Sync
4. 真机运行
5. 截图/录屏
6. git commit
```
