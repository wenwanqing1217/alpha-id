# Alpha-ID 全项目执行方案

> **核心任务：把散落于各 AI 工具中的"你"收集回来，变成一个统一的数字身份——Ghost Layer。**

---

## 第一卷：项目全貌 — Ghost Layer 七层架构

```
                    ┌─────────────────────────┐
                    │      Ghost Layer        │
                    │  注入所有 AI 工具之上   │
                    └─────────────────────────┘
                              │
     ┌───────────┬────────────┼────────────┬───────────┐
     │           │            │            │           │
     ▼           ▼            ▼            ▼           ▼
  ┌───────┐  ┌───────┐  ┌─────────┐  ┌───────┐  ┌───────┐
  │ A2A层 │  │ MCP层 │  │ 采集器  │  │ 图谱  │  │ 记忆层│
  │ I2I   │  │ 注入   │  │  层     │  │ 层    │  │       │
  └───────┘  └───────┘  └─────────┘  └───────┘  └───────┘
     │           │            │            │           │
     └───────────┴────────────┼────────────┴───────────┘
                              ▼
                       ┌──────────┐      ┌──────────┐
                       │ Profile  │      │   DID    │
                       │ 画像层   │      │ 身份层   │
                       └──────────┘      └──────────┘
```

| # | 层名 | 组件说明 | 状态 |
|:-:|:-----|:--------|:----:|
| 1 | **DID 身份层**（底层） | `did:aid:` + Ed25519，所有上层的锚点 | ✅ |
| 2 | **Profile 画像层** | 语言风格画像 + 技术画像 + 时间节律画像 | ✅ |
| 3 | **三层记忆层** | 工作记忆 / 情景记忆 / 语义记忆 | ✅ |
| 4 | **因果图谱层** | 决策 → 行动 → 结果 的因果链 | ⏳ |
| 5 | **采集器层** | 多源数据采集（ChatGPT / Claude / Trae / 浏览器 / 代码） | 🔄 |
| 6 | **MCP 注入层** | 把身份 / 画像 / 记忆通过 MCP 协议暴露给所有 AI 工具 | ⏳ |
| 7 | **A2A 关系层** | DID 与 DID 之间的关系网络（I2I：Identity-to-Identity） | ⏳ |

---

## 第二卷：路线图 — 四阶段

```
Phase 0 ─ 画像骨架 ─────────── ✅ 已完成
  ├── DID 存在 + Profile 有内容
  ├── 单一数据源跑通 collect → extract → show
  ├── 完成标志（技术）：`aid init && aid collect chatgpt <zip> && aid profile show`
  └── 完成标志（一句话）：用户看到 `aid profile show` 输出一句有内容的自我描述，不是空壳

Phase 1 ─ 多源采集 ─────────── 🔄 当前
  ├── 从"一个导入器"升级到"一套采集器框架"
  ├── 核心产物：统一 Collector 协议 + 自动发现
  ├── 完成标志（技术）：任何用户的本机数字痕迹（聊天/代码/浏览/笔记）都能在 5 分钟内被采集
  ├── 完成标志（一句话）：用户运行 `aid collect scan` 后，`aid profile show` 输出的画像显著比 Phase 0 更丰富
  └── 关键新命令：`aid collect list` / `aid collect scan`

Phase 2 ─ 思维复制与注入 ───── ⏳ 待启动
  ├── 从"认识你"升级为"像你一样思考"
  ├── 核心产物 A：MCP Profile Server（暴露身份/画像/记忆给所有 MCP 客户端）
  ├── 核心产物 B：思维框架引擎（3个核心框架：第一性原理 / 反向推翻 / 节律控制）
  ├── 核心产物 C：轻量因果图谱（手动标注起步 + LLM 辅助抽取，非完整引擎）
  ├── ⚡ 先验假设（优先执行）：A/B 测试 — 同一问题，有框架约束 vs 无约束，收集用户偏好
  │      ▸ 命令：`aid test ab --question "..."` ，CLI 终端展示两个回答
  │      ▸ 原理：同一 LLM 调两次，A 带框架约束 prompt（如第一性原理），B 不带约束
  │      ▸ 展示：终端并排输出 A/B，用户选 A / B / 平局
  │      ▸ 存储：~/.alpha-id/ab_results.json，记录每次选择
  │      ▸ 成功标准：≥50 次有效选择，约束胜率 >60% → 铺开；否则重评框架策略
  ├── 完成标志（技术）：Claude Desktop / Cursor / Trae 均能通过 MCP 获取用户画像 + 思维框架约束
  ├── 完成标志（一句话）：用户在 Claude Desktop 里输入"我是谁"，得到"你是一个凌晨活跃的 Python 开发者，喜欢函数式编程，最近在做向量数据库项目"；问"我该学 Rust 还是 Python"时，得到按他的思维框架（第一性原理拆解 + 反向推翻验证 + 节律控制收敛）整合后的分析，而非单选题
  └── 关键体验：
       ▸ Claude 问代码 → 注入"擅长 Python/TypeScript，喜欢简洁风格"
       ▸ Cursor 写代码 → 注入框架偏好 / 命名风格
       ▸ 用户做决策 → 思维框架引擎约束 LLM 推理路径（7 步强制流程）
       ▸ 浏览器搜资料 → 记录并建立因果节点

Phase 3 ─ 关系网络与完整框架 ── ⏳ 远期
  ├── DID 与 DID 之间建立关系（朋友/同事/合作/陌生）
  ├── 核心产物：A2A (I2I) 协议 — 发现 → 握手 → 建立关系 → 关系图谱
  ├── 完整七框架引擎（Phase 2 的 3 个 → 全部 7 个）
  ├── 完成标志（技术）：两个 Alpha-ID 用户可以互相"认识"，共享画像片段（带签名验证）
  └── 完成标志（一句话）：两个 Alpha-ID 用户互相发现，建立朋友关系，双方的数字存在开始互动
```

