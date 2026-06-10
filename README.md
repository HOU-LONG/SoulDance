# SoulDance / ShopGuide Agent

SoulDance 是一个低压力 AI 导购 Agent：用户用自然语言说出需求，系统理解预算、品牌、用途和负向偏好，从商品库中给出一个主推商品、少量备选、商品卡片、购物车操作和语音交互。

项目包含 Android 原生客户端和 FastAPI 后端，当前 App 默认连接公网服务，安装 APK 后即可体验。

## 30 秒快速体验

1. 在 GitHub Releases 下载最新 APK。
2. 安装到 Android 真机，允许录音权限。
3. 打开 App 后直接输入或语音说：

```text
我想要一杯不超过30元的咖啡
我要一瓶东鹏特饮
推荐一款拍照好的手机，预算8000
把小米17ultra加入购物车
清空购物车
不要雀巢，换一个同类推荐
```

当前公网服务：

```text
HTTP API: https://continually-replication-allowing-editions.trycloudflare.com/
WebSocket: wss://continually-replication-allowing-editions.trycloudflare.com/ws/chat
```

说明：APK 建议通过 GitHub Releases 分发，不提交到 git 历史。当前 Cloudflare Tunnel 是公网演示地址，如果地址变化，需要重新打包 APK。

## 核心能力

- 自然语言导购：理解商品类别、预算、品牌、用途、排除项和多轮追问。
- 精准商品卡片：默认主推一个商品，必要时给 1-2 个备选，避免搜索引擎式堆结果。
- 上下文追问：围绕某款商品继续问，例如“不要雀巢”“换便宜点”“更适合拍照吗”。
- 购物车闭环：支持自然语言加购、清空购物车、购物车页面结算和我的订单展示。
- 语音交互：支持语音输入、流式语音播报和会话级静音。
- 公网演示：Android 客户端可直接连接已公开的后端服务，便于评委和体验用户快速验证。

## 演示路径

建议按下面顺序体验：

1. 商品理解：输入“我想要一杯不超过30元的咖啡”，确认不会出现超预算商品。
2. 精确检索：输入“我要一瓶东鹏特饮”，确认能找到商品库中的东鹏特饮。
3. 多轮追问：点击商品卡片下方建议，或输入“不要这个品牌”，确认返回新的推荐。
4. 自然语言加购：输入“把小米17ultra加入购物车”，确认购物车里是真实的小米商品且数量为 1。
5. 购物车操作：进入购物车，增减数量、清空购物车、结算。
6. 订单展示：结算后进入“我的订单”，确认页面稳定且订单可展示。
7. 语音体验：按住语音键说需求，松开发送，上滑取消；当前会话可静音。

## 系统架构

```text
Android App
  Kotlin + Jetpack Compose
  MVVM + StateFlow
  OkHttp / Retrofit / WebSocket
  SpeechRecognizer + streaming TTS playback

FastAPI Backend
  商品数据加载与图片资源服务
  BM25 / embedding 检索
  语义解析与推荐编排
  购物车与订单 demo 服务
  STT / TTS 适配层

Data
  ecommerce_agent_dataset/
  商品 JSON、图片、评论和派生标签
```

Android 只负责 UI 状态、发送正确 payload、展示后端结果；商品推荐、商品匹配、价格过滤和购物车真实状态由后端负责。

## 仓库结构

本仓库采用单主分支 monorepo，按目录区分客户端和后端：

```text
SoulDance/
  android/     Android Kotlin + Jetpack Compose 客户端
  backend/     FastAPI 后端服务
  docs/        技术说明、验收清单和运行文档
  tests/       后端测试
```

不建议用两个长期分支分别保存 Android 和后端。功能开发可以使用短期分支，例如 `feature/cart-fix`；主分支保留完整产品，便于 clone、评审、发布和版本对应。

## Android 开发

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

本地编译：

```powershell
cd android
$env:JAVA_HOME='C:\Users\houlong\.jdks\jbr-21.0.11'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
.\gradlew.bat :app:testDebugUnitTest
.\gradlew.bat :app:assembleDebug
```

APK 输出：

```text
android\app\build\outputs\apk\debug\app-debug.apk
```

安装到真机：

```powershell
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
```

如果 Windows 中文路径导致 JUnit 类加载异常，可指定 ASCII 构建目录：

```powershell
$env:SHOPGUIDE_ANDROID_BUILD_DIR='C:\path\to\android-build'
```

## 后端开发

安装依赖后在仓库根目录运行：

```bash
python -m pytest -q
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

本机验证：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS "http://127.0.0.1:8000/api/cart?session_id=demo_session_001"
```

公网验证：

```powershell
curl.exe -sS https://continually-replication-allowing-editions.trycloudflare.com/health
```

## 主要接口

```text
GET  /health
GET  /api/products
GET  /api/cart
POST /api/cart/add
POST /api/cart/clear
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

## 测试与验收

后端：

```bash
python -m pytest -q
```

Android：

```powershell
cd android
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

关键验收点：

- “不超过30元的咖啡”不返回超预算商品。
- “我要一瓶东鹏特饮”能命中商品库真实商品。
- “把小米17ultra加入购物车”加入小米 17 Ultra，数量为 1，不会加入主推 OPPO 17 件。
- 点击购物车和我的订单不闪退，同步失败时保留本地状态并显示原因。
- Markdown 结构化文本正常显示，语音播报不读出 Markdown 符号。

## 发布 APK

推荐使用 GitHub Releases：

```text
GitHub Releases
  -> 上传 app-debug.apk 或 signed release APK
  -> Release Notes 写清楚公网后端地址、主要功能、已知限制
  -> README 放 Release 下载入口
```

不建议把 APK 长期提交到主分支：

- APK 是构建产物，不是源码。
- 每次更新都会增加仓库体积。
- Releases 更适合管理版本、下载链接和变更说明。

## 常见问题

### App 显示连接失败

先检查公网后端：

```powershell
curl.exe -sS https://continually-replication-allowing-editions.trycloudflare.com/health
```

如果失败，通常是后端进程或 Cloudflare Tunnel 停止。

### 语音识别失败

确认手机已授权录音权限，并检查 `/api/stt` 是否可访问。后端未配置 STT provider 时应返回明确错误，Android 会显示失败原因。

### 商品图片不显示

确认 App 当前 `BASE_HTTP_URL` 与后端公网地址一致，并检查商品图片路径是否能通过公网访问。

### 自己部署后端后 App 仍连接旧服务

更新 `AppConfig.kt` 的 HTTP/WS 地址后，必须重新编译并安装 APK。
