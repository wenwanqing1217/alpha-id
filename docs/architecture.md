# Alpha-ID 内部架构

> 更新日期：2026-07-27
> 版本：v0.3.3
> 本文档深入分析 Alpha-ID 内部模块设计与数据流

---

## 一、工程结构

```
src/
├── main.py                  ← FastAPI 入口 + lifespan + 中间件栈
├── api/                     ← HTTP 路由层（7 个路由模块）
├── core/                    ← 核心业务逻辑（15+ 模块）
├── auth/                    ← 认证与安全（JWT/CSRF/中间件）
├── entrypoints/             ← 入口点（CLI/MCP/daemon）
├── alpha_id/                ← 子包（DID/skill/poe/collector）
├── tools/                   ← 工具集
└── mindflow/                ← 工作流引擎
```

---

## 二、依赖注入容器

### 2.1 设计

`Container`（`core/container.py`）是应用级依赖容器，解决模块间耦合问题：

- **单例模式**：线程安全的双重检查锁，全局唯一实例
- **惰性初始化**：各 manager 首次访问时才创建
- **存储后端切换**：通过 `storage` setter 注入 mock 或切换实现
- **FastAPI DI 兼容**：`get_container` 从 `app.state` 获取，回退到单例

### 2.2 存储后端自动选择

```
DATABASE_URL 环境变量存在且以 postgresql 开头？
  ├── 是 → PostgresStorage（需 psycopg）
  │         └── psycopg 未安装 → 回退 SQLite
  └── 否 → SqliteStorage（默认）
```

也可通过 `STORAGE_BACKEND` 环境变量显式指定 `sqlite` 或 `postgres`。

### 2.3 管理器生命周期

```python
container = Container.instance()

container.identity    # → UserIdentityManager（惰性创建）
container.social       # → AlphaSocialManager（注入 user_exists 回调）
container.risk         # → RiskAssessmentEngine（无状态）
container.memory       # → MemoryStore（用第一个用户初始化）
container.storage      # → StorageBackend（自动选择后端）
```

切换存储后端时，已创建的管理器会被重置，下次访问时用新存储重建。

---

## 三、存储抽象层

### 3.1 StorageBackend ABC

```python
class StorageBackend(ABC):
    load(key) → dict           # 加载整个数据集
    save(key, data)            # 保存整个数据集
    get(collection, id) → dict # 获取单条记录
    put(collection, id, rec)   # 写入单条记录
    delete(collection, id)     # 删除单条记录
    list(collection, filters)  # 列出记录（支持过滤）
    count(collection, filters) # 统计记录数
```

### 3.2 两种实现

| 实现 | 文件 | 适用场景 |
|:-----|:-----|:--------|
| `SqliteStorage` | `core/storage_sqlite.py` | 本地开发、单用户 |
| `PostgresStorage` | `core/storage_postgres.py` | 生产部署、多用户 |

### 3.3 双链记忆的存储策略

`DualChainManager` 使用两个独立的存储 key：

- `private_{alpha_id}` → 加密记忆（AES-256-GCM）
- `knowledge_{alpha_id}` → 明文记忆（可搜索）

两条链可以共用同一个 SQLite 文件，通过 key 前缀隔离。

---

## 四、双链记忆隔离

### 4.1 设计原理

```
敏感度 >= 70 → 私有链（Private Chain）→ 加密存储，本地永不上传
敏感度 < 70  → 知识链（Knowledge Chain）→ 明文存储，可搜索可共享
```

### 4.2 加密方案

| 环节 | 实现 |
|:-----|:-----|
| 密钥派生 | PBKDF2-HMAC-SHA256，100,000 次迭代 |
| 加密算法 | AES-256-GCM（`cryptography` 库） |
| 密钥来源 | 从用户 DID + 随机 salt 派生 |
| Salt 存储 | `assets/.salt_{alpha_id}`（每用户独立） |

### 4.3 核心操作

```python
mgr = DualChainManager(alpha_id="Alpha-001", storage=storage)

# 写入（自动分链）
mgr.save("我的密码是xxx", sensitivity=90)   # → 私有链（加密）
mgr.save("今天天气不错", sensitivity=10)    # → 知识链（明文）

# 查询（支持关键词搜索 + 敏感度过滤）
mgr.query(chain="all", keyword="密码", max_sensitivity=100)

# 链间迁移
mgr.migrate(memory_id="xxx", target_chain="private")  # 降级（加密）
mgr.migrate(memory_id="xxx", target_chain="knowledge") # 升级（解密）

# 统计
stats = mgr.stats()  # ChainStats(private_count, knowledge_count, ...)
```

### 4.4 安全清洗

`alpha_id` 在用于文件路径前经过 `_sanitize_alpha_id()` 处理：
- 只允许字母、数字、连字符、下划线
- 移除路径遍历序列（`..`）
- 限制长度 128 字符

---

## 五、孪生大脑（TwinBrain）

### 5.1 状态机

```
SLEEP ←→ IDLE ←→ AWAKE
  ↑       ↑       ↑
  └───────┴───────┘
      ERROR（异常状态）
```

