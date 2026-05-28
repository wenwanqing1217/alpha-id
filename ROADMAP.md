# Alpha-ID → 4.5 跃迁计划

## 当前评分：2.7 / 5.0（2025-06-28）

| 维度 | 分数 | 短板 |
|------|:----:|------|
| 身份 | 3.0 | 中心化，无 DID 标准 |
| 社交 | 2.5 | 中心化好友列表，无联邦协议 |
| 风控 | 3.5 | 规则引擎，无 ML 模型 |
| Agent | 2.0 | 状态机，无 ReAct / Tool Use |
| 存储 | 2.0 | SQLite 本地，无向量搜索 |
| 安全 | 1.5 | 数据库未加密，无 ZK |
| 代码 | 4.0 | 277 测试，类型注解 |
| 创新 | 3.0 | 组合创新，无单点突破 |

## 最终目标：4.5

## 三阶段路线

```
2.7 ── Phase 1 ── 3.5 ── Phase 2 ── 4.0 ── Phase 3 ── 4.5
      (4 weeks)         (3 months)          (6 months)
```

---

## Phase 1「地基加固」：2.7 → 3.5（全量可写）

### P1-1 ReAct Agent（Agent 2.0 → 3.5）

**目标：** `TwinBrain.think()` 调用 LLM → 执行 ReAct 循环

**文件清单：**
- 新建 `src/core/agent_react.py` → ReAct 引擎
- 修改 `src/core/twin_brain.py` → `think()` 转发到 ReAct

**接口设计：**
```python
class ReActEngine:
    def __init__(self, alpha_id, brain: TwinBrain, llm_api_key: str = ""):
        ...
    def think(self, input_text: str = "") -> Dict:
        # 1. 召回相关记忆
        # 2. 构建 ReAct prompt
        # 3. 调用 LLM（支持 OpenAI / 兼容 API）
        # 4. 解析行动指令
        # 5. 执行工具 → 更新记忆
        # 6. 返回思考结果
```

**内置工具（Tool Registry）：**
- `search_memory(query)` → 向量搜索记忆
- `query_profile(alpha_id)` → 查询身份
- `send_message(to, content)` → 发送消息
- `evaluate_risk(action)` → 风险评估
- `get_time()` → 当前时间

**LLM 支持：**
- 默认 OpenAI 兼容 API（环境变量 `LLM_API_KEY` + `LLM_BASE_URL`）
- 可选本地模型（环境变量 `LLM_MODEL`）

**测试：** 新增 `tests/test_agent_react.py`（mock LLM）

---

### P1-2 向量记忆（存储 2.0 → 3.5）

**目标：** `MemoryStore.search("query")` 语义匹配

**文件清单：**
- 修改 `src/core/memory_store.py` → 加 ChromaDB 向量层

**设计：**
```python
class VectorMemoryLayer:
    def __init__(self, alpha_id, collection_name="alpha_memories"):
        # ChromaDB 持久化客户端
    def add(self, memory_id, text, metadata):
        # 生成 embedding（sentence-transformers）
    def search(self, query, k=5):
        # 向量搜索 → 返回相关记忆
    def delete(self, memory_id):
        pass
```

**依赖：** `chromadb>=0.5`, `sentence-transformers>=2.2`（写到 pyproject.toml）

**回退：** 无 GPU / 不想装模型时，自动用关键词搜索（现有逻辑）

---

### P1-3 数据库加密（安全 1.5 → 3.0）

**目标：** SQLite 文件 AES 加密

**文件清单：**
- 修改 `src/core/storage_sqlite.py` → 透明加解密层

**设计：**
- 使用 `cryptography.Fernet`（已在 pyproject.toml 中）
- 密钥从 `DB_ENCRYPTION_KEY` 环境变量读取
- 若未设置密钥，不加密（向后兼容）
- 加密粒度：整个数据库文件（sqlcipher 风格），或表级加密值

**实现方案：**
```
方案 A（推荐）：sqlite3 写前加密 → 读出再解密
- load("key") 时 decrypt(bytes)
- save("key", data) 时 encrypt(bytes)
```

---

### P1-4 ML 风控增强（风控 3.5 → 4.0）

