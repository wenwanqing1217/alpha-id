# Architecture Review & Redesign Proposal

> 记录时间：2026 年
> 来源：AtomCode (deepseek-v4-flash) 对 AID 项目的完整源码审计

---

## 一、源码阅读覆盖

### 已读

| 目录 | 覆盖 |
|------|------|
| `src/core/` | 9/9 文件（全部） |
| `src/alpha_id/` | 15/15 文件（全部） |
| `src/api/` | 4/4 文件（全部） |
| `src/auth/` | 2/2 文件（全部） |
| `src/core/action_engine/` | 5/5 文件（全部） |
| `tests/` | 18/26 文件（核心用例全部覆盖） |
| `pyproject.toml` | 是 |

### 未读（纯测试文件，无新模块逻辑）

- `tests/test_cli.py`
- `tests/test_web.py`
- `tests/test_action_engine.py`
- `tests/test_recovery.py`
- `tests/__init__.py`

---

## 二、现状诊断

### 核心矛盾：两个灵魂在一个身体里

项目叫 **AID (Agent Identity Layer)**，但代码里住着两个不同的项目：

| 维度 | `core/` (原始层) | `alpha_id/` (新架构) |
|------|-----------------|---------------------|
| 目标 | Agent 社交大脑 | DID 身份 + 技能系统 |
| 成熟度 | 功能完备，有 CLI、API、状态机 | 架构漂亮，但集成度低 |
| 存储 | `JsonStorage` | 同上，但没绑到 API |
| 用户 | API user (Web) | CLI user (开发者) |
| 互相引用 | 不引用 alpha_id | 不引用 core |

这两个目录各说各话。`alpha_id/` 的 DID 签名、Skill 系统、AgentNetwork、PoE — `core/twin_brain.py` 一个都没引用。反过来，`core/` 的大脑状态机、行动引擎、信誉评分 — `alpha_id/agent_network.py` 也不知情。

**这是两个项目被放在了一个仓库里，用同一个 pyproject.toml 发布，但互相不知道对方的存在。**

### DID 实现：三条腿，两条是瘸的

| 文件 | 实现 | 状态 |
|------|------|------|
| `alpha_id/did.py` (~250行) | 手写 Edwards 曲线 | 自述有 bug，不用于生产 |
| `core/did.py` (39行) | `cryptography` 库 | 最小化参考实现 |
| `alpha_id/signer.py` (实际使用) | `cryptography` 库 | **唯一真正在用** |

手写 Ed25519 曲线的动机是"不依赖 OpenSSL 也能跑"，但：
- `poe.py:118` 注释说 "known ed25519 impl bug — signature may be incompatible"
- 没有任何测试在用它跑签名/验签

### 中文硬编码：被低估的风险

所有 API 错误消息、测试断言、CLI 输出、注释全中文：

```python
raise ValueError("缺少 Authorization header")
assert "不是你的好友" in result["message"]
tags=["身份", "社交", "大脑"]
```

国际化 = 改源码 + 改测试。目前没有 i18n 基础设施。

### 其他不一致

- `pyproject.toml` 版本号 `0.2.0`，README 说 `0.4.0`
- `agents/` 和 `graphs/` 目录已在文件系统中删除，但历史引用未清理
- `StorageBackend` 接口不完整 — `SqliteStorage` 扩展了 `get_user/upsert_user` 等方法，但接口定义上没有
- 用户注册后默认 `status="locked"`，但没有 unlock 机制暴露
- `alpha_id/__init__.py` 导出了 `Container`, `Agent`, `AIDSigner`, `ProofOfExecution`，但 Skill 系统需要额外导入

---

## 三、架构亮点（这些应该保留）

### 3.1 Proof of Execution (PoE)

`alpha_id/poe.py` 真正理解了"去中心化身份需要的是证明而非信任"。每次技能执行生成一个签名过的、链式的执行证明。`CallChain` 的 `parent_poe_id` 参数允许追溯调用链路，这在 agent-to-agent 协作场景中是必需的设计。

### 3.2 SkillRepository 双层结构

```
repo/
  index.json        # 元数据索引（轻量，可快速浏览）
  skills/           # 实际技能文件（重量）
```

发布者只推送 `index.json`，消费者选择性拉取技能文件。这在去中心化的技能市场设计里是对的。

### 3.3 社交恢复（Social Recovery）

`core/recovery.py` 的时间锁 + 见证人阈值机制，是真实的去中心化密钥恢复方案，参考了以太坊的 social recovery wallet。虽然实现简单，但设计思路是对的。

### 3.4 ActionEngine 审批矩阵

