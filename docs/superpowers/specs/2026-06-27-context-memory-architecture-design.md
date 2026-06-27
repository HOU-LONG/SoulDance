# 对话上下文分层存储与 Prompt 注入 — 设计文档

> 基于 SoulDance 现有 SessionContext / ConstraintState / Cache 体系的增量扩展。目标文档中已实现的部分不变，本文档只描述增量。

## 一、Phase 1：全量对话流水 + Response Prompt 注入历史

### 1.1 全量对话流水（形态A）

**现状：** 无 `[{role, content}]` 格式存储。`focus_history` 仅记录 followup 时的 user 消息，`context_events` 只存结构化标签。

**增量：** 在 `SessionContext` 中新增 `dialog_turns` 字段，存储完整用户-助手对话轮次。

```python
# models.py — SessionContext 新增字段
dialog_turns: list[dict[str, str]] = Field(default_factory=list)
# 每项：{"role": "user", "content": "..."} 或 {"role": "assistant", "content": "..."}
# 以"消息条数"计量：50 条消息 = 25 轮完整对话
```

**写入时机：**
- User 消息：`stream_message()` 入口，在处理前立即 append `{"role": "user", "content": request.message}`
- Assistant 回复：采用 buffer 收集模式——`stream_message` 内部对每个 yielded text_delta 同时 append 到内存 buffer，在 `yield {"type": "done"}` 之前将 buffer 拼接为完整文本并 append `{"role": "assistant", "content": full_text}`。此方案不增加首字延迟（buffer 是追加操作，不影响 yield 时机）
- **中断处理**：如果流在中途断开（连接异常、超时），`dialog_turns` 中只有 user 消息没有对应 assistant 回复。此时写入一条占位 assistant 消息 `{"role": "assistant", "content": "[回复中断]"}`，避免后续 Prompt 拼装时出现 user-assistant-user-user 这样不对称的角色序列
- 容量控制：保留最近 100 条消息（50 轮完整对话）；超过后截断最旧的 10 条，被截断部分进入摘要（Phase 2 接管）

**持久化：** `dialog_turns` 随 `SessionContext` 经 `SessionStore.save()`（文件模式 → `model_dump_json()`）和 `SessionRepository.save()`（DB 模式 → `state_json` JSONB 列）自动持久化。会话重启恢复时 Pydantic `default_factory=list` 保证旧 `state_json` 不含此字段时不报错。

**Schema 升级：** `SessionContext.schema_version` 从 `1` 升至 `2`。加载旧版本数据时不做迁移——`dialog_turns` 从空列表开始积累。

### 1.2 Response Prompt 注入对话历史

**现状：** Response LLM（`stream_response`）的 system prompt 无对话历史，只看到当前约束和候选产品。

**增量：** 在 `_response_evidence_payload` 中新增 `recent_context_text` 字段，拼接最近 N 轮对话和摘要。

```python
# llm_client.py — _response_evidence_payload 新增
def _response_evidence_payload(..., context: SessionContext | None = None):
    ...
    recent_context_text = _build_recent_context_text(context) if context else ""
    return {
        ...原有字段...
        "recent_context_text": recent_context_text,
    }
```

**Prompt 拼装规则：**
- 如果 `dialog_turns` ≤ 20 条消息（10 轮完整对话）：注入全部
- 如果 > 20 条消息：注入 `[对话历史摘要] + 最近 10 条消息（5 轮完整对话）`
- 摘要来源：Phase 2 之前用占位文本 "前 N 轮为购物咨询对话，用户当前需求如上"，Phase 2 之后用 `context.compression_state.living_summary.text`
- System prompt 追加指令："以下是用户与本助手的近期对话历史，请基于历史理解用户当前意图。"

**Prompt 模板修改**（`prompts/v1/response.txt`）：
```
## 对话历史上下文
{recent_context_text}

## 当前需求
用户最新消息：{user_message}
{约束短句}

## 回答合同
(原有内容不变)
```

### 1.3 约束短句生成

当有对话历史时，将 `hard_constraints` 和关键 `soft_preferences` 转为自然语言短句注入 Prompt：

```
已知用户条件：预算500以内、排除品牌华为；偏好：干性皮肤、秋冬季节。
```

