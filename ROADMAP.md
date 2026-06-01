# AID — Agent Identity Layer

> **从「技能管理器」到「Agent 身份层」**
> 技能会泛滥，模型会过时。唯一恒定的是「你是谁」和「这是谁写的」。

## 当前评分：2.7 / 5.0（2025-07）

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
| **Skill 生态** | — | **全新维度：尚不存在，决定方向** |

## 最终目标：4.5

一个 **身份优先、协议驱动** 的 Agent 生态 —— 任何 Agent 框架、任何模型都能接入的「身份层」。
**技能签名可验证、作者信誉可追溯、执行证明可审计。**

## 三阶段路线

```
2.7 ── Phase 1 ── 3.5 ── Phase 2 ── 4.0 ── Phase 3 ── 4.5
      (8 weeks)         (3 months)          (6 months)
```

| 阶段 | 目标分 | 主题 | 一句话定位 |
|------|--------|------|-----------|
| Phase 1「身份地基」 | 2.7 → 3.5 | Agent DID Registry + Skill SDK | 先让 Agent 有「身份」，让 Skill 有「签名」 |
| Phase 2「信誉网络」 | 3.5 → 4.0 | 技能归因 + 跨框架信誉传播 | 让好作者被看见，让恶意代码被追踪 |
| Phase 3「身份自治」 | 4.0 → 4.5 | 执行证明(PoE) + 去平台化协议 | Agent 自治，不再依赖任何中心平台 |

---

## Phase 1「身份地基」：2.7 → 3.5（全量可写）

> **核心转变：** 原来 Phase 1 是「地基加固」(ReAct Agent + 安全加固)，现在是「身份地基」—— DID 优先级提到最前面，所有东西都围绕身份层来建。ReAct Agent 不变，但它是基础设施的一部分，不是目的。

### P1-0 Agent DID Registry（新增最高优先）

**目标：** 让每个 Agent 有一个可验证的身份，让每个 Skill 有作者签名。

```json
// .aid/identity.json — 最小 DID 文件
{
  "did": "did:aid:abc123...",
  "publicKey": "-----BEGIN PUBLIC KEY-----...",
  "skills_signed": ["tts", "search", "code_review"],
  "created": "2025-07-15"
}
```

**交付物：**
- [ ] CLI `aid identity init` — 生成 DID + 密钥对
- [ ] CLI `aid identity show` — 查看当前身份
- [ ] CLI `aid identity verify <file>` — 验证技能签名
- [ ] Python SDK `AIDSigner` — 签名/验签接口
- [ ] `.aid/` 目录规范（identity.json + skills/ + keys/）

**为什么先做这个：**
- 身份是 trust 的基础，没有身份就没有信誉
- 所有后续功能（Skill SDK、信誉图谱、归因）都依赖它
- 足够小、两周内可交付，立刻见效

**依赖：** cryptography（已有），无外部服务

---

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

**目标：** `aid` 命令行工具

**文件清单：**
- 新建 `src/alpha_id/cli.py` → Typer CLI
- 新建 `src/alpha_id/identity_cli.py` → DID 身份子命令