| 状态 | 说明 | 可处理消息 |
|:-----|:-----|:----------|
| `SLEEP` | 休眠/离线 | 仅自动回复（如果开启） |
| `IDLE` | 空闲待机 | 是（低功耗） |
| `AWAKE` | 活跃处理中 | 是 |
| `ERROR` | 异常安全模式 | 否 |

状态转换受 `BRAIN_TRANSITIONS` 规则约束，非法转换会被拒绝并记录错误。

### 5.2 子模块惰性加载

```python
brain = TwinBrain(alpha_id="Alpha-001", storage=storage)

brain.identity    # 首次访问时创建 UserIdentityManager
brain.social       # 首次访问时创建 AlphaSocialManager
brain.risk         # 首次访问时创建 RiskAssessmentEngine
brain.memory       # 首次访问时创建 MemoryStore
brain.actions      # 首次访问时创建 ActionEngine
brain.agent        # 首次访问时创建 AgentLoop
brain.react        # 首次访问时创建 ReActEngine
brain.reputation   # 首次访问时创建 ReputationEngine
```

### 5.3 消息路由

`receive()` 方法按消息类型分发：

| 消息类型 | 处理模块 |
|:---------|:--------|
| `CHAT` | AgentLoop 智能回复 |
| `FRIEND_REQUEST` | 社交模块 |
| `FRIEND_RESPONSE` | 社交模块 |
| `PROFILE_QUERY` | 身份模块（按可见度过滤） |
| `PING` | 心跳回复 |
| `ACTION_CONFIRM` | 行动引擎 |
| `ACTION_QUERY` | 行动引擎 |
| `APP_ACTION` | 外部应用（桌面宠等） |

### 5.4 自主学习周期

`think()` 方法执行：
1. 检查待办好友请求
2. 执行待办行动（idle/awake 状态下）
3. 计算信誉评分
4. 空闲时主动思考（AgentLoop 或 ReActEngine）
5. 自动状态转换（超时 → idle → sleep）

### 5.5 BrainRegistry 全局管理

```python
registry = BrainRegistry()
registry.register(brain)
registry.get_or_create("Alpha-001")  # 获取或创建
registry.broadcast(message)           # 向所有活跃大脑广播
registry.list_active()                # 列出活跃大脑
registry.count()                      # 统计各状态数量
```

---

## 六、Agent 循环（AgentLoop）

### 6.1 设计

纯 Python 实现的 LLM + Tools + Loop，不依赖任何框架：

```
用户输入 → 构建 messages（系统提示 + 档案 + 记忆 + 工具）
         → LLM 调用 → 解析 __TOOL_CALL__ 标记
         → 执行工具 → 结果注入 messages → 再次调用 LLM
         → 无工具调用 → 返回最终回答
```

### 6.2 内置工具（14 个）

| 工具 | 说明 |
|:-----|:-----|
| `get_profile` | 获取身份档案 |
| `get_friends` | 获取好友列表 |
| `get_risk_score` | 获取风控评分 |
| `get_messages` | 获取消息列表 |
| `send_message` | 发送消息 |
| `send_friend_request` | 发送好友请求 |
| `save_memory` | 保存长期记忆 |
| `query_memory` | 查询长期记忆 |
| `plan_action` | 计划行动 |
| `execute_action` | 执行行动 |
| `list_pending_actions` | 列出待办行动 |
| `get_action_history` | 查询行动历史 |
| `list_skills` | 列出技能 |
| `execute_skill` | 执行技能 |
| `get_skill_info` | 查询技能信息 |

### 6.3 安全机制

- **SSRF 防护**：`_validate_llm_base_url()` 校验 LLM 端点，禁止内网地址
- **连接复用**：全局 `httpx.Client` 连接池（5 keepalive，30s expiry）
- **可观测**：`record_llm_call()` 记录每次 LLM 调用的耗时和 token 用量

### 6.4 异步版本

`arun()` 使用 `AsyncLLMClient`（连接池复用 + 流式支持 + Prometheus 指标），工具执行仍为同步。

---

## 七、A2A 协议（Agent-to-Agent）

### 7.1 服务器启动

在 FastAPI lifespan 中启动（后台线程，端口 9001）：

```python
if settings.a2a_enabled:
    skills = SkillRegistry()
    signer = A2ASigner(public_key_hex=...)
    a2a_server = A2AServer(skills=skills, signer=signer, port=9001)
    a2a_server.start(blocking=False)
```

### 7.2 技能注册

```python
@skills.skill("ping", description="健康检查")
def _ping(params):
    return {"status": "ok", "agent": settings.app_name}
```

### 7.3 签名验证

技能包使用 Ed25519 签名，确保来源可信。执行证明（PoE）记录每次技能执行。

---

## 八、中间件栈

执行顺序（从外到内）：

```
请求 → CorrelationID → CSRF → RateLimit → CORS → 路由处理
```

| 中间件 | 文件 | 说明 |
|:-------|:-----|:-----|
| `CorrelationIDMiddleware` | `core/middleware.py` | 请求 ID 注入 + 访问日志 |
| `CSRFMiddleware` | `auth/csrf.py` | 仅对 POST/PUT/DELETE/PATCH 生效，安全方法放行 |
| `RateLimitMiddleware` | `core/rate_limit.py` | 滑动窗口限流（默认 60 req/min） |
| `CORSMiddleware` | FastAPI 内置 | 跨域白名单 |