---

## 第三卷：当前焦点 — Phase 1 详细执行清单

按优先级排序，每项含：**任务 / 描述 / 完成标准 / 预计代码量**。

| # | 任务 | 描述 | 完成标准 | 预计代码量 |
|:-:|:----|:-----|:---------|:----------:|
| 1 | **BaseCollector 协议** | 从现有 `ChatGPTCollector` 抽取基类：`detect()` / `collect()` / `summary()` / `info`，定义 `source / quality / timestamp` 三字段输出规范 | `ChatGPTCollector(BaseCollector)` 重构完成，原有 `aid collect chatgpt` 功能不破；基类接口清晰可被新采集器实现 | ~200 行（含 ChatGPT 重构） |
| 2 | **自动发现** | `collectors/__init__.py` 遍历目录，自动注册所有 `BaseCollector` 子类 | 新增一个 `FooCollector` 文件即出现在 `aid collect list` 中 | ~50 行 |
| 3 | **来源标记 + merge** | `MemoryItem` 带 `source / quality / timestamp`；`merge_profile` 在冲突时取 `quality` 高者 | 同一画像项被两个采集器给出的值不同时，展示 `quality` 高的那个，另一值保留为备选 | ~100 行 |
| 4 | **aid collect scan** | 检测本机可用数据源 → 顺序采集 → 增量合并 → 输出汇总。无导出数据时降级为本机信号扫描（shell/git/后缀/书签/剪贴板）——也就是 #6 冷启动逻辑在此实现 | `aid collect scan` 一键跑完，输出"已采集 N 个来源，画像更新了 M 项" | ~200 行（含冷启动降级逻辑） |
| 5 | **aid collect list** | 列出所有已注册采集器 + 状态（可用/未检测到/已采集）+ 上次采集时间 | `aid collect list` 输出采集器表格 | ~60 行 |
| 6 | **场景识别** | 硬编码规则：窗口标题 / 文件后缀 / 当前时间 → 判断场景（写代码/写邮件/聊天）。结果供 daemon 做 Profile 注入用 | 手动触发检测，输出"当前场景：写代码（IDE 窗口检测到），建议注入技术偏好画像" | ~100 行 |

**关键新架构要求：**

- 每个采集器继承 `BaseCollector`，统一 API
- 自动注册：放在 `collectors/` 目录下即被发现
- 统一来源标记：`source` / `quality` / `timestamp` 三字段缺一不可
- `merge_profile` 必须读取 `quality`，在冲突时做出决策

---

## 第四卷：Phase 2 执行清单（预排，Phase 1 完成后启动）

| # | 任务 | 描述 | 完成标准 | 预计代码量 |
|:-:|:----|:-----|:---------|:----------:|
| 1 | **A/B 测试框架** | `aid test ab --question "..."` CLI 命令。同一 LLM 调两次，A 带框架约束 prompt，B 不带，终端并排展示，用户选 A/B/平局 | 跑 10 次测试，结果写入 `~/.alpha-id/ab_results.json`，`aid test ab --stats` 可查看统计 | ~150 行 |
| 2 | **FrameworkEngine 基类 + 第一性原理** | `core/framework_engine.py`：`FrameworkEngine` 基类定义 `constrain(prompt) → constrained_prompt`。首个实现 `FirstPrinciples`（压缩→重建四步） | `FirstPrinciples.constrain("我该学 Rust 还是 Python")` 返回带四步约束的 prompt；可被 #1 A/B 测试调用 | ~200 行 |
| 3 | **反向推翻 + 节律控制** | 补完 Phase 2 的三框架：`ReverseDisproof`（证伪五步）、`RhythmControl`（扩散/收缩检测） | 三个框架均可独立实例化，`FrameworkEngine.list()` 列出全部可用框架 | ~200 行 |
| 4 | **MCP Profile Server 激活** | 现有 `mcp/profile_mcp_server.py`（191行骨架）接入真实画像数据。暴露 `profile://identity`、`profile://style`、`profile://memory` 三个资源 | `aid-mcp` 启动后，Claude Desktop MCP 客户端可读取上述三个资源 | ~100 行 |
| 5 | **MCP 注入 Claude Desktop** | 自动检测/写入 `claude_desktop_config.json`，注入 Profile MCP Server 配置 | 用户运行 `aid inject claude` → 重启 Claude Desktop → 输入"我是谁" → Claude 返回画像内容 | ~80 行 |
| 6 | **MCP 注入 Cursor / Trae** | 同上，适配 Cursor 和 Trae 的 MCP 配置路径 | `aid inject cursor` / `aid inject trae` 可用 | ~80 行 |
| 7 | **轻量因果图谱** | 手动标注 API：`aid graph link --from "学 Rust" --to "做系统编程" --cause "性能需求"`。LLM 辅助批量抽取（喂对话记录，自动建议因果边） | 至少 10 条因果边，`aid graph show` 展示当前图谱 | ~200 行 |