**生成函数**（纯规则，不调用 LLM）：
```python
def _constraint_sentence(plan: RetrievalPlan) -> str:
    parts = []
    h = plan.hard_constraints
    if h.price_max is not None:
        parts.append(f"预算{h.price_max:.0f}以内")
    if h.exclude_brands:
        parts.append(f"排除品牌{'、'.join(h.exclude_brands)}")
    if h.include_brands:
        parts.append(f"指定品牌{'、'.join(h.include_brands)}")
    for k, v in plan.soft_preferences.items():
        if k not in ("anchor_reference", "price_preference"):
            parts.append(f"{v}")
    return "已知用户条件：" + "、".join(parts) + "。" if parts else ""
```

---

## 二、Phase 2：LivingSummary + context_compression 集成

### 2.1 存储模型集成

**已有模型：**
- `LivingSummary`（`models.py:291`）— `text`、`covered_part_ids`、`updated_turn`、`source_token_count`
- `SessionCompressionState`（`models.py:304`）— 内置 `living_summary`、`watermark_level`、`decisions`、`total_tokens`

**集成方式（新增一个字段，不引入双重 living_summary）：**
```python
# models.py — SessionContext 新增
compression_state: SessionCompressionState = Field(default_factory=SessionCompressionState)
```
摘要永远从 `context.compression_state.living_summary` 读取，不在 SessionContext 上单独放 `living_summary` 字段。

`SessionCompressionState` 随 `SessionContext` 由 `SessionStore.save()` / `SessionRepository.save()` 自动持久化。`compression_state.living_summary` 初始为 `LivingSummary()`（空文本），无摘要时不注入 Prompt。

### 2.2 摘要触发与生成

**触发条件：** 在 `stream_message` 末尾（所有退出路径 return 之前），调用 `_maybe_update_summary`：
- `dialog_turns` ≥ 16 条消息（8 轮完整对话）
- 距上次摘要已新增 ≥ 6 条消息（3 轮）
- 仅以下路径触发：recommendation、product_followup、compare_products；澄清/闲聊/错误不触发

```python
def _maybe_update_summary(self, context: SessionContext):
    turns = context.dialog_turns
    last = context.compression_state.living_summary.updated_turn
    if len(turns) < 16:
        return
    if len(turns) - last < 6:
        return
    # 生成摘要...见 2.3
```

### 2.3 摘要 Prompt 模板

使用已有的 `FakeLLMClient` 兼容接口生成摘要——新增一个 `generate_summary` 方法在 `llm_client.py` 中。

**Prompt 模板**（新增 `prompts/v1/summary.txt`）：
```
你是一个购物助手的对话摘要器。请将以下对话历史浓缩为 1-2 句中文摘要，
聚焦于用户的购物需求、已查看的商品、明确的约束条件和偏好。
不要包含闲聊细节。只返回摘要文本，不要添加前缀或解释。

对话历史：
{history_text}

摘要：
```

**输入构建：** 将 `dialog_turns` 的 `[role] content` 格式转为多行纯文本。

**调用方式：** 使用同步 `self.llm_client._json_completion`（非流式），不阻塞 `stream_message` 的 yield——在 `yield done` 之后、函数 return 之前调用。

**降级策略：**
- FakeLLMClient：`generate_summary()` 返回 `"前几轮为购物咨询对话，用户当前需求如上。"`
- LLM 超时（3s）：跳过本轮摘要，`updated_turn` 不更新
- LLM 返回空/异常：跳过本轮摘要

### 2.4 摘要持久化

- `living_summary.text` 更新为最新摘要文本
- `living_summary.covered_part_ids` 记录被摘要覆盖的 `dialog_turns` 索引范围 `[0..N]`
- `living_summary.updated_turn` 记录摘要时的 `len(dialog_turns)`
- `living_summary.source_token_count` 记录被摘要的原始对话 token 数（估计值）
- 随 SessionContext 持久化，下次会话恢复时摘要可用

### 2.5 摘要注入 Prompt

在 `_build_recent_context_text` 中：

```python
def _build_recent_context_text(context: SessionContext) -> str:
    parts = []
    ls = context.compression_state.living_summary
    # 1. 摘要
    if ls.text:
        parts.append(f"[之前对话摘要] {ls.text}")
    # 2. 最近 10 条消息（5 轮完整对话）
    recent = context.dialog_turns[-10:]
    for turn in recent:
        role = "用户" if turn["role"] == "user" else "助手"
        parts.append(f"{role}：{turn['content']}")
    return "\n".join(parts)
```

