# AID 项目 — 给 Agent 的完整上下文

> 本文件替代以下散落文档：AGENTS.md · CARRY_OVER.md · CHATLOG.md · CONTINUE.md · FINAL_PLAN.md · LANDSCAPE.md · VISION.md · decisions.md
>
> **每次对话前自动注入。不要再读其他上下文文档。**

---

## 一、一句话定位

**AID（Alpha-ID）是你的数字灵魂 / Ghost Layer。** 它坐在所有 AI 工具（ChatGPT、Claude、Cursor）上面，提供跨平台属于你的身份、记忆和操作能力。

> 你换模型、换工具、换平台，AID 不换。

---

## 二、当前状态（2026-06）

| 指标 | 数值 |
|------|------|
| 技术地基完成度 | ~70% |
| 测试通过 | 525+ |
| 源文件 | `src/` 86 个 + `tests/` 26 个 |
| Phase 1「身份地基」 | ✅ 100% |
| Phase 2「信誉网络」 | ✅ 80% |
| Phase 3「身份自治」 | ✅ 75% |
| **产品形态（aid_daemon）** | ✅ **已有一个桌面悬浮球** |

---

## 三、已定死的决策（不再讨论）

| # | 决策 | 解释 |
|---|------|------|
| 1 | **不做模型、不做框架、不造协议、不做平台** | AID 搭便车：MCP（工具层）+ A2A（社交层） |
| 2 | **协处理器模式** | 私钥在本地（只能签名不能伪造），大脑在云端（只能验证不能伪造身份） |
| 3 | **没有独立界面** | AID 没有登录页、注册页、独立 App 窗口。通过 MCP 连接已有工具 |
| 4 | **语音为主、打字为辅** | 输入：麦克风→ASR→TTS 输出 |
| 5 | **操作层走 Computer Use** | 不看 API，不写插件。像人一样看屏幕、点鼠标、拖文件 |
| 6 | **DID 藏起来** | 对用户不提 DID、不提 Ed25519、不提 W3C。用户只感知"它能认出我" |
| 7 | **默认信任** | 80% 操作自动执行，只有高风险才确认 |
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
| 眼睛和手脚 | ✅ 截图+OCR+鼠标键盘 | `screen_capture.py`, `ocr.py`, `window_control.py` |
| 社交生态 | ⚠️ 半成品 | 缺 MCP/A2A 对接 |
| 自主学习 | ❌ 未写 | Phase 3 内容 |

### 目录结构

```
src/alpha_id/     # SDK — Agent, Container, DID, Signer, CLI, Web
src/core/         # 核心层 — TwinBrain, ReAct, MemoryStore, Social, Risk, ...
│  └── action_engine/  # 操作引擎
src/core/twin_brain.py     # 大脑状态机 ✅不改
src/core/agent.py          # Agent 思考循环 ✅不改
src/core/memory_store.py   # 记忆系统 ✅不改
src/tools/                 # Agent 工具集
src/tools/screen_capture.py   # 截图 ✅
src/tools/ocr.py              # OCR（新，零Coze依赖）✅
src/tools/window_control.py   # 鼠标键盘 ✅
src/tools/ocr_tool.py         # 旧OCR（绑死Coze）⛔ 待废弃
src/storage/              # 存储 — database, memory, S3
src/api/                  # FastAPI 路由
src/auth/                 # JWT 认证
src/aid_daemon.py         # 桌面精灵（Tkinter 悬浮球）✅ 706行
src/aid_mcp_server.py     # MCP 服务端
tests/                    # 26 个测试文件，525+ 测试
```

---

## 五、桌面精灵（aid_daemon.py）

这是目前唯一可演示的产品形态。**面试/展示用这个。**

- 桌面右上角暗色磨砂玻璃悬浮球
- 双击输入指令 / 右键菜单 / 拖拽移动
- 指令：`看屏幕`（截图+OCR）、`窗口列表`、`鼠标位置`、`点击 x y`、`输入 文本`

启动：`scripts/aid_daemon.bat`

---

## 六、Computer Use 三层闭环

