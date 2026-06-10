# Alpha-ID 项目：最终方案总汇

> 给 Codex 的完整上下文。不需要再读任何其他文档。
> 创建时间：2026-05-30 | 来源：AtomCode（deepseek-v4-flash）与项目创建者的深度对话

---

## 一、一句话定位

**AID 是你的数字灵魂 / Ghost Layer。** 它坐在所有 AI 工具（ChatGPT、Claude、Cursor）上面，提供跨平台属于你的身份、记忆和操作能力。

> 你换模型、换工具、换平台，AID 不换。

---

## 二、当前状态（2026-05-30）

| 指标 | 数值 |
|------|------|
| 技术地基完成度 | ~70% |
| 测试通过 | 525+ |
| 源文件 | src/ 86 个 + tests/ 26 个 |
| Phase 1 身份地基 | ✅ 100% |
| Phase 2 信誉网络 | ✅ 80% |
| Phase 3 身份自治 | ✅ 75% |
| **产品形态** | ❌ **没做出来（核心卡点）** |

---

## 三、已经定死的决策（不再讨论）

| # | 决策 | 解释 |
|---|------|------|
| 1 | **不做模型、不做框架、不造协议、不做平台** | AID 搭便车：MCP（工具层）+ A2A（社交层） |
| 2 | **协处理器模式** | 私钥在本地（只能签名不能伪造），大脑在云端（只能验证不能伪造身份） |
| 3 | **没有独立界面** | AID 没有登录页、注册页、独立 App 窗口。通过 MCP 连接已有工具 |
| 4 | **语音为主、打字为辅** | 输入：麦克风→ASR→TTS；输出：TTS 播报 |
| 5 | **操作层走 Computer Use** | 不看 API，不写插件。像人一样看屏幕、点鼠标、拖文件 |
| 6 | **DID 藏起来** | 对用户不提 DID、不提 Ed25519、不提 W3C。用户只感知"它能认出我" |
| 7 | **默认信任** | 80% 操作自动执行，只有高风险才确认。对标 BCI 时代的原则 |
| 8 | **冷启动不教而获** | 第一天上手就导入已有的数字痕迹（ChatGPT 导出、GitHub、浏览器历史） |
| 9 | **core/ 层零外部依赖** | 核心大脑不绑任何第三方库 |
| 10 | **商业模式** | 身份永久免费；可选云端同步 $4.99/月；生态圈抽成 5% |

---

## 四、核心架构

### 四层结构

```
用户客户端（私钥在本地，只能签名不能伪造）
    ↓ API / MCP
TwinBrain（大脑/云端，只能验证/执行，不能伪造身份）
    ↓
工具层（screen_capture / OCR / window_control / 文件操作）
    ↓
存储层（SQLite + 向量记忆）
```

### 五层能力

| 层 | 代码情况 | 说明 |
|---|---------|------|
| 统一身份 | ✅ DID + Ed25519 签名 | `did:aid:you`，私钥在本地 |
| 孪生大脑 | ✅ TwinBrain 状态机 | 三层记忆：工作记忆 + 情景记忆 + 语义记忆 |
| 眼睛和手脚 | ✅ 截图+OCR+鼠标键盘（散着的） | 详见下面第五节的 Computer Use 闭环 |
| 社交生态 | ⚠️ 半成品 | 缺 MCP/A2A 对接 |
| 自主学习 | ❌ 未写 | Phase 3 内容 |

### 架构目录

```
src/alpha_id/     # SDK — Agent, Container, DID, Signer, CLI(typer), Web(FastAPI)
src/core/         # 核心层 — TwinBrain, ReAct, MemoryStore, Social, Risk, Reputation, PoE
│  └── action_engine/  # 操作引擎
src/tools/        # Agent 工具 — screen_capture, OCR(新), window_control, identity...
src/storage/      # 存储 — database, memory, S3
src/api/          # FastAPI 路由
src/auth/         # JWT 认证
src/utils/        # 工具函数
```

---

## 五、Computer Use 三层闭环（核心操作架构）

