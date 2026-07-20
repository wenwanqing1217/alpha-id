# Alpha-ID 翻新方案

> 接手项目后的完整诊断与重构计划。

---

## 一、体检报告

### 好消息
- 测试 789 个全绿，基线稳
- 架构分层清晰：`core/`、`alpha_id/`、`entrypoints/` 分离
- 采集器有 `BaseCollector` + 6 个实现 + 自动发现，框架规范
- 画像 Schema 有版本、合并策略、来源追溯（`x_provenance`、`x_quality_map`、`x_alternatives`）
- CLI Typer 多子命令结构清楚
- MCP Server 已有骨架

### 坏消息：4 个底层结构性问题

#### 问题 1：三套画像/记忆系统并存，互不相通
- **MemoryStore** (`core/memory_store.py`) — 通用记忆存储
- **CoALAMemorySystem** (`core/coala_memory.py`) — 四层记忆
- **Mining** (`alpha_id/mining/`) — 本机痕迹扫描 → 推断画像
- **Collectors** (`alpha_id/collectors/`) — 从导出文件采集画像

数据流是断的。Mining 推断出的 `AlphaIDProfile` 不会进 CoALA 记忆，Collectors 采集到的画像不会触发 CoALA 的事实抽取。

#### 问题 2：DID 是"有名字的 UUID"，不是真正的 W3C DID
- 生成 Ed25519 密钥对 ✅
- 私钥存在本地 ✅
- 但没有 DID Document（没有 `service`、`verificationMethod`、`authentication`）
- 没有 DID 解析器
- 没有签名/验证能力对外暴露

#### 问题 3：Ghost Layer 的"注入"只做了一半
- MCP Server 暴露了 `profile://identity` 等资源，但返回的是静态 mock 数据
- `aid inject claude` 这个命令在文档里写了，代码里**不存在**
- 没有身份层注入，没有跨工具连续性验证

#### 问题 4：画像推断是"关键词正则匹配"，不是"认识你"
- inferrer 用正则匹配 `python`/`rust`/`fastapi` → 推断技术栈
- 统计消息长度 → 推断句子长度
- 统计问号比例 → 推断语气
- 这是 pattern matching，不是画像。同一个 Python 开发者得到完全一样的画像

---

## 二、翻新路线图

### Phase 0：底层统一（1-2 周，必须做，不能跳）

#### 0.1 统一 Profile + Memory 数据模型
- `AlphaIDProfile` 成为**唯一的用户画像数据模型**
- `AlphaMemory` 成为**唯一的记忆数据模型**
- Profile 和 Memory 通过 `memory_refs` 关联
- 所有 Collector / Miner / MCP / Web 都消费同一个 `Profile` 对象
- `profile_schema.py` 升级为 `Profile v1.0`，加入 `provenance`、`memory_refs`、`privacy_flags`
- 写 `docs/SCHEMA.md`

#### 0.2 DID 升级为真正的 W3C DID Document
- `core/did.py` 改为生成完整的 `DIDDocument`（JSON-LD 格式）
- `DIDRegistry` 增加 `resolve(did) → DIDDocument`
- `DIDRegistry` 增加 `sign(data) → signature` 和 `verify(did, data, signature) → bool`
- 私钥存储升级为加密的 keystore
- DID Document 存储在 `~/.alpha-id/did/did.json`

#### 0.3 MCP Server 接入真实 Profile 数据
- `profile_mcp_server.py` 改为从 `load_profile()` 读取真实数据
- 每个资源加本地鉴权
- 加入 `profile://provenance` 和 `profile://memory` 资源

### Phase 1：Ghost Layer 真正打通（2-3 周）

#### 1.1 MCP 自动注入到 Claude Desktop / Cursor
- 实现 `aid inject claude` / `aid inject cursor` / `aid inject list` / `aid inject remove`
- 注入的不是"profile 数据"，而是**身份上下文**
- 请求头携带 DID 签名，Alpha-ID 验证签名后返回对应权限级别的 profile

#### 1.2 画像推断从"正则匹配"升级到"特征工程 + LLM 蒸馏"
| 层 | 方法 | 输出 |
| 信号层 | 扫描本机文件 → 提取结构化信号 | 语言、框架、文件类型、活跃时段 |
| 特征层 | 特征工程（代码复杂度、commit 频率、命名习惯） | 编码风格、工作节奏、协作模式 |
| 推断层 | LLM 蒸馏（可选，有 API key 时启用） | 沟通风格、技术偏好、人格标签 |

- 没有 API key 时，信号层 + 特征层也能产出有意义的画像
- 画像字段数从 7 个扩展到 15-20 个

### Phase 2：魔法时刻打磨（1 周）

#### 2.1 Web 端升级
- 个人空间页面：画像卡片 + 来源追溯面板 + 记忆时间线 + 工作节律热力图
- 模拟盘入口：D3.js 2D 力导向图，不做 Three.js 3D

#### 2.2 Demo 脚本完善
- `python scripts/demo.py` 一键跑通完整链路
- 60 秒内完成 `init → mine → show → web`

### Phase 3：生态扩展（持续，不做硬截止）

| 功能 | 优先级 | 触发条件 |
| 扩展采集器（Claude/Cursor/Browser/Git） | P1 | Phase 1 用户反馈"希望采集更多来源" |
| 轻量 A2A 适配器 | P2 | 有 2+ 个 Alpha-ID 用户需要互联 |
| 因果图谱 MVP | P2 | 用户说"我想知道这个偏好是怎么来的" |
| 双大脑拆分（理解脑 + 执行脑） | P3 | TwinBrain 职责变得模糊 |
| 完整七框架引擎 | P3 | A/B 测试证明框架约束有效 |
| 数字遗产/继承 | P4 | 有用户明确需要 |
| 3D 宇宙 | P4 | Web 端 2D 版本用户反馈良好 |

---

## 三、需要你对齐的 4 个关键决策

1. **CoALA 四层记忆是核心还是可选？**
   - 建议：是核心基础设施，Phase 0 统一

2. **LLM 蒸馏是 Phase 1 必须还是 Phase 2？**
   - 建议：Phase 1 加入，但做可选的（有 API key 时启用）

3. **DID 要完整实现 W3C 规范还是保持现状？**
   - 建议：最小实现 W3C DID Core（DID Document + resolve + sign/verify）

4. **模拟盘是 Phase 1 还是 Phase 3？**
   - 建议：Phase 1 只做 2D 力导向图概念验证，Phase 3 做 3D

---

## 四、一句话总结

> 你的项目文档领先代码 3 个 Phase，但代码的骨架比文档里写的更结实。真正的翻新不是"加功能"，而是"把三套并存的系统统一成一套，把伪装的 DID 变成真正的 DID，把正则匹配的画像变成能让人说'它认识我'的画像"。
