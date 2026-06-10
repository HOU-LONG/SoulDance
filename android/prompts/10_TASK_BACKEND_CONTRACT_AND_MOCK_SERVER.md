# Task 10：后端协议对齐与 Android Mock Server

## 目标

让 Android 在后端未完全完成时也能独立开发和演示。实现一个简单的 Mock WebSocket/REST 服务器，返回固定的流式事件。

## 适用场景

```text
1. Android 端需要先做 UI 和流式渲染。
2. 后端 RAG 还没完全联调。
3. Demo 前需要稳定备用数据。
```

## Mock Server 技术

建议用 Python FastAPI。

```text
server/mock_android_api.py
```

## 需要模拟的接口

```text
WS   /api/chat/realtime
GET  /api/cart?session_id=xxx
POST /api/cart/add
POST /api/cart/add_bundle
POST /api/cart/update_quantity
POST /api/cart/remove
POST /api/cart/checkout
```

## Mock WebSocket 流程：普通推荐

收到：

```json
{
  "type": "user_message",
  "message": "推荐防晒霜，但不要含酒精的，也不要日系品牌"
}
```

依次返回：

```text
1. text_delta 若干次
2. products_start
3. product_item primary
4. product_item alternative
5. products_done
6. done
```

## Mock WebSocket 流程：商品级追问

收到：

```json
{
  "type": "product_followup",
  "focus_product_id": "sku_101",
  "message": "这个有点贵，有没有100以内的？"
}
```

依次返回：

```text
1. focus_text_delta 若干次
2. replacement_product
3. focus_done
```

## Mock WebSocket 流程：三亚组合

收到包含“三亚度假”的 query 后返回：

```text
1. text_delta
2. bundle_start
3. bundle_item 防晒护理 / 防晒霜
4. bundle_item 防晒护理 / 晒后修复
5. bundle_item 穿搭 / 轻薄外套
6. bundle_item 出行配件 / 遮阳帽
7. bundle_done
8. done
```

## 验收标准

```text
1. Android 连接 Mock Server 可以跑通所有 UI。
2. 断开真实后端时仍能做前端演示。
3. Mock 数据覆盖普通推荐、反选、场景组合、商品追问、购物车。
```

## 给 Codex/Claude Code 的执行提示

```text
请在 server/mock_android_api.py 中实现一个 FastAPI mock server，用于 Android 端联调。
不要实现真实 RAG，只返回固定流式事件。
同时补充 README_MOCK_SERVER.md，说明如何启动和 Android 如何配置 BASE_URL。
```