```
Plan  层 → 意图分解：把"帮我把桌面截图按日期分类"拆成 N 步（待建）
Skill 层 → 具体工具：screen_capture + ocr + window_control（✅ 已有）
Safety 层 → 风险控制：敏感操作暂停、版本回溯、录屏审计（待建）
```

**当前 Skill 层工具状态：**

| 工具 | 文件 | 状态 |
|------|------|------|
| 截图 | `src/tools/screen_capture.py` | ✅ 质量高，风格好 |
| OCR | `src/tools/ocr.py` | ✅ **本轮新写**，345 行，零 Coze 依赖 |
| 鼠标键盘 | `src/tools/window_control.py` | ✅ 可用 |
| 旧 OCR（保留不动） | `src/tools/ocr_tool.py` | ⛔ 绑死 Coze，待废弃 |
| 旧视觉（保留不动） | `src/tools/vision_tool.py` | ⛔ 绑死 Coze，待废弃 |

**OCR 新文件设计要点：**
- 双后端：Tesseract（免费离线）+ LLM 视觉（OpenAI 兼容 API）
- 三个核心函数：`extract_text()` / `extract_structured()` / `analyze()`
- langchain 是可选皮肤，核心零依赖
- 11 个测试全绿（8 passed + 3 skipped=无 Tesseract 引擎）
- 风格完全对齐 `screen_capture.py`（延迟导入、优雅降级、清晰报错）

---

## 六、三阶段路线图

### Phase 1「身份地基」: 2.7 → 3.5（8 周）

| 子项 | 做什么 | 优先级 |
|------|-------|--------|
| **P1-0 Agent DID Registry** | CLI `aid identity init/show/verify`，`.aid/` 目录规范 | 🔴 最高 |
| P1-1 ReAct Agent | `TwinBrain.think()` → LLM 调用 → ReAct 循环 | 🟡 |
| P1-2 向量记忆 | ChromaDB + sentence-transformers 语义搜索 | 🟡 |
| P1-3 数据库加密 | SQLite AES-Fernet 透明加密 | 🟢 |
| P1-4 ML 风控增强 | IsolationForest 异常检测 | 🟢 |
| P1-5 CLI 工具 | Typer CLI `aid` 命令 | 🟡 |
| P1-6 演示 Web App | FastAPI + 多 Agent 可视化 | 🟢 点缀 |

### Phase 2「信誉网络」: 3.5 → 4.0（3 个月）
- P2-1 技能签名与验证
- P2-2 使用归因与信誉图谱
- P2-3 跨框架运行时抽象 ✅（已完成）

### Phase 3「身份自治」: 4.0 → 4.5（6 个月）
- P3-1 执行证明 PoE
- P3-2 去平台化协议
- P3-3 多 Agent 协作自治

---

## 七、⚠️ 关键冲突：两套 Plan 必须选一条

项目目前存在两套路线方案，**必须二选一**，不能混着走：

| 维度 | VISION 路线（产品驱动） | ROADMAP 路线（技术驱动） |
|------|-----------------------|------------------------|
| **第一个交付** | 导入器（冷启动解药） | DID Registry（身份地基） |
| **优先级** | 产品体验优先，让用户先"Wow" | 技术基础设施优先，再盖房子 |
| **Phase 0** | 有（结构重组+加密统一+Daemon） | 无（直接从 P1 开始） |
| **Computer Use** | Phase 2 主力 | 未明确提及 |
| **Daemon** | Phase 0 就要写 | 未明确提及 |
| **写于** | 2026-05（更新） | 2025-07（较旧） |

### AtomCode 的建议

**选 VISION 路线。** 理由是：
1. ROADMAP 是 2025 年 7 月写的，VISION 是 2026 年 5 月更新的
2. VISION 有"产品形态"的思考，ROADMAP 没有
3. 当前瓶颈不是技术（70% 地基已做完），是产品
4. DID Registry 对用户毫无意义，用户不关心"你的身份基础设施"，用户只关心"它今天能帮我做什么"

> **建议你先想清楚选哪条路。选定之前别写任何代码。**

