# Android 与后端协议说明

## WebSocket 地址

```text
/api/chat/realtime
```

## 客户端发给后端

### user_message

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

### product_followup

```json
{
  "type": "product_followup",
  "session_id": "demo_session_001",
  "focus_product_id": "sku_101",
  "message": "这个有点贵，有没有100以内的？",
  "tts_enabled": true
}
```

### cart_action

可选，如果购物车操作走 WebSocket：

```json
{
  "type": "cart_action",
  "session_id": "demo_session_001",
  "action": "add_to_cart",
  "product_id": "sku_101",
  "quantity": 1
}
```

## 后端发给 Android

```text
text_delta
products_start
product_item
products_done
bundle_start
bundle_item
bundle_done
focus_text_delta
replacement_product
focus_done
audio_delta
cart_update
done
error
```

## REST 接口

```http
GET  /api/cart?session_id=xxx
POST /api/cart/add
POST /api/cart/add_bundle
POST /api/cart/update_quantity
POST /api/cart/remove
POST /api/cart/select
POST /api/cart/clear
POST /api/cart/checkout
```

## 错误处理原则

```text
1. TTS 失败不影响文字和商品卡片。
2. 商品图片失败显示 fallback。
3. WebSocket 断开显示提示，可重连。
4. 商品详情 followup 失败只影响 BottomSheet，不清空聊天。
5. 购物车失败必须明确提示用户。
```