**Phase 2 总预计代码量：~1010 行**

**依赖链：**
```
#1 A/B 测试 ─────────────────────────────┐
    └→ #2 第一性原理 ─────────────────────┤
         └→ #3 反向推翻+节律控制 ─────────┤
                                         │
#4 MCP Server 激活 ─────────────────────┤
    └→ #5 Claude 注入 ───────────────────┤
         └→ #6 Cursor/Trae 注入 ─────────┤
                                         │
#7 因果图谱 ─── 并行（依赖画像稳定） ────┘
```

---

## 第五卷：Phase 3 概要（远期，详细执行清单届时另排）

| 领域 | 核心交付 | 一句话完成标志 |
|:-----|:--------|:------------|
| **I2I 发现协议** | `aid agent discover` — 局域网/互联网扫描其他 Alpha-ID 节点 | 两个 AID 节点互相发现，展示对方昵称和公开标签 |
| **I2I 握手 + 关系图谱** | DID 签名握手 → 建立关系（朋友/同事/陌生） → 关系图谱持久化 | A 向 B 发起握手，B 确认，双方关系图谱各自更新 |
| **完整七框架引擎** | Phase 2 的 3 框架 → 补全宇宙星链/递归降维/反脆弱/全息追溯 | 全部 7 框架可被 A/B 测试调用，`FrameworkEngine.list()` = 7 |
| **数字遗嘱** | 用户可指定继承者 DID，触发条件（90天未活跃）后自动转移记忆和画像 | 用户设置遗嘱 → 触发条件满足 → 继承人收到通知 |
| **Web 宇宙** | Three.js 3D 图谱可视化：画像球体 + 因果连线 + 关系网络 | 浏览器打开 `aid web` → 看到自己的数字宇宙 3D 图 |

---

## 第六卷：什么不做（当前范围冻结）

| ❌ 不做 | 原因 |
|:------|:-----|
| MCP 身份注入（Phase 2 才做） | 当前优先把"采集→画像"框架跑通；注入依赖画像稳定 |
| Computer Use Plan 层 / Safety 层 | 有真实用户反馈后再加入 |
| A2A 协议 | 推迟到 Phase 3；先让"一个人认识自己" |
| 语音交互 | Phase 2+ 做 ASR/TTS 通路，Phase 3 做声线人格化 |
| 修改既有 803+ 测试文件 | 只新增测试，不改旧 |
| 引入 LangChain | 项目不依赖重框架；保持 `core/` 轻量无外部包 |
| 发 git commit / 建分支 | 工作目录就地开发，版本管理不在本阶段 |
| 加版权头 / 修改与任务无关的代码 | 保持最小改动原则 |
| 因果图谱层（Decision→Action→Result） | Phase 2 之后，画像稳定再建 |

---

## 第七卷：代码约束（继承自 decisions.md §八）

> 完整约束参见 `docs/decisions.md` §八。

- **测试**：`pytest`，每次修改后跑 `python -m pytest tests/ -q`
- **格式化**：ruff（配置在 `ruff.toml`）
- **CLI 入口**：`pyproject.toml` 中 `aid = "alpha_id.cli:app"`，用 typer
- **新增模块必须加 `__init__.py`**，导出公共接口
- **核心逻辑写在 `core/`**，不依赖外部包
- ❌ 禁止引入 LangChain 作为依赖
- ❌ 禁止修改已有测试文件（除非只改预期值）
- ❌ 禁止发 git commit / 建分支
- ❌ 禁止加版权头
- ❌ 禁止改与当前任务无关的代码

---

> **执行力准则：确认方向后，按优先级顺序执行，不跳不偏。**
> *Version: 2.0 | Last updated: 2026-06-07*
