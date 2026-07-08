<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/status-alpha--showcase--ready-purple" alt="Status">
  <img src="https://img.shields.io/badge/focus-Ghost%20Layer%20%2F%20Digital%20Identity%20Infra-ff6" alt="Focus">
</p>

<h1 align="center">Alpha-ID</h1>

<p align="center">
  <strong>你的数字灵魂。</strong><br>
  不是另一个 AI 助手，是坐在所有 AI 工具之上的 Ghost Layer：换模型、换平台、换设备，Alpha-ID 不换。
</p>

<p align="center">
  <strong>一个数字身份，所有 AI 工具都认识同一个你。</strong>
</p>

---

## 30 秒说清它是什么

```bash
git clone https://github.com/wenwanqing1217/alpha-id
cd alpha-id/projects
pip install -e ".[dev]"
aid init
aid profile mine --path .
aid profile show
aid profile web
python scripts/demo.py
```

### 面试可直接讲

**一句话**：不是另一个 AI 助理，是坐在所有 AI 工具之上的 Ghost Layer。先看本机有什么，再决定采集什么；换工具、换平台，Alpha-ID 不换。

**三句话叙事**：
1. 大多数项目做“新增一个助手”；Alpha-ID 做“让所有工具都认识同一个你”。
2. 核心不是云记忆，而是本地 DID + 本机痕迹 + MCP 注入。
3. 私钥在本地，画像可导出，用户拥有数字身份主权。

**它解决的核心问题**：你在 ChatGPT、Claude、Cursor、浏览器里的记忆和身份都是孤岛；Alpha-ID 用本地 DID + 本机痕迹挖掘 + MCP 注入，让所有工具共享同一个你。

---

## 为什么现在还需要 Alpha-ID

| 场景 | 没有 Alpha-ID | 有 Alpha-ID |
|:-----|:--------------|:------------|
| 换 AI 工具 | 每次都重新自我介绍 | 身份、风格、记忆自动跟着走 |
| 跨平台工作 | ChatGPT 不认识 Claude 历史 | 一个 `did:aid:` 贯穿所有工具 |
| 本机痕迹 | 分散在代码、聊天、浏览器里 | 统一成可解释的人格画像 |
| 数据主权 | 记忆锁在平台服务器 | 私钥在本地，记忆可导出 |
| 面试/展示 | 只有零散功能 demo | 有完整系统叙事和魔法时刻 |

**核心判断**：现在最稀缺的不是“又一个 AI 助理”，而是“属于用户的跨工具连续性层”。

---

## 魔法时刻

> 用户运行 `aid profile mine --path .` 后，看到的不只是一张卡片。
> 他看到的是：系统已经先扫描了他电脑里**实际存在**的痕迹，再按这些痕迹认出他。
> 不会先假设他一定有 ChatGPT / Claude / Cursor，而是先看他**有什么**。

这个瞬间比“又一个导入器”重要，因为它解释了你到底在做一种什么新东西：**不是工具，是数字存在。**

---

## 已完成能力

- **DID 身份层**：本地 Ed25519，`did:aid:`，私钥不离开本机。
- **画像/记忆层**：三层记忆、画像 Schema、来源质量、合并策略。
- **采集器层**：ChatGPT / Claude / Cursor / Trae / Browser / Git 框架已就位。
- **CLI 层**：`aid init`、`aid collect ...`、`aid profile ...` 已有骨架。
- **Web 层**：已有 FastAPI + Web 入口，可继续扩展 3D 宇宙和模拟盘。
- **MCP 层**：已有 profile MCP server 骨架，可继续扩展注入链路。
- **代码结构**：`src/` 下 88 个 Python 文件，统一约束、可继续扩展。

---

## 项目结构

```text
projects/
  src/
    alpha_id/       CLI、采集器、Web、MCP server
    core/           零外部依赖核心：DID、记忆、双大脑、关系/风险
    api/            FastAPI 路由
    auth/           JWT auth
    tools/          桌面自动化工具
    entrypoints/    统一入口：CLI / MCP / API / Daemon
  docs/            核心文档与落地方案
  tests/           自动化测试
```

---

## 路线图

- **V1.0**：完整主链路 + Web 展示 + 模拟盘 MVP + 面试演示。
- **V1.1**：Git/Browser/Trae/Cursor 采集扩展、Web profile API、稳定性修复。
- **V2.0**：双大脑拆分、因果图谱、A2A 轻量接入、语音通路。
- **V3.0**：I2I + A2A 完整闭环、数字遗产、生态标准组件。

---

## 商业价值

- **短期**：开源影响力 + 高端岗位叙事 + 本地主权 AI 顾问方案。
- **中期**：面向重度 AI 用户的订阅能力：备份、同步、高级记忆分析。
- **长期**：成为 A2A / Agent 生态里的“可信身份 + 记忆”标准层；先拿 GitHub 影响力、高端岗位叙事、本地主权 AI 顾问方案落地。

这个项目的价值不只是代码，而是：**谁能先定义“用户数字存在”的标准，谁就能占据下一波 AI 产品的基础设施位。**

---

## License

MIT
