# SoulDance 18 阶段方案缺口补齐设计

**日期**：2026-06-20  
**背景**：SoulDance 项目已完成 Stage 0/01，后端 Agent 核心（意图识别、检索排序、推荐生成、购物车、订单状态机、语音、反馈闭环）已可用，但基础设施与部分链路仍存在缺口。本设计基于当前项目结构，按用户提供的 18 阶段方案顺序补齐缺失部分，**排除 Docker 部署、图片上传 / 视觉理解**。

---

## 一、当前状态与 18 阶段映射

| 阶段 | 主题 | 当前状态 | 处理方式 |
|------|------|----------|----------|
| 01 | 目录 / 配置 / 健康检查 | 目录已就绪；`requirements.txt` 未锁定 | 补齐依赖锁定 |
| 02 | 商品 / SKU / 库存 / 价格 / 购物车 / 订单数据库模型 | `models.py` 有 Pydantic 模型，但无 ORM/数据库 | 迁移到 SQLAlchemy + PostgreSQL |
| 03 | Alembic 迁移 + 测试数据 | 无 Alembic，数据来自 JSON fixture | 补齐 migration 与 seed |
| 04 | 确定性商品查询 + 购物车 CRUD | 已实现 | 跳过，仅增强测试 |
| 05 | 订单预览 / 地址选择 / 确认状态机 | 后端已实现；Android 缺少地址选择与 confirmation_token 流程 | 补齐客户端交易闭环 |
| 06 | 文档清洗 / Chunking / 向量入库 | 有整商品 chunk + 证据抽取；缺少属性/场景/评价维度 chunk 与元数据 | 增强 chunking |
| 07 | SQL 过滤 + 关键词 + 向量 + RRF | 目前是内存过滤 + BM25/向量加权融合 | 补齐 SQL/全文/RRF/reranker |
| 08 | 意图识别与约束提取 | 已实现 | 跳过/调优 |
| 09 | Agent 工具注册 + 状态机 | 已实现 | 跳过/增强 schema |
| 10 | WebSocket 事件协议 + 断线恢复 | 已实现 | 跳过/补齐 ack 与 seq |
| 11 | Android RealtimeEvent → ViewModel → StateFlow | 已实现 | 跳过 |
| 12 | 商品卡片 / 对比 / 购物车同步 | 已实现 | 跳过/增强 |
| 13 | 用户事件 / 画像 / 热榜 | 事件与画像已实现；热榜未实现 | 跳过/补热榜 |
| 14 | 精灵动画 / 等级 / 装扮 | 已实现 | 跳过 |
| 15 | 图片 / 语音输入 + TTS | 语音已实现；**图片上传 / 视觉理解排除** | 跳过 |
| 16 | 缓存 / 超时 / 降级 / 观测 / 压测 | 缓存与熔断已实现；缺少统一超时/降级策略与指标 | 补齐 |
| 17 | RAG + Agent 固定评测集 | 有后端单测，无固定场景评测集与端到端测试 | 补齐 |
| 18 | A/B 实验 / 转化率 | 超出当前范围 | 延后 |

---

## 二、实施路线

### 里程碑 A：数据与依赖基线（P01-P03）

目标：把当前 JSON 文件持久化升级为 PostgreSQL + pgvector，建立可复现的依赖基线，同时不破坏现有 API 和客户端。

#### A1. 依赖锁定
- 新增 `server/requirements.in`，包含当前已用依赖及新增依赖；
- 使用 `pip-compile` 生成 `server/requirements.lock`（含哈希）；
- 新增 `server/requirements-dev.txt` 用于测试与生成 lock 文件。

新增依赖示例：
```text
sqlalchemy[asyncio]==2.0.51
psycopg[binary,pool]==3.3.4
pgvector==0.4.2
alembic==1.18.4
redis[hiredis]==7.2.2
orjson==3.11.9
```

#### A2. 数据库模型与迁移
- 在 `server/backend/app/db/` 下创建 SQLAlchemy ORM 模型，映射已有 Pydantic 模型：
  - `products`、`product_skus`、`product_attributes`、`product_documents`、`product_chunks`
  - `prices`、`inventory`
  - `carts`、`cart_items`
  - `addresses`、`orders`、`order_items`
  - `user_events`、`user_profiles`
  - `conversations`、`messages`
  - `agent_runs`、`tool_calls`
- 使用 Alembic 管理迁移，`migrations/` 目录放在 `server/migrations/`；
- 每个实体增加 `version`、`updated_at`、`is_active`、`source`、`content_hash`。

#### A3. 持久化服务迁移
- 保持 `CartService`、`OrderService`、`SessionStore`、`FeedbackStore`、`UserProfileStore` 的接口不变；
- 内部实现从 JSON 文件切换到数据库读写；
- 保留 JSON fixture 作为初始化 seed，新增 `scripts/seed_db.py`。

#### A4. pgvector 向量表
- `product_chunks` 表包含 `embedding vector(384)`（或按实际模型维度）；
- 初始版本把当前 `product.chunk` 整体入库；后续里程碑 C 再切分为细粒度 chunk。

### 里程碑 B：交易闭环 + RAG 检索增强（P05-P07）

#### B1. Android 订单确认流程
- 在 `CheckoutBottomSheet` 中增加地址选择步骤：
  1. 点击“结算” → 调用 `/api/order/initiate`；
  2. 展示地址列表 → 调用 `/api/order/select_address` 获取 `confirmation_token`；
  3. 展示订单预览 → 调用 `/api/order/confirm` 完成下单；
  4. 成功后跳转到 `OrdersScreen`。
