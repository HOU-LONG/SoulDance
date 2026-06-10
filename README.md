# ShopGuide Agent / SoulDance

低压力 AI 导购产品，包含 Android 原生客户端和 FastAPI 后端。用户可以用自然语言说出购物需求，系统会基于商品库给出主推商品、少量备选、商品卡片、购物车操作、语音输入和语音播报。

## 仓库组织

推荐用一个 GitHub 仓库、一个主分支管理完整产品，按目录区分 Android 和后端：

```text
SoulDance/
  android/     Android Kotlin + Jetpack Compose 客户端
  backend/     FastAPI 后端服务
  docs/        部署、语音、验收和技术说明
  tests/       后端测试
```

不建议用两个长期分支分别存 Android 和后端。分支更适合表达版本或功能开发，比如 `feature/voice-fix`、`release/demo-2026-06-10`。如果 Android 和后端分散在两个长期分支里，用户 clone 后无法一次拿到完整产品，README、Issue、Release 和版本对应关系都会变复杂。

## 当前公网体验地址

当前 Android 客户端默认连接公网后端，真机安装后即可体验。

```text
HTTP API: https://continually-replication-allowing-editions.trycloudflare.com/
WebSocket: wss://continually-replication-allowing-editions.trycloudflare.com/ws/chat
```

## 快速体验

### 方式 1：下载 APK 直接安装

可以把编译好的 APK 上传到 GitHub Releases，用户下载后直接安装使用。因为 App 已经内置公网后端地址，用户不需要本地部署后端。

推荐发布方式：

1. 在 GitHub 仓库页面创建 `Release`。
2. 上传 `app-debug.apk` 或正式签名的 release APK。
3. 在 Release Notes 中写清楚公网后端地址、主要功能和已知限制。
4. 在 README 里放 Release 下载入口。

说明：

- 可以上传 APK 到 GitHub，但更建议放在 GitHub Releases，而不是直接提交进 git 仓库。
- Debug APK 适合内部演示和快速体验；面向外部用户时建议发布 signed release APK。
- Android 安装第三方 APK 时需要允许“安装未知来源应用”。
- 当前 Cloudflare URL 是临时隧道风格地址；如果隧道地址变化，需要更新 `android/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt` 后重新打包 APK。

### 方式 2：开发者本地编译安装

```powershell
cd android
$env:JAVA_HOME='C:\Users\houlong\.jdks\jbr-21.0.11'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
.\gradlew.bat :app:testDebugUnitTest
.\gradlew.bat :app:assembleDebug
```

APK 默认输出：

```text
android\app\build\outputs\apk\debug\app-debug.apk
```

安装到已连接真机：

```powershell
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
```

如果需要自定义构建输出目录，可以设置：

```powershell
$env:SHOPGUIDE_ANDROID_BUILD_DIR='C:\path\to\build\dir'
```

## 体验流程

打开 App 后可以直接输入：

```text
我要一瓶东鹏特饮
我想要一杯不超过30元的咖啡
把东鹏特饮加入购物车
清空购物车
不要雀巢
推荐一款拍照好的手机，预算8000
```

核心交互：

- 文本聊天：输入购物需求，后端通过 WebSocket 流式返回回答和商品卡片。
- 商品推荐：默认一个主推商品，必要时展示 1-2 个备选。
- 商品详情：点击商品卡片打开详情 BottomSheet，可围绕当前商品继续追问。
- 购物车：支持自然语言加购、清空购物车，以及购物车页面结算。
- 语音输入：按住麦克风说话，松开发送，上滑取消；首次使用需要授予录音权限。
- 语音播报：默认开启；当前会话可静音，新会话会恢复默认播报。

## Android 配置

公网配置在：

```text
android/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt
```

当前配置：

```kotlin
const val BASE_HTTP_URL = "https://continually-replication-allowing-editions.trycloudflare.com/"
const val BASE_WS_URL = "wss://continually-replication-allowing-editions.trycloudflare.com"
const val WS_CHAT_PATH = "/ws/chat"
```

如果使用新的 Cloudflare Tunnel 地址，需要同步更新 `BASE_HTTP_URL` 和 `BASE_WS_URL`，然后重新编译 APK。

## 后端部署

当前后端运行在：

```text
mix_A100:/home/huadabioa/houlong/SoulDance
```

进入后端目录：

```bash
ssh mix_A100
cd /home/huadabioa/houlong/SoulDance
```

运行测试：

```bash
env/venv_shopguide_backend/bin/python -m pytest -q
```

启动或重启 FastAPI：

```bash
pkill -f "uvicorn backend.app.main:app" || true
mkdir -p logs
setsid -f env/venv_shopguide_backend/bin/python -m uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info \
  --timeout-keep-alive 120 \
  --ws-ping-interval 20 \
  --ws-ping-timeout 10 \
  --limit-concurrency 20 \
  > logs/backend.log 2>&1 < /dev/null
```

本机验证：

```bash
curl -fsS http://127.0.0.1:8000/health
```

启动 Cloudflare 临时公网隧道：

```bash
nohup /home/huadabioa/bin/cloudflared tunnel --url http://127.0.0.1:8000 \
  > logs/cloudflared-8000.log 2>&1 &
tail -f logs/cloudflared-8000.log
```

复制日志中生成的 `https://*.trycloudflare.com` 地址，然后更新 Android 的 `AppConfig.kt`。

公网验证：

```powershell
curl.exe -sS https://<your-subdomain>.trycloudflare.com/health
```

## 接口概览

```text
GET  /health
GET  /api/products
GET  /api/cart
POST /api/cart/checkout
POST /api/stt
WS   /ws/chat
```

WebSocket 主要事件：

```text
text_delta
products_start
product_item
recommendations_ready
cart_update
audio_delta
audio_done
done
error
```

Android 不在客户端写商品推荐逻辑；商品匹配、价格过滤、购物车真实状态、语音识别和 TTS 都以后端为准。

## 发布 APK 到 GitHub 的建议

推荐使用 GitHub Releases：

```text
GitHub Releases
  -> 上传 app-debug.apk 或 signed release APK
  -> Release Notes 写清楚当前公网后端地址、支持功能、已知限制
  -> README 放 Release 下载入口
```

不建议把 APK 长期直接提交到主分支，原因是：

- APK 是构建产物，不是源码。
- 每次更新都会增加仓库体积。
- GitHub Releases 更适合管理版本、下载链接和变更说明。

如果公网后端地址稳定，用户下载 APK 后就可以直接使用；如果 Cloudflare 临时地址变化，旧 APK 会连不上，需要重新打包并发布新 Release。

## 常见问题

### App 显示连接失败

先检查公网后端：

```powershell
curl.exe -sS https://continually-replication-allowing-editions.trycloudflare.com/health
```

如果失败，通常是后端进程或 Cloudflare Tunnel 已停止。

### 语音识别失败

确认：

- 手机已授权录音权限。
- `/api/stt` 可访问。
- 后端 ASR provider 已配置并运行。

快速检查：

```bash
curl -fsS http://127.0.0.1:8000/openapi.json | grep /api/stt
```

### 商品图片不显示

确认公网后端可访问商品图片资源，并检查 App 当前 `BASE_HTTP_URL` 是否和后端公网地址一致。

### 自己部署后端后 App 仍连接旧服务

更新 `AppConfig.kt` 后必须重新编译并安装 APK。

## 验收命令

Android：

```powershell
cd android
.\gradlew.bat :app:testDebugUnitTest
.\gradlew.bat :app:assembleDebug
```

后端：

```bash
env/venv_shopguide_backend/bin/python -m pytest -q
curl -fsS http://127.0.0.1:8000/health
```