**目标：** 规则 + ML 双引擎

**文件清单：**
- 修改 `src/core/risk_engine.py` → 加 IsolationForest 异常检测

**设计：**
```python
class MLAnomalyDetector:
    def __init__(self):
        self.model = IsolationForest(contamination=0.1)
    def fit(self, history: List[Dict]):
        # 从历史行为提取特征向量
    def predict(self, features: Dict) -> float:
        # 返回异常分数 0-100
```

**特征工程：**
- 登入时间偏差
- 打字速度变化
- 设备变化频率
- IP 地理位置跳跃距离
- 会话时长

**集成：** `RiskAssessmentEngine.calculate_total_risk()` 中混合：
```python
ml_score = self.ml_detector.predict(features) if self.ml_detector.fitted else 0
final_score = 0.7 * rule_score + 0.3 * ml_score
```

---

### P1-5 CLI 工具（产品载体）

**目标：** `alpha-id` 命令行工具

**文件清单：**
- 新建 `src/alpha_id/cli.py` → Typer CLI

**命令设计：**
```bash
alpha-id create                          # 创建新 Agent
alpha-id identify <alpha_id>             # 查询身份
alpha-id connect <id1> <id2>             # 建立好友关系
alpha-id send <from> <to> "message"      # 发送消息
alpha-id think <alpha_id>                # 触发思考
alpha-id list                            # 列出所有 Agent
alpha-id risk <alpha_id>                 # 风险评估
```

**依赖：** `typer>=0.12`（写到 pyproject.toml）

---

### P1-6 演示 Web App

**目标：** 简单但直观的 Web 界面，展示多 Agent 社交和思考

**文件清单：**
- 新建 `src/alpha_id/web.py` → FastAPI + Jinja2 页面
- 新建 `src/alpha_id/templates/` → HTML 模板

**功能：**
- Agent 列表 + 状态（在线/离线）
- 好友网络可视化（简单的力导向图或列表）
- 消息发送/接收面板
- 触发 `think()` 并显示思考过程
- 风险评分仪表盘

---

### Phase 1 依赖变更（pyproject.toml）

```toml
[project.dependencies]
# 已有
chromadb>=0.5
sentence-transformers>=2.2
scikit-learn>=1.4
typer>=0.12
```

---

## Phase 2「智能升级」：3.5 → 4.0（大纲，待细化）

### P2-1 DID + 可验证凭证（身份 3.0 → 4.5）
- W3C DID Core 标准实现
- `did:alpha:` 方法
- 签发/验证 Verifiable Credentials
- Credential Status List 撤销检查

### P2-2 联邦社交协议（社交 2.5 → 4.0）
- Agent 之间 HTTP/gRPC 直连
- Alpha-ID 全局解析器（公钥 + 地址）
- 好友关系跨实例可移植

### P2-3 Agent 工具市场（Agent 3.5 → 4.5）
- `agent install tool:<name>` 插件系统
- Chain of Thought 多步规划
- 外部 API 自动发现

---

## Phase 3「去中心化」：4.0 → 4.5（大纲，待细化）

### P3-1 P2P 身份网络
- Kademlia DHT 全局发现
- 去中心化身份解析

### P3-2 零知识证明（安全 3.0 → 4.5）
- 选择性披露
- 属性基加密

### P3-3 多 Agent 涌现
- Agent 间辩论/协作/投票
- 群组集体决策

---

## 测试策略

- Phase 1 每个模块新增 >= 20 个测试用例
- 所有 LLM 调用在外围被 mock（`unittest.mock.patch`）
- ChromaDB 用 `chromadb.ephemeral` 做集成测试
- 全量回归：`pytest tests/` ≥ 350 passing

## 技术债务跟踪

- [ ] `_sdk_smoke_test.py`（已删除）
- [ ] `assets/alpha_id.db`（需要迁移到标准路径）
- [ ] `numpy` 在 `risk_engine.py` 中是运行时导入（应移到文件头）
- [ ] `memory_store.py` 默认路径是 JSON 文件，混合存储架构需统一
- [ ] `TwinBrain` 的 `_memory` 用 `JsonStorage`，与 SQLite 不一致