### CSRF 豁免路径

- 注册流程（公开接口，无 session 可伪造）
- 身份认证接口（Bearer Token 已防伪造）

---

## 九、JWT 认证

### 9.1 令牌对机制

| 令牌类型 | 有效期 | 用途 |
|:---------|:-------|:-----|
| Access Token | 30 分钟 | API 请求认证 |
| Refresh Token | 7 天 | 轮换新的令牌对 |

### 9.2 跨服务验证

`POST /api/v1/identity/auth/verify` 是公开端点，供其他服务验证 AID 签发的 JWT。

### 9.3 主密钥校验

服务启动时 `validate_master_key()` 校验 `AUTH_MASTER_KEY` 是否配置，未配置则拒绝启动。

---

## 十、风控引擎

### 10.1 三维评分

| 维度 | 输入 | 权重 |
|:-----|:-----|:-----|
| 设备指纹 | hardware_id, ip, location, browser, screen | 30% |
| 行为指纹 | typing_speed, mouse_movement, session_time, input_pattern | 40% |
| 声纹验证 | voice_match, habit_match, noise_level, audio_quality | 30% |

### 10.2 风险等级

```
0-20:   low      → 正常放行
21-50:  medium   → 加强监控
51-80:  high     → 要求二次验证
81-100: critical → 拒绝访问
```

---

## 十一、GDPR 合规

### 11.1 数据导出

`GET /api/v1/gdpr/export` 返回用户全部个人数据：
- 基础档案
- 双链记忆（private + knowledge）
- 社交数据（好友 + 请求）

### 11.2 被遗忘权

`DELETE /api/v1/gdpr/delete` 删除全部个人数据：
- 需要确认码（必须等于 alpha_id）
- 删除双链记忆、社交数据、用户档案
- 返回删除统计

---

## 十二、可观测性

### 12.1 健康检查

| 端点 | 说明 |
|:-----|:-----|
| `GET /health` | 详细健康检查（存储 + 身份 + 记忆） |
| `GET /ready` | 就绪探针（依赖是否就绪） |
| `GET /metrics` | Prometheus 指标抓取 |

### 12.2 Prometheus 指标

- LLM 调用次数 / 耗时 / token 用量
- 请求计数 / 延迟
- 错误计数

---

## 十三、配置参考

所有配置通过 `core/settings.py`（pydantic-settings）管理，支持环境变量或 `.env` 文件。

| 变量 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `AUTH_MASTER_KEY` | *(必填)* | JWT 签名主密钥 |
| `LLM_API_KEY` | *(可选)* | LLM API 密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM 端点 |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `DATABASE_URL` | *(可选)* | PostgreSQL 连接 |
| `STORAGE_BACKEND` | *(自动)* | `sqlite` 或 `postgres` |
| `A2A_ENABLED` | `true` | A2A 服务器开关 |
| `A2A_PORT` | `9001` | A2A 端口 |
| `RATE_LIMIT_ENABLED` | `true` | 限流开关 |
| `RATE_LIMIT_RPM` | `60` | 每分钟请求数 |
| `JWT_ACCESS_EXPIRE_MINUTES` | `30` | Access Token 有效期 |
| `JWT_REFRESH_EXPIRE_DAYS` | `7` | Refresh Token 有效期 |
| `CORS_ORIGINS` | `http://localhost:3000,...` | 跨域白名单 |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama 端点（桌面宠用） |
| `FAIRY_MODEL` | `minicpm-o:4.5-4bit` | 桌面宠模型 |
| `SMS_DEMO_MODE` | `true` | SMS 演示模式 |
| `ALIPAY_DEMO_MODE` | `false` | 支付宝演示模式 |

---

## 十四、数据流示意

```
外部请求
  │
  ▼
┌─────────────────────────────────────────────┐
│  CorrelationID → CSRF → RateLimit → CORS   │
└─────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────┐
│  API 路由层（api/*.py）                      │
│  identity / registration / social /         │
│  dual_chain / agent / risk / gdpr           │
└─────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────┐
│  Depends(get_container) → Container         │
│  ├── identity → UserIdentityManager         │
│  ├── social   → AlphaSocialManager          │
│  ├── risk     → RiskAssessmentEngine        │
│  ├── memory   → MemoryStore                 │
│  └── storage  → SqliteStorage / Postgres    │
└─────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────┐
│  持久化层                                    │
│  SQLite (alpha_id.db) / PostgreSQL          │
└─────────────────────────────────────────────┘
```

---

## 十五、相关文档

- [API 端点参考](api-reference.md) — 全部 HTTP 端点详情
- [专家审计报告](EXPERT_AUDIT_2026-07-27.md) — 外部专家代码审计
- [Ghost 全局架构](../../docs/architecture/ARCHITECTURE.md) — 主仓库架构文档
- [Ghost 生态系统](../../docs/architecture/ECOSYSTEM.md) — 全组件串联