按 **行动类型 × 平台** 配置审批策略：

- `AUTO` — 自动执行
- `NOTIFY` — 执行并通知
- `CONFIRM` — 需确认
- `REVIEW` — 需审查内容
- `BLOCK` — 拒绝

这是 agent 安全里一个成熟的设计模式，覆盖了从完全自主到完全受控的区间。

---

## 四、重新设计：统一架构方案

### 核心设计原则

1. **一个有且仅有一个职责**
2. **不要有两个东西做同一件事**
3. **每层的 API 契约先行，实现可以换**
4. **国际化的代价应该在第一天就付掉**

### 架构总图

```
┌─────────────────────────────────────────────┐
│             API Layer (Flask)                 │
│  REST endpoints → 路由到下层，i18n 错误消息      │
├─────────────────────────────────────────────┤
│             CLI Layer (click)                 │
│  命令行入口，对等层，不包含业务逻辑                │
├──────────┬──────────┬───────────────────────┤
│  Agent   │ Network  │      Skill Layer       │
│  (brain) │  Layer   │  (signer + poe + repos)│
│  大脑·记忆 │ P2P 对等  │  ity + runtime)        │
│  情绪·信誉 │ 调用链    │  执行证明 + 属性追踪     │
│  社交·风险 │ DID 传输  │                       │
├──────────┴──────────┴───────────────────────┤
│           Identity Layer (DID)               │
│  signer.py (唯一实现, cryptography)            │
│  did_resolver · key management · recovery    │
├─────────────────────────────────────────────┤
│           Storage Backend                    │
│  JsonStorage(dev) → SqliteStorage(prod)      │
│  统一接口定义，可热切换                          │
└─────────────────────────────────────────────┘
```

### 第 0 层：基础设施

**显式化 StorageBackend 接口：**

```python
class StorageBackend(ABC):
    def load(self, namespace: str, key: str) -> Any: ...
    def save(self, namespace: str, key: str, value: Any) -> None: ...
    def delete(self, namespace: str, key: str) -> None: ...
    def list_keys(self, namespace: str) -> List[str]: ...
    def query(self, namespace: str, **filters) -> List[Tuple[str, Any]]: ...
```

所有模块都依赖这个接口，不再自己 `json.load(open(...))`。

**中文 → key-based i18n：**

```python
# 不写
raise ValueError("缺少 Authorization header")

# 写
raise ValueError(ErrMsg.MISSING_AUTH_HEADER)
```

`ErrMsg` 是一个枚举，值 = 英文 key。渲染时查 Locale 表。测试断言枚举名而非中文文本。

### 第 1 层：Identity Layer（唯一 DID 实现）

```
alpha_id/
  signer.py         ← 唯一生产实现（cryptography）
  did.py            ← 迁到 docs/handwritten_ed25519.py（参考用途）
  did_resolver.py   ← 保留，完善
  recovery.py       ← 从 core/ 移来（它是 DID 层的功能）
```

```python
class AIDSigner:
    def generate() -> str                    # 创建 DID
    def sign(data: bytes) -> bytes            # 签名
    def verify(data, signature, pub_key?) -> bool  # 验签
    def sign_json(obj: dict) -> bytes         # JSON 签名（sort_keys）
    def verify_json(obj, signature) -> bool
    def export_private_key() -> bytes
    def load_from_aid_dir(path) -> str
    def to_did_document() -> DIDDocument      # 新增
    def recover(did, witnesses, new_key) -> RecoveryRequest  # 新增
```

### 第 2 层：Skill Layer（最完善的一层，基本不动）

只加集成点：
1. `SkillRuntime.execute()` 接受 `TwinBrain` 作为上下文
2. PoE 存储复用统一 StorageBackend
3. 技能执行后触发大脑状态更新

```python
class SkillRuntime:
    def execute(self, name, params, executor_did, brain=None):
        result = self._run_skill(...)
        if brain:
            brain.on_skill_executed(name, success=True, duration=elapsed)
        return result
```

### 第 3 层：Agent Layer（从 core/ 拆分并精简）

`twin_brain.py` 当前职责过多。拆为四个子模块：

```
core/
  brain/
    __init__.py       # TwinBrain 外观模式
    state_machine.py  # 状态机（awake → idle → think → act → sleep）
    thinking.py       # think() 循环逻辑
    memory.py         # MemoryStore
    emotion.py        # 情绪计算
  social/
    manager.py        # AlphaSocialManager
    message.py        # Message 模型
  reputation/
    engine.py         # ReputationEngine
  risk/
    engine.py         # RiskAssessmentEngine
  action/
    engine.py         # ActionEngine
```