**命令设计：**
```bash
# 身份层（P1-0 最高优先）
aid identity init                     # 生成 DID + 密钥对
aid identity show                     # 查看当前身份
aid identity verify <file>            # 验证技能签名

# 原有功能（P1-1 ~ P1-4）
aid agent create                      # 创建新 Agent
aid agent think <id>                  # 触发思考
aid agent connect <id1> <id2>         # 建立好友关系
aid agent send <from> <to> "message"  # 发送消息
aid agent list                        # 列出所有 Agent
aid agent risk <id>                   # 风险评估
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

## Phase 2「信誉网络」：3.5 → 4.0（大纲，待细化）

> **核心转变：** 原来 Phase 2「智能升级」(DID + 社交 + 工具市场)，现在是「信誉网络」—— 所有 DID 和社交能力围绕「技能信誉」来组织。

### P2-1 技能签名与验证（身份 3.5 → 4.0）
- Skill 包的 DID 签发（作者私钥签名 skill 内容 hash）
- 用户侧 `aid identity verify <skill>` 验签
- 撤销列表（作者可吊销已发布的 skill 版本）
- 参考：MiMo-Skills 的 npm 包格式 + 附加签名字段

### P2-2 使用归因与信誉图谱（社交 2.5 → 4.0）
- 记录「谁执行了谁的 skill」的归因链（有向图）
- 作者信誉分 = f(下载量, 好评率, 持续维护, 签名历史)
- 信誉分跨 Agent 框架传播（OpenClaw 的信用 → Claude Code 可见）
- 恶意 skill 被举报 → 作者信誉扣分 → 社区自动过滤

### P2-3 跨框架运行时抽象（Agent 3.5 → 4.5）✅
- Skill SDK 接口抽象层（`execute(ctx, input) -> output`）✅
- 适配器：OpenClaw → AID, Claude Code → AID, Cursor → AID
- 每个适配器负责将对应框架的 tool call 标准化为 AID Skill 接口
- **不造新框架，只造桥**

---

## Phase 3「身份自治」：4.0 → 4.5（大纲，待细化）

### P3-1 执行证明（Proof of Execution）
- Agent 每次执行 skill 生成可验证的 PoE 记录
- PoE = (skill_hash, caller_did, author_did, timestamp, output_hash) 签名链
- 链下存储，可选发布到公共日志做公证

### P3-2 去平台化协议
- 不再依赖任何中心市场/平台发现 skill
- Git-based 发现 + DID 解析器作为 fallback
- 作者可自托管 skill 仓库，用户通过 DID 解析找到

### P3-3 多 Agent 协作自治
- Agent 间通过 DID 互相认证身份
- 技能调用链可追溯（A → B's skill → C's skill）
- 多方执行证明自动聚合

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

---

## 📚 前沿调研 & 关键洞察（2025年6月）

### 资料来源

| 来源 | 核心领域 | 价值 |
|------|---------|------|
| Anthropic: Building Effective Agents | Agent 架构最佳实践 | ⭐⭐⭐⭐⭐ |
| LangGraph 文档 | Agent 编排框架 | ⭐⭐⭐⭐ |
| AT Protocol (Bluesky) | 去中心化社交身份 | ⭐⭐⭐⭐⭐ |
| W3C DID Core 1.0 | 去中心化身份标准 | ⭐⭐⭐⭐⭐ |
| CrewAI | 多 Agent 协作 | ⭐⭐⭐ |
| Veramo | DID/VC 框架 | ⭐⭐⭐⭐ |
| Farcaster | 去中心化社交 | ⭐⭐⭐⭐ |

### 🔑 关键洞察 & 对我们的路线图的修正

#### 洞察 1：Agent 要简单，不要框架

**来源：** Anthropic, LangGraph

**原文：**
> "The most successful implementations use simple, composable patterns rather than complex frameworks."

**对路线图的修正：**

原计划写一个复杂的 ReActEngine → **改**：直接用 `LLM + tools + loop` 模式，< 200 行代码。

```python
# 这不是伪代码，这是最终实现的架构
class Agent:
    def __init__(self, llm, tools, memory):
        self.llm = llm       # 直接调用 OpenAI/API
        self.tools = tools   # Dict[str, Tool]
        self.memory = memory # 向量记忆

    def run(self, task):
        while steps < max_steps:
            context = self.memory.search(task)   # 召回
            thought = self.llm.call(task, context, self.tools.describe())
            if thought.action == "final_answer":
                return thought.answer
            result = self.tools[thought.action].run(thought.args)
            self.memory.save(result)
            steps += 1