- `CartViewModel` 增加 `OrderFlowState` 状态机。

#### B2. 商品 Chunking 增强
- 扩展 `knowledge_base.py` 或新增 `rag/chunking.py`：
  - 规格 → 按属性组切分；
  - 功能 → 每项功能一个 chunk；
  - 场景 → 按使用场景切分；
  - 广告文案 → 单独 chunk，标记 `trust_level=marketing`；
  - 评价 → 按维度聚合；
  - FAQ → 每组 Q&A 一个 chunk。
- 每个 chunk 元数据：
  ```json
  {
    "product_id": "P001",
    "sku_id": "SKU001",
    "category_id": "headphones",
    "chunk_type": "specification",
    "source_type": "official_detail",
    "trust_level": "official",
    "document_version": 3
  }
  ```

#### B3. 混合检索链路
- 新增/改造 `rag/` 模块：
  - `lexical_search.py`：PostgreSQL full-text + BM25；
  - `vector_search.py`：pgvector 相似度搜索；
  - `fusion.py`：RRF 融合；
  - `reranker.py`：轻量交叉编码器或 LLM 重排；
  - `constraint_filter.py`：SQL 硬过滤（价格、库存、类目、品牌）。
- 检索流程：
  ```text
  用户输入 → 约束提取 → SQL 候选过滤 → 关键词 Top 30 → 向量 Top 30 → RRF 融合 → 业务过滤 → 重排 Top 8 → 实时补充价格/库存 → 生成解释
  ```

### 里程碑 C：稳定性 + 评测集（P16、P17）

#### C1. 超时与降级策略
- 为不同操作设置分级超时：
  - 意图识别：短超时；
  - 关键词/向量检索：短超时；
  - 重排：可降级；
  - LLM：流式超时；
  - 业务写操作：严格事务超时。
- 降级链：
  - 重排失败 → 使用 RRF 排名；
  - 向量失败 → 回退关键词 + 热榜；
  - LLM 失败 → 返回结构化卡片 + 固定模板；
  - Redis 失败 → 回源 PostgreSQL；
  - 库存服务失败 → 禁止下单。

#### C2. 固定场景评测集
- 在 `data/eval/` 下建立评测集，覆盖至少 20 个场景：
  - 明确型号查询、模糊需求、冷启动、再便宜点、更高端一点；
  - 不要某种成分、排除某品牌、两商品对比、三商品对比；
  - 加购后修改数量、删除购物车商品、库存不足、地址缺失；
  - 更换地址、重复确认下单、语音识别错误修正；
  - 模型超时、向量检索不可用、Redis 不可用、WebSocket 断线重连。

#### C3. 端到端测试
- 使用 `httpx` + `pytest-asyncio` 编写 API 端到端测试；
- 对关键路径（下单状态机、购物车幂等、检索硬约束）增加集成测试。

---

## 三、接口与兼容性约束

1. 保持 `/health`、`/api/products`、`/api/cart/*`、`/api/order/*`、`/api/stt`、`/ws/chat` 稳定；
2. WebSocket 事件类型 `text_delta`、`product_item`、`cart_update`、`done`、`error` 保持兼容；
3. 数据库迁移必须可回滚；
4. 新增代码必须与现有 `pydantic` 模型、`ShopGuideAgent` 调用链兼容；
5. 不改变 Android 端已有 ViewModel 接口签名，仅在其上扩展订单流程。

---

## 四、验收标准

### 里程碑 A
- [ ] `pip install -r requirements.lock` 可完整复现后端环境；
- [ ] `alembic upgrade head` 成功创建所有表；
- [ ] `scripts/seed_db.py` 能把 fixture 商品导入数据库；
- [ ] 购物车/订单/会话/反馈/画像读写从 JSON 切换到数据库后，原有测试仍通过。

### 里程碑 B
- [ ] Android 能从聊天页或购物车页完成完整下单流程（地址选择 + 确认）；
- [ ] 后端检索链路支持 SQL 过滤 + 全文 + 向量 + RRF；
- [ ] 检索结果支持价格/库存/品牌硬约束；
- [ ] 商品 chunk 携带完整元数据并入库 pgvector。

### 里程碑 C
- [ ] 所有外部调用（LLM、检索、数据库）都有超时和降级；
- [ ] 固定场景评测集可运行并输出指标；
- [ ] 新增端到端测试覆盖下单状态机和购物车幂等。

---

## 五、排除项

- **Docker / 容器化部署**：用户明确不需要，本设计不做 Docker Compose；
- **图片上传 / 视觉理解**：用户明确不需要，本设计不做多模态图片输入；
- **A/B 实验与转化率分析**：超出当前范围，延后。

---

## 六、风险与注意事项

1. **数据库迁移风险**：从 JSON 切换到 PostgreSQL 时，必须保持 `CartService` / `OrderService` 等接口不变，避免影响 Android 端；
2. **向量维度一致性**：pgvector 列维度需与实际 embedding 模型输出维度一致；
3. **检索改写风险**：升级检索链路后，需用固定评测集验证原有推荐质量不下降；
4. **性能风险**：首次引入数据库后，需验证 `/health` 与 `/ws/chat` 的 p95 延迟。