**TwinBrain 变成外观层：**

```python
class TwinBrain:
    def __init__(self, alpha_id, storage, identity: AIDSigner):
        self.identity = identity          # ← 大脑现在有 DID 了
        self.state = StateMachine()
        self.memory = MemoryStore(alpha_id, storage)
        self.social = AlphaSocialManager(storage)
        self.reputation = ReputationEngine(alpha_id, storage)
        self.risk = RiskAssessmentEngine()
        self.action = ActionEngine()
        self.react = ReActEngine(alpha_id, brain=self)
```

### 第 4 层：Network Layer（打通 core 和 alpha_id 的关键）

```python
class AgentNetwork:
    def __init__(self, identity: AIDSigner, brain: TwinBrain = None):
        self.identity = identity
        self.brain = brain      # ← 连接大脑！
        self.peers: dict[str, AgentPeer] = {}
    
    def call_skill(self, peer_did, skill_name, params):
        # 1. 认证对等节点
        # 2. 验证技能来源
        # 3. 执行 + PoE
        # 4. 通知大脑
    
    def send_message(self, peer_did, content):
        return self.brain.social.send_message(...)
```

`AgentNetwork` 成为跨 DID 的传输层，`TwinBrain` 是每个 Agent 的内部大脑。

### 第 5 层：API Layer（统一路由）

```
/api/v1/
  auth/          ← 注册、登录、刷新 token
  identity/      ← DID 文档、公钥管理
  brain/         ← 状态、思考、情绪、记忆
  social/        ← 好友、消息
  skills/        ← 技能注册、搜索、执行
  network/       ← 对等节点管理
  risk/          ← 风险评估
  recovery/      ← 社交恢复
```

每个 blueprint 是薄层，只做：参数解析 → 调用下层 → 错误枚举转 HTTP → 统一 JSON 返回。

### 最终文件结构

```
aid/
  __init__.py
  identity/
    signer.py           # 唯一 DID 实现
    did_resolver.py
    recovery.py         # 从 core/ 移来
  skill/
    signer.py           # skill_signer 重命名
    registry.py
    runtime.py
    poe.py
    repository.py
    attribution.py
  agent/
    brain/
      __init__.py       # TwinBrain 外观
      state.py
      thinking.py
    social.py
    memory.py
    reputation.py
    risk.py
    action.py
  network/
    agent_network.py
    peer.py
  api/
    app.py
    blueprints/
    middleware.py
    errors.py           # i18n 错误枚举
  cli/
    main.py             # 统一入口
  storage/
    backend.py          # 接口定义
    json_storage.py
    sqlite_storage.py
  i18n/
    zh.py               # 中文消息表
    en.py               # 英文消息表
```

不再有 `src/core/` 和 `src/alpha_id/` 的割裂。所有代码在一个包 `aid/` 下，按功能组织。

---

## 五、改动量评估

| 改动 | 工作量 | 风险 |
|------|--------|------|
| 删掉手写 Ed25519（迁到 docs） | 1 人·时 | 低 |
| 统一 StorageBackend 接口 | 4 人·时 | 中 |
| 中文 → i18n key | 8 人·时 | 中 |
| core/did.py → from alpha_id.signer | 0.5 人·时 | 低 |
| TwinBrain 接收 AIDSigner 参数 | 2 人·时 | 低 |
| AgentNetwork 接收 TwinBrain 参数 | 3 人·时 | 中 |
| 重排文件结构 | 6 人·时 | 高（影响所有 import） |
| 统一 API 路由 | 4 人·时 | 低 |
| 测试适配新结构 | 8 人·时 | 中 |

**总计：约 36 人·时（一个全职开发者一周的量）**

---

## 六、未回答的问题

> **这个项目到底是做什么的？**

1. 如果是一个 **Agent 社交平台** → 打磨 `core/` 到可部署，补 API 文档，做前端
2. 如果是一个 **DID 协议实现** → 扔掉 `core/`，专注 `alpha_id/`，写规范文档
3. 如果是一个 **技能执行引擎** → `SkillRuntime` + `PoE` + `AgentNetwork` 做成独立包
4. 如果"都是" → 需要一个端到端场景证明它们的组合价值

---

## 七、后记

> 这个方案是一个合格的架构师答案，但我不确定它是对这个项目最好的答案。
>
> 读完整套代码后，真正让我记住的不是架构，而是 PoE 的链式证明、社交恢复的时间锁 + 见证人阈值、ActionEngine 的审批矩阵。这些是这个项目独特的地方。
>
> 结构只是结果，不是原因。先想清楚这个项目要成为什么，再来谈结构怎么组织。