```

**去掉了什么：**
- ❌ 不依赖 LangChain
- ❌ 不依赖任何 Agent 框架
- ❌ 不引入复杂的状态图（已有 TwinBrain 状态机就够了）

**保留了：**
- ✅ 直接 LLM API 调用
- ✅ 清晰可调的 prompt
- ✅ 每一步都可 trace

---

#### 洞察 2：Agent 的核心是 Tool Design，不是 Prompt

**来源：** Anthropic

> "Agents are typically just LLMs using tools based on environmental feedback in a loop. It is therefore crucial to design toolsets and their documentation clearly."

**对路线图的修正：**

原计划把重心放在 `think()` 逻辑上 → **改**：重心放在 Tool API 设计上。

**新原则：**
- 每个 Tool 必须有：name, description, parameters (JSON Schema), returns
- Tool 的 description 要写得像 API 文档（LLM 靠它理解工具）
- Tool 的返回值要结构化，不要返回原始字符串

**Alpha-ID Agent 的 Tool 清单（重构后）：**

| Tool | Description | 使 Agent 能做什么 |
|------|-------------|------------------|
| `search_memory(query)` | 搜索相关记忆 | 记住过去的事情 |
| `save_memory(content, tags)` | 保存新记忆 | 学习新知识 |
| `query_identity(alpha_id)` | 查询身份档案 | 认识其他人 |
| `send_message(to, content)` | 发送消息 | 社交互动 |
| `evaluate_risk(action_desc)` | 评估风险 | 自我保护 |
| `get_time()` | 获取当前时间 | 时间感知 |
| `execute_action(action_id)` | 执行审批中的行动 | 自主行动 |

---

#### 洞察 3：DID 实现可以很轻——不需要完整 W3C 栈

**来源：** AT Protocol, W3C DID Core

**核心理解：**
- DID 的核心就是一个 `DID Document`（JSON），包含公钥 + 服务地址
- `did:alpha:` 方法的复杂度取决于我们定义多少功能
- AT Protocol 的 PLC DID 只有 2 种 key：signing key + rotation key

**对路线图的修正：**

原计划 Phase 2 完整实现 DID Core → **改**：Phase 1 就做最小 DID 实现。

```python
# 最小的 DID Document
{
    "@context": "https://www.w3.org/ns/did/v1",
    "id": "did:alpha:Alpha-042",
    "verificationMethod": [{
        "id": "did:alpha:Alpha-042#signing-key",
        "type": "JsonWebKey2020",
        "publicKeyJwk": { ... }  # Ed25519
    }],
    "authentication": ["did:alpha:Alpha-042#signing-key"],
    "service": [{
        "id": "did:alpha:Alpha-042#pds",
        "type": "AlphaPersonalDataServer",
        "serviceEndpoint": "https://pds.alpha-id.io/Alpha-042"
    }]
}
```

**这是在 Phase 1 做的原因：**
- DID 本身就是个 JSON 文档——写起来 50 行代码
- 生成 Ed25519 密钥对用 `cryptography`（已有依赖）
- 有 DID Document 之后，身份就从「一个数据库条目」变成了「一个可验证的加密身份」
- 这是通向去中心化的第一步，但对 Agent 立即可用

---

#### 洞察 4：联邦社交可以借鉴 AT Protocol 的三层架构

**来源：** AT Protocol

**AT Protocol 架构：**
```
PDS (Personal Data Server)   → 你的数据你的服务器
       ↓
Relay                        → 汇总全局数据流
       ↓
App View                     → 检索和展示层
```

**对路线图的修正：**

原计划 Phase 2 做联邦社交 → **改**：Phase 1 做「可移植身份」的第一步——让 Alpha-ID 可以导出/导入。

具体来说 Phase 1 加一个 `export_identity(alpha_id)` 方法：
```python
# 导出 = DID Document + 签名后的社交数据
identity_bundle = agent.export()
# 导入 = 验证签名 + 恢复
agent2.import_(identity_bundle)
```

这不需要服务器，不需要联邦协议，但为 Phase 2 的联邦社交奠定了基础。

---

#### 洞察 5：Memory 分两层——工作记忆 + 长期记忆

**来源：** LangGraph, Anthropic

**LangGraph 的区分：**
- Short-term working memory: 当前对话上下文（消息列表）
- Long-term memory: 跨会话的知识（向量数据库）

**对路线图的修正：**

原计划只做向量记忆 → **改**：两种记忆分开，TwinBrain 已有 `receive()` 消息列表做工作记忆，向量记忆做长期记忆。

```python
class TwinBrainMemory:
    """统一记忆接口"""
    
    def working_memory(self) -> List[Message]:
        """当前会话消息列表（短期）"""
        return self._recent_messages[-20:]
    
    def long_term_memory(self, query: str) -> List[Dict]:
        """向量语义搜索（长期）"""
        return self._vector_store.search(query)
    
    def save_to_long_term(self, content: str, importance: float):
        """只有重要内容存长期"""
        if importance > 0.3:
            self._vector_store.add(content)