---

## 八、等你和 Codex 讨论的 5 个待定问题

### 1. 第一个交付做什么？

选项：
- A: DID Registry + CLI（ROADMAP 路线）
- B: 导入器 + 冷启动魔法时刻（VISION 路线）
- C: `aid_daemon.py` 串起来现有能力（直觉路线）
- D: 混合 —— 先做 DID Registry，但包装成"导入器"

### 2. OCR 怎么融入大计划？

目前是孤立的 `tool`。需要 Plan 层（意图分解）和 Safety 层（风险控制）才能构成完整的 Computer Use 闭环。

### 3. Phase 0 要不要存在？

结构重组（core/daemon/import 分包）+ 统一加密 + tools 迁 MCP Server。

### 4. Daemon 什么时候写？

这是"库"变"存在"的关键一步。写完 daemon，AID 就是一个可以一直在后台跑的东西。

### 5. 测试策略？

现在 525+ 测试。新加代码的测试策略：
- core/ 层：单元测试全覆盖（已有）
- tools/ 层：mock 测试为主（已有雏形）
- daemon/ 层：需要新建 E2E 集成测试框架
- 不要为凑覆盖率写测试

---

## 九、最小惊艳版本（MVP+ 建议）

如果 2 周后要给人演示，建议做到：

```
1. 跑起 daemon（后台服务）
2. MCP 连接 Claude Desktop（或任何 MCP 客户端）
3. 在 Claude 里问："帮我看看桌面上有什么文件？"
4. daemon 调用 screenshot → OCR → LLM 理解 → 回答
5. 用户看到："你桌面上有 3 个文件夹：'项目资料'、'截图'、'临时'，还有 2 个文件……"
```

这不完美、不安全、不持久。但它的价值是：
- 让项目有了"活的东西"
- 让创造者自己看到它工作时感到兴奋
- 让给别人演示时从"看，这是代码"变成"看，它在回答我"

> **如果必须在"做对"和"活着"之间选，选活着。不完美的活物比完美的死库强一百倍。**

---

## 十、声线人格的建议

AGENTS.md 说"Phase 2 再定"——建议现在就定一个简单的。

理由：
- 语音已经是确认的交互方式
- 沉默的 AI 是工具，会说话的才是"存在"
- 一个简单的 TTS（edge-tts 免费，中文好，Windows 原生支持）会彻底改变对项目的感知

---

## 十一、市场格局一览

| 赛道 | 玩家 | AID 的位置 |
|------|------|-----------|
| 模型层 | OpenAI/Anthropic/Google/Meta | 不竞争，坐上面 |
| 协议层 | MCP/A2A/DID/AT Protocol | 搭便车，不造协议 |
| 个人 AI 记忆 | ChatGPT Memory/Mem.ai/Rewind | 差异：跨平台、身份绑定 |
| Computer Use | Claude/Operator/Browser Use | 差异：有身份+记忆，不止操作 |
| Agent 框架 | LangChain/CrewAI/AutoGen | 不做框架，做产品 |
| 身份安全 | Ceramic/Spruce/DID 项目 | 差异：从技术标准变成产品 |
| 硬件/BCI | Neuralink/Synchron/Apple/Meta | 远期应用层，今天先落 BCI 原则 |

**一句话：** 没有人在做"属于你的 Ghost Layer"。赛道是蓝海，但用户不知道需要你。你的工作不是证明 AID 比谁好——是证明"这个类别应该存在"。

---

## 十二、已完成的战术动作（本轮对话产出）

| 动作 | 文件 | 状态 |
|------|------|------|
| 重写 OCR 工具 | `src/tools/ocr.py`（345行） | ✅ 完成，测试全绿 |
| OCR 测试 | `tests/test_ocr.py`（128行，11个测试） | ✅ 完成 |
| 此文档 | `FINAL_PLAN.md` | ✅ 当前文件 |

---

*本文档由 AtomCode（deepseek-v4-flash）编写于 2026-05-30*
*供项目创建者与 Codex 讨论使用*
