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

### 首次运行：搭建 Python 虚拟环境（约 3 分钟）

```bash
bash server/scripts/setup_backend_env.sh
```

### 启动后端（默认 8000 端口）

```bash
cd server
nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
  --log-level info --timeout-keep-alive 120 --ws-ping-interval 20 \
  --ws-ping-timeout 10 --limit-concurrency 20 \
  > /tmp/souldance-backend.log 2>&1 &
```

> 启动日志写入 `/tmp/souldance-backend.log`，可通过 `tail -f /tmp/souldance-backend.log` 实时查看。

看到以下输出表示启动成功：

```
INFO: Uvicorn running on http://0.0.0.0:8000
```

验证：

```bash
curl http://127.0.0.1:8000/health
# 返回: {"status":"ok"}
```

### 代码更新后重启后端

修改代码后，先停旧进程再重新启动：

```bash
kill $(ps aux | grep "uvicorn.*8000" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2 && cd server
nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
  --log-level info --timeout-keep-alive 120 --ws-ping-interval 20 \
  --ws-ping-timeout 10 --limit-concurrency 20 \
  > /tmp/souldance-backend.log 2>&1 &
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

## v2.0 新特性体验

v2.0 版本新增了多项核心能力。以下测试查询可快速验证新特性是否正常工作：

| 测试查询 | 测试目标 | 预期效果 |
|---------|---------|---------|
| "推荐一款6000元左右的小米手机" | 带品牌约束的商品推荐 | 返回符合小米品牌、价位在 6000 元附近的手机推荐卡片 |
| "分析一下小米 17Max的优缺点" | product_analysis + CJK-ASCII 归一化 | AI 对"小米 17Max"进行优缺点分析，中文品牌与英文型号正常识别匹配 |
| "有没有便宜一点的替代品？" | 更便宜替代品追问 | 基于上一轮推荐结果，返回价位更低但功能相近的替代商品 |
| "帮我对比一下第一款和第二款" | 多商品对比 | 列出两款商品在价格、配置、适用场景等维度的详细对比 |

> **提示**："有没有便宜一点的替代品？"和"帮我对比一下第一款和第二款"需要在前面已有一轮推荐对话的上下文中使用，属于多轮追问场景。

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
kill $(ps aux | grep "uvicorn.*8000" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 1
cd server && nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
  --log-level info --timeout-keep-alive 120 --ws-ping-interval 20 \
  --ws-ping-timeout 10 --limit-concurrency 20 \
  > /tmp/souldance-backend.log 2>&1 &
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

### Q: LLM 调用超时

LLM API 偶发超时属正常现象，等待几秒后重试即可。若持续超时，检查：
1. API Key 是否有效：确认 `.env` 中 `LLM_API_KEY` 正确
2. 网络连通性：`curl -I https://api.deepseek.com`
3. 模型配额是否耗尽：登录 DeepSeek 控制台查看用量

### Q: 对话回复"服务暂时不可用"

出现此提示时，检查后端日志定位具体原因：

```bash
tail -50 /tmp/souldance-backend.log
```

常见原因包括 LLM API 返回错误、工具调用失败或服务内部异常。日志中会有详细错误堆栈。

### Q: WebSocket 频繁断开

Cloudflare tunnel 对长连接有超时限制。如 WebSocket 频繁断开：
1. 尝试重建 tunnel（停掉旧 tunnel 进程后重新运行 `cloudflared tunnel`）
2. 改用 `adb reverse` 进行本地测试可完全避免此问题

### Q: 回复很慢

plan_tool + stream_response 两轮 LLM 调用合计 20-40s 是正常范围。观察 `/dev` 仪表盘的延时数据来确认瓶颈。

---

## 评委快速体验 Checklist

- [ ] `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`
- [ ] curl 发 "华为 Pura 90 Pro 价格" → 得到带商品知识的自然回复
- [ ] curl 发 "心情不好推荐甜的" → 得到先共情再推荐的真实商品卡片
- [ ] curl 发 "推荐一款咖啡" → 得到含锚点的推荐回复 + product_item 事件
- [ ] curl 发 "推荐一款6000元左右的小米手机" → 得到品牌约束推荐（v2.0）
- [ ] curl 发 "分析一下小米 17Max的优缺点" → 得到产品分析回复（v2.0）
- [ ] 浏览器打开 `/dev` → 看到 6 张统计卡片 + 图表
- [ ] (可选) 安装 APK 手机上体验完整对话交互