```

这简化了 Phase 1 的实现——向量记忆只存「重要的事」，不存所有历史。

---

#### 洞察 6：现有代码的几个「可立即优化」点

来自代码审查 + 前沿对比：

| 问题 | 建议 | 优先级 |
|------|------|--------|
| `TwinBrain._handle_chat` 调用 `social.send_message` 但硬编码 sender | 改为从 message.sender 读取 | P0 |
| `think()` 是空方法 | Phase 1 核心修复 | P0 |
| `RiskAssessmentEngine` 有 `numpy` 运行时 import | 移到文件头 | P0 |
| `get_statistics()` 返回字典没有 JSON Schema | 加 Pydantic model | P1 |
| `register_user()` 直接传 founder_code 明文 | 改传哈希比对 | P1 |
| 没有版本号暴露给 SDK 用户 | `alpha_id.__version__` | P1 |

---

#### 洞察 7：Xiaomi MiMo — Agent Skills 生态已到来，我们应「借势不硬刚」

**调查时间：** 2025-07 | **来源：** [github.com/XiaomiMiMo](https://github.com/XiaomiMiMo)

**MiMo 是什么：**
小米的 AI Agent 生态体系。核心仓库：

| 仓库 | ⭐ | 对应关系 |
|------|---|---------|
| MiMo-Skills | 62 | **Agent skills 分发** — `npx skills add XiaomiMiMo/MiMo-Skills` |
| MiMo-V2-Flash | 1320 | 推理+Agentic 基础模型 |
| MiMo | 2134 | 推理管线（预训练到后训练） |
| MiMo-VL | 641 | 视觉语言多模态 |
| MiMo-Embodied | 385 | 具身智能 |

**对我们最关键的发现 — MiMo-Skills：**

```
npx skills add XiaomiMiMo/MiMo-Skills
```

- 跨 Agent 框架兼容（Claude Code / Cursor / OpenClaw 都可以装）
- Skill = 一个可安装的 npm 包，包含工具定义 + 实现 + 文档
- MIT 开源
- 平台入口：platform.xiaomimimo.com（API Key 模式鉴权）

**对我们的影响：**

| MiMo 方向 | 我们的应对 |
|-----------|-----------|
| 分发层：npx 安装 | 兼容其格式，技能包加 DID 签名字段，而非另造轮子 |
| API Key 鉴权 | 借鉴其简洁设计，我们加一层 DID 可选验证 |
| 跨 Agent 兼容 | 我们 Skill SDK 预留适配器接口，直接对标 |
| 平台中心化（platform.xiaomimimo.com） | **差异点：** 我们不做平台，做身份层——去中心化 + DID 验证 |
| 纯分发，无信誉系统 | **差异点：** 我们做信誉图谱 + 归因链，MiMo 不做 |

**一句话结论：**
> MiMo 在造最好的模型+技能平台。我们在造「谁写的、谁用的、谁可信」的**身份层**。两者正交——我们的 Skill 可以跑在 MiMo 上，MiMo 的 Skill 可以用我们的 DID 签名增强可信度。

---

### 路线图优化总结

| 原计划 | 优化后 | 原因 |
|--------|--------|------|
| 复杂 ReAct 引擎 | 简单 LLM + tools + loop | Anthropic: 简单 = 有效 |
| Phase 2 才做 DID | Phase 1 做最小 DID | 50 行代码，立即可用 |
| Agent 重心在 think 逻辑 | Agent 重心在 Tool API 设计 | Anthropic: 工具接口决定 Agent 质量 |
| 只做向量记忆 | 工作记忆 + 长期记忆分层 | LangGraph 模式 |
| 联邦社交 Phase 2 | Phase 1 加导出/导入可移植性 | AT Protocol 启发 |
| 完整 W3C DID | 最小 DID: `did:aid` | 标准里只取 20% 就得 80% 效果 |
| 做 Agent 技能管理器 | 做 Agent 身份层 + 签名层 | MiMo-Skills 已解决分发，我们解决信任 |