---

## 三、Phase 3：intent_domain 跟踪 + model_attr_map

### 3.1 intent_domain 跟踪

**现状：** `_prepare_context_for_turn` 判断 `same_task/new_task/clarification_answer` 三态，但不跟踪具体的 domain 切换（如从精华切到手机）。

**增量：**

```python
# models.py — ConstraintState 新增
class ConstraintState(BaseModel):
    ...现有字段...
    current_domain: str | None = None  # "美妆护肤" / "数码电子" / ...
```

```python
# agent.py — _prepare_context_for_turn 新增逻辑
def _detect_domain_switch(self, new_plan, context):
    new_domain = new_plan.hard_constraints.category
    if not new_domain:
        return False
    old_domain = context.state.constraint_state.current_domain
    if old_domain and old_domain != new_domain:
        return True
    context.state.constraint_state.current_domain = new_domain
    return False
```

**域切换时的行为：**
1. 清空 `soft_preferences`（肤质参数不适用于手机）
2. 清空 `reference_anchors` 中所有以 `first_turn_` 为前缀的 key（"回到第一轮"在域切换后不再有语义）
3. 保留 `last_cheaper_alternative` 等与产品直接关联的 anchor
4. 重置 `last_product_ids = []` 和 `focus_product_id = None`
5. 清空 `recommendation_memory.items = []` 和 `last_set_id = None`
6. 保留 `dialog_turns` 和 `compression_state`（对话连续性）
7. 保留 `entity_params`（产品参数跨域有效）

**`current_domain` 为 None 时的行为：** 当 `plan.hard_constraints.category` 为 `None`（用户未指定品类），不更新 `current_domain`，不触发域切换逻辑。

### 3.2 model_attr_map（按产品缓存参数）

**增量：**

```python
# models.py — SessionContext 新增
entity_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
# {"p_beauty_001": {"price": 720, "brand": "雅诗兰黛", "category": "美妆护肤", ...}}
```

**写入时机：** `_remember_recommendations` 调用时，对 `final_selected` 中的每个产品提取属性：
```python
for item in final_selected:
    pid = item.product.product_id
    if pid not in context.entity_params:
        context.entity_params[pid] = {
            "price": item.product.price,
            "brand": item.product.brand,
            "category": item.product.category,
            "sub_category": item.product.sub_category,
        }
```

**容量控制：** `entity_params` LRU 上限为最近 50 个产品。超出时删除最旧条目（用 `insertion_order` 或独立 `_entity_params_order` 队列跟踪）。

**读取时机：**
- 比较请求中提及的产品 ID 若在 `entity_params` 中 → 从缓存提供属性，不额外调用 `hard_filter`
- 后续 "那个重的手机多少克" 类问题 → 先查 `entity_params`，命中则直接返回参数，无需检索
- 读取路径在 `_build_comparison_events` 的产品解析阶段——`entity_params.get(pid)` 替代 `self.product_map.get(pid)` 的部分属性查询

**互斥规则：** `entity_params` 只在推荐完成时写入，不在对话中随意覆盖。产品 ID 必须来自 `product_map`（已验证存在），避免幻觉产品 ID。

---

## 四、数据流汇总

```
用户 query
  │
  ├─ 1. append dialog_turns[role=user]  (Phase 1)
  │
  ├─ 2. SemanticParser → StateReducer → ConstraintState  (已有)
  │
  ├─ 3. detect_domain_switch  (Phase 3)
  │      └─ 若切换：reset soft_prefs + mark anchors stale
  │
  ├─ 4. QueryBuilder.build → retrieve_and_rank  (已有)
  │      ├─ entity_params 写入  (Phase 3 新增)
  │      └─ Cache B1/B2 命中判断  (已有)
  │
  ├─ 5. 拼装 Prompt  (Phase 1-2 改造)
  │      ├─ System Prompt
  │      ├─ 约束短句 (Phase 1)
  │      ├─ living_summary  (Phase 2)
  │      ├─ 最近 5 轮 dialog_turns  (Phase 1)
  │      ├─ 当前 query
  │      └─ 候选产品
  │
  ├─ 6. LLM stream_response
  │
  └─ 7. 回写
         ├─ dialog_turns[role=assistant]  (Phase 1)
         ├─ maybe_update_summary  (Phase 2)
         └─ save context  (已有)
```