```
Plan  层 → 意图分解（待建）
Skill 层 → screen_capture + ocr + window_control（✅已有）
Safety 层 → 风险控制（待建）
```

当前只做了 Skill 层。Plan 和 Safety 需要补。

---

## 七、路线图

### Phase 0（已完成/进行中）
- ✅ `aid_daemon.py` 桌面精灵
- ⬜ 结构重组（aid-core / aid-daemon / aid-import 分包）
- ⬜ 统一加密体系到 Ed25519
- ⬜ tools/ 从 LangChain 迁移到 MCP Server

### Phase 1（30天：冷启动解药）
- ⬜ 聊天导出导入器 → 分析对话历史 → 提取用户画像
- ⬜ 导入器+：GitHub / Claude / Cursor 数据源
- ⬜ MCP 暴露身份和记忆上下文
- ⬜ 第一个魔法时刻：导入后回原工具发现被记住了

### Phase 2（30天：眼睛和手脚）
- ⬜ Computer Use 三层闭环完整实现（Plan + Safety 层）
- ⬜ 可演示的最小闭环："帮我把桌面截图按日期分类"

### Phase 3（3个月：让它自己活着）
- ⬜ 观察者循环 / 自主学习循环 / 生态圈对接 A2A / 每日晨报

---

## 八、六项大胆升级（远期愿景）

| # | 升级 | 一句话 |
|---|------|--------|
| 1 | **离线生存** | 没有你，它还在 |
| 2 | **人格胚胎** | 它越长越像你 |
| 3 | **深度关系** | 不止认识，还懂你们之间 |
| 4 | **数字身体** | 一个有面孔和声音的存在 |
| 5 | **生态经济** | 能力即财富，信誉即货币 |
| 6 | **数字遗嘱** | 你走了，AID 替你守护记忆 |

---

## 九、市场格局（速览）

| 赛道 | AID 的位置 |
|------|-----------|
| 模型层（OpenAI/Anthropic/Google） | 不竞争，坐上面 |
| 协议层（MCP/A2A/DID） | 搭便车，不造协议 |
| 个人 AI 记忆（Mem/Rewind/Apple） | 差异：跨平台+身份绑定 |
| Computer Use（Claude/Operator） | 差异：有身份+记忆，不止操作 |
| Agent 框架（LangChain/CrewAI） | 不做框架，做产品 |
| 身份安全（Ceramic/DID项目） | 差异：从技术标准变成产品 |

**一句话：** 没有人在做"属于你的 Ghost Layer"。赛道是蓝海。

---

## 十、AID 的优势与劣势

### 优势
1. **赛道定位没有直接对手** — 无人区
2. **身份+记忆+操作三合一** — 别人只做其中一件
3. **技术地基扎实** — 70% 已完成，525+ 测试
4. **冷启动解药** — 第一天上手就导入已有数字痕迹

### 劣势
1. **执行力瓶颈** — 一个人 vs 几十人团队
2. **分发渠道为零** — 需要"现象级体验"打穿
3. **没有网络效应之前很脆弱**
4. **DID 包袱太重** — 技术藏不起来就是减分项

---

## 十一、代码约束

- Python 3.12+, 类型注解全覆盖, pyright basic
- 测试: pytest, 每次修改后跑 `python -m pytest tests/ -q`
- 格式化: ruff（配置在 ruff.toml）
- CLI 入口: `aid = "alpha_id.cli:app"`, 用 typer
- 核心逻辑写在 `core/`, 不依赖外部包
- ❌ 禁止引入 LangChain 作为依赖
- ❌ 禁止修改已有测试文件（除非只改预期值）
- ❌ 禁止发 git commit / 建分支
- ❌ 禁止加版权头
- ❌ 禁止改与当前任务无关的代码

---

*本文档由 AtomCode 于 2026-06 整理合并自以下源文件：AGENTS.md · CARRY_OVER.md · CHATLOG.md · CONTINUE.md · FINAL_PLAN.md · LANDSCAPE.md · VISION.md · decisions.md*
*原始散落文件可安全删除，上下文完整保留于此。*
