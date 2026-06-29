# SoulDance · 灵舞 — 部署与体验指南

本文档面向评委和首次体验者，帮助你最快 5 分钟内完成部署并体验核心功能。

---

## 体验路径总览

```
1. 克隆仓库 → 2. 配置 LLM → 3. 启动后端 → 4. 安装 APK → 5. 开始对话
```

核心体验只需 **一台 Linux 服务器 + 一部 Android 手机**，或**仅服务器**（通过 curl 测试 API）。

---

## 第一步：克隆仓库

```bash
git clone git@github.com:HOU-LONG/SoulDance.git
cd SoulDance
```

---

## 第二步：配置 LLM API Key

编辑仓库根目录的 `.env` 文件（如不存在则新建）：

```bash
# 必填 — LLM Provider
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx    # 你的 DeepSeek API Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_FAST_MODEL=deepseek-v4-flash
```

> 也支持豆包 (doubao)：设置 `LLM_PROVIDER=doubao` + `ARK_API_KEY=ark-xxx`。

---

## 第三步：启动后端

```bash
# 首次运行：搭建 Python 虚拟环境（约 3 分钟）
bash server/scripts/setup_backend_env.sh

# 启动后端（默认 8000 端口）
bash server/scripts/start_backend.sh
```

看到以下输出表示启动成功：

```
INFO: Uvicorn running on http://0.0.0.0:8000
```

验证：

```bash
curl http://127.0.0.1:8000/health
# 返回: {"status":"ok"}
```

---

## 第四步（二选一）：通过 API 体验 或 安装 APK 体验

### 选项 A：curl API 体验（无需手机）

直接用 curl 测试 3 个核心场景：

```bash
# 场景 1：问商品价格（product_analysis）
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" -H "X-User-Id: demo_user_a" \
  -d '{"type":"user_message","session_id":"exp1","message":"华为 Pura 90 Pro 价格多少"}'

# 场景 2：情绪 + 购物复合需求（chitchat + 推荐）
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" -H "X-User-Id: demo_user_a" \
  -d '{"type":"user_message","session_id":"exp2","message":"心情不好，推荐点甜的"}'

# 场景 3：商品推荐
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" -H "X-User-Id: demo_user_a" \
  -d '{"type":"user_message","session_id":"exp3","message":"推荐一款咖啡"}'
```

每次请求会返回流式 JSON 事件数组，其中 `text_delta` 为 AI 回复文本，`product_item` 为商品卡片。

### 选项 B：安装 APK 体验（需要 Android 手机）

**前置条件**：JDK 17+、Android SDK、Kotlin 工具链已安装。

#### B1. 暴露公网（Cloudflare Tunnel）

让手机能访问服务器上的后端：

```bash
cloudflared tunnel --url http://127.0.0.1:8000 &
# 终端会打印 tunnel URL，如 https://xxx.trycloudflare.com
```

#### B2. 构建 APK

```bash
cd client
export JAVA_HOME=/path/to/android-studio/jbr
export ANDROID_HOME=/path/to/android-sdk
./gradlew :app:assembleDebug
```

Gradle 编译时会自动检测 Cloudflare tunnel 并将 URL 写入 AppConfig。

> 离线开发可跳过 tunnel 检查：
> ```bash
> SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
> ```
> 然后手动编辑 `client/.../config/AppConfig.kt` 填入 tunnel URL。

#### B3. 安装 APK

```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

#### B4. 打开 App 开始对话

App 首页是精灵空间（Sprite Home），点击聊天按钮进入对话页面。

**推荐体验话术**：

| 话术 | 预期效果 |
|------|---------|
| "华为 Pura 90 Pro 价格多少" | AI 用通用知识回答 + 标注本店不一定在售 |
| "推荐一款防晒霜" | 推荐主推商品卡片 + 备选缩略图 |
| "今天心情不好，推荐点甜的" | AI 先共情"吃点甜的确实治愈"，再自然带出两款真实商品卡片 |
| "这个多少钱？"（接上条） | 直接告知刚才焦点商品的价格 |
| "换个更便宜的" | 推荐一款更便宜的替代品 |
| "加入购物车" | 购物车操作 |

---

## 开发者控制台（可选）

后端启动后访问：

```
http://127.0.0.1:8000/dev
```

仪表盘实时显示：
- **6 张统计卡片**：平均延迟 / 首个 Token 延迟 / 平均 Token 消耗 / 累计 Token / 总请求数 / Plan 占比
- **延时趋势折线图**：最近 50 条请求的端到端延迟
- **Tool 分布饼图**：7 种工具的使用比例
- **请求明细表格**：每条请求的消息、工具、延时、Token、错误

通过公网 tunnel 也可访问：`https://xxx.trycloudflare.com/dev`

仪表盘还支持 **Prompt 热更新** — 在网页上直接修改 LLM 系统提示并即时生效，无需重启后端。

---

## 环境要求

| 组件 | 要求 |
|------|------|
| 操作系统 | Linux (推荐 Ubuntu 20.04+) |
| Python | 3.12+ |
| JDK | 17+ (仅构建 APK 时需要) |
| Android SDK | 36+ (仅构建 APK 时需要) |
| 内存 | ≥ 4GB (含 embedding 模型) |
| 磁盘 | ≥ 2GB |
| 网络 | 需访问 DeepSeek API (api.deepseek.com) |

---

## 常见问题

### Q: 后端启动报 "Port 8000 already used"

```bash
kill $(lsof -ti :8000) && bash server/scripts/start_backend.sh
```

### Q: APK 编译报 "Tunnel check failed"

使用离线模式：
```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```

### Q: 手机 App 显示"连接中断"

1. 确认后端存活：`curl http://127.0.0.1:8000/health`
2. 确认 Cloudflare tunnel 域名与 AppConfig 一致
3. 如是内网环境，可用 `adb reverse` 替代 tunnel：
   ```bash
   adb reverse tcp:8000 tcp:8000
   ```
   然后将 AppConfig 的 URL 改为 `http://127.0.0.1:8000`

### Q: 回复很慢

plan_tool + stream_response 两轮 LLM 调用合计 20-40s 是正常范围。观察 `/dev` 仪表盘的延时数据来确认瓶颈。

---

## 评委快速体验 Checklist

- [ ] `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`
- [ ] curl 发 "华为 Pura 90 Pro 价格" → 得到带商品知识的自然回复
- [ ] curl 发 "心情不好推荐甜的" → 得到先共情再推荐的真实商品卡片
- [ ] curl 发 "推荐一款咖啡" → 得到含锚点的推荐回复 + product_item 事件
- [ ] 浏览器打开 `/dev` → 看到 6 张统计卡片 + 图表
- [ ] (可选) 安装 APK 手机上体验完整对话交互