---

## 五、兼容性约束

- `dialog_turns` 的 `role` 取值固定为 `"user"` / `"assistant"`，不得用其他值
- `living_summary.text` 限 200 字以内
- `entity_params` 只缓存 `产品级` 属性，不缓存 session 级偏好
- FakeLLMClient 测试路径每次对话用固定摘要文本，不引入不确定性
- 所有新增字段（dialog_turns, living_summary, entity_params, current_domain）均需在 `SessionContext.model_dump` 和 DB JSONB 序列化路径中正确往返

---

## 六、迁移、回滚与兼容性

### 6.1 数据迁移

- 不需要主动迁移脚本。所有新增字段使用 `default_factory`（`Field(default_factory=list/dict/SessionCompressionState)`），Pydantic 自动填充默认值
- 旧 `state_json` 加载：`model_validate(old_json)` 不报错（已确认 `model_config.extra="ignore"`），新字段取默认值

### 6.2 回滚策略

- Phase 1 上线后回滚：`dialog_turns` 和 `compression_state` 字段存在于 `state_json` 中。回滚到旧代码后，Pydantic `extra="ignore"` 静默丢弃未知字段，数据不丢失
- Phase 2 回滚：`living_summary` 和 `compression_state` 数据留在 JSON 中但不再被读取或更新
- `schema_version` 从 1 升到 2：回滚时旧代码检查 `schema_version == 2` 无特殊逻辑（不会报错）

### 6.3 Phase 1 → Phase 2 升级

- Phase 1 已存的 `dialog_turns` 字段保留
- Phase 2 新增 `compression_state`，存量会话用 `default_factory` 初始化
- `_maybe_update_summary` 对存量会话的初始 `updated_turn = 0`，会尝试为全部历史生成摘要——这是预期行为，一次性的历史浓缩

---

## 七、可观测性

| 指标 | 方式 |
|------|------|
| `dialog_turns` 长度 | `logger.debug` 每轮写入后记录 `len(context.dialog_turns)` |
| 摘要生成 | `logger.info` 记录成功/失败/耗时 ms，附带 `session_id` 前 8 位 |
| 域切换事件 | `logger.info` 记录 `domain_switch from={old} to={new}` |
| `entity_params` 大小 | 写入时若超过 50 条触发 `logger.warning`（LRU 淘汰） |
| Prompt token 估计 | 复用以有的 `_estimate_tokens` 函数，在拼装完成后记录 |

---

## 八、验证方法

### Phase 1
1. **空对话 Prompt：** `dialog_turns=[]`、无摘要时，`_build_recent_context_text` 返回空字符串，Prompt 模板不崩溃
2. **单元测试：** 发送 3 轮对话，断言 `context.dialog_turns` 含 6 条消息（3 user + 3 assistant），role 正确
3. **集成测试：** `_response_evidence_payload` 的 `recent_context_text` 包含最近 user message 文本
4. **边界测试：** 恰好 20 条消息时全部注入；第 21 条时切换到 "摘要 + 最近 10 条"

### Phase 2
5. **单元测试：** 模拟 10 轮对话，断言 `_maybe_update_summary` 触发，`compression_state.living_summary.text` 非空
6. **集成测试：** 长对话 Prompt 包含 `[之前对话摘要]` 前缀和最近 10 条消息
7. **非触发路径：** 澄清/闲聊/错误响应后 `_maybe_update_summary` 不触发
8. **降级测试：** FakeLLMClient 摘要返回固定文本；异常时 `updated_turn` 不更新

### Phase 3
9. **域切换：** 发送精华推荐 → 发送手机推荐，断言 `current_domain` 从 "美妆护肤" 切换为 "数码电子"，`soft_preferences` 清空、`recommendation_memory.items` 清空
10. **category=None：** 连续两轮不指定品类的推荐 → `current_domain` 不更新、不触发域切换
11. **entity_params 写入：** 推荐完成后 `entity_params` 包含被推荐产品的 price/brand/category
12. **entity_params LRU：** 写入 51 个产品后断言最旧条目被淘汰

### 全量回归
13. `pytest -q --maxfail=10`，预期 352+ passed
14. Demo test 十轮全部通过
15. **旧 state_json 兼容：** 加载不含新字段的 JSON → `model_validate` 不报错，新字段取默认值
