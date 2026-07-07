# Alpha-ID — 最终落地方案（拍板版）

> 拍板原则：保留完整野心，不降级成 demo；先串通一条可演示的主链路，再扩展剩余模块。

## 拍板结论

1. **保留全系统愿景**：DID / I2I / A2A / 双大脑 / 模拟盘 / MCP 注入全都要。
2. **当前阶段只做“能串起来的最小完整链路”**：`aid init → aid profile mine --path . → aid profile show → aid profile web → aid-mcp`。
3. **先让第一个用户说“它认识我”**：Web 端作为第一展示面，模拟盘作为第二魔法时刻。
4. **不碰已稳定的 715 个测试**：只新增文件、只补缺失链路、只做展示层。
5. **商业叙事从“工具”转向“基础设施”**：记忆基础设施 + 可信代理层 + 本地主权 AI。

## 为什么这个方向是 2026 年对的

- **记忆层正在平台化**：Mem0 等证明“记忆是独立产品”，Alpha-ID 可以做带身份的记忆层。
- **Agent 执行层已成熟**：OpenClaw / Codex / Claude Code 证明“操作电脑”是标配，Alpha-ID 补“谁在执行”。
- **A2A 已进入生产**：v1.0 发布、CrewAI 原生支持；现在接入就能拿到第一批生态卡位。
- **隐私是硬约束**：中国《智能体规范应用与创新发展实施意见》、企业合规、个人数据主权都在上升。
- **跨工具连续性仍是空白**：多数产品绑定单一模型/平台，Alpha-ID 的“寄生式”Ghost Layer 仍是稀缺定位。

## 竞争优势

| 维度 | 竞品现状 | Alpha-ID 优势 |
|------|----------|---------------|
| 身份 | 中心化账号 / Agent 自己的 DID | 人的 `did:aid:` + 本地私钥 |
| 记忆 | 孤岛记忆 / 功能模块 | 跨平台连续记忆 + 人格化画像 |
| 注入 | 单一平台内置 | MCP / A2A 跨工具接入 |
| 操作 | 通用 Computer Use | 身份驱动的有边界操作 |
| 数据主权 | 云端优先 | 本地优先，私钥不上传 |
| 展示 | 功能拼盘 | 数字灵魂 + 模拟盘体验 |

核心壁垒不是某个功能，而是：**用户在 Alpha-ID 里留下的历史关系不可复制。**

## 商业可行性

- **短期**：开源影响力 + 面试叙事 + 本地主权 AI 顾问/企业内网版。
- **中期**：面向重度 AI 用户的订阅服务（同步、备份、高级记忆分析）。
- **长期**：A2A 生态中的可信身份/记忆标准组件，或数字遗产/继承服务。

结论：**可行，且窗口期正在收窄**。重点不是“有没有人做”，而是“谁先做成可演示的完整系统并占领叙事”。

## 拍板后的版本路线

### V1.0 — 全链路可演示

- 主链路：`aid init → aid profile mine --path . → aid profile show → aid profile web → aid-mcp`。
- 展示层：Web 端个人空间 + 星链宇宙 + 模拟盘 MVP。
- 文档层：README + 30s/3min demo script + 架构图。

### V1.1 — 稳定与采集扩展

- 修复已知阻塞问题。
- 扩展采集器：Claude / Cursor / Git / 浏览器。
- 补 MCP 自动注入到主流客户端。

### V2.0 — 深度能力

- 双大脑职责拆分 + 因果图谱。
- 轻量 A2A 适配器。
- 语音通路（ASR/TTS）作为第二交互入口。

### V3.0 — 生态

- I2I + A2A 完整闭环。
- 数字遗产。
- 对外发布记忆/身份标准组件。

## 立即执行文件清单

```text
projects/src/alpha_id/mining/__init__.py
projects/src/alpha_id/mining/scanner.py
projects/src/alpha_id/mining/extractor.py
projects/src/alpha_id/mining/inferrer.py
projects/src/alpha_id/cli/profile_commands.py
projects/src/alpha_id/web/pages/profile.py
projects/src/alpha_id/web/pages/simulation.py
projects/docs/narrative.md
```

## 本周验收标准

1. `aid profile mine --path .` 能输出完整画像。
2. `aid profile show` 有“完整度 + 来源追溯”。
3. `aid profile web` 可打开个人空间。
4. `aid-mcp` 可被 MCP 客户端读取 `profile://identity`。
5. README + demo script 可用来面试演示。
