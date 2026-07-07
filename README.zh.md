<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/status-alpha--showcase-ready-purple" alt="Status">
</p>

<h1 align="center">Alpha-ID</h1>

<p align="center">
  <strong>你的数字灵魂。</strong><br>
  不是另一个 AI 助手，而是坐在所有 AI 工具之上的 Ghost Layer：换模型、换平台、换设备，Alpha-ID 不换。
</p>

---

## 30 秒讲清楚

```bash
git clone https://github.com/wenwanqing1217/alpha-id
cd alpha-id/projects
pip install -e ".[dev]"
aid init
aid profile mine --path .
aid profile show
aid profile web
python scripts/demo.py
python scripts/demo.py
```

初始化数字身份 -> 从本机痕迹里认出你 -> Web 端看到你的数字灵魂 -> 所有 AI 工具共用同一个你。

---

## 为什么这个项目还要继续做

| 场景 | 没有 Alpha-ID | 有 Alpha-ID |
|:-----|:--------------|:------------|
| 换 AI 工具 | 每次都重新自我介绍 | 身份、风格、记忆自动跟着走 |
| 跨平台工作 | ChatGPT 不认识 Claude 历史 | 一个 `did:aid:` 贯穿所有工具 |
| 本地痕迹 | 分散在对话、代码、浏览器里 | 统一成可解释的人格画像 |
| 数据主权 | 记忆锁在平台服务器 | 私钥在本地，记忆可导出 |
| 求职/展示 | 只能展示零散功能 | 能展示完整系统与魔法时刻 |

**一句话**：现在缺的不是“又一个个人助理”，而是“属于用户的跨工具连续性层”。

---

## 当前已经具备的能力

- **DID 身份**：本地生成，`did:aid:`，私钥不离开本机。
- **画像与记忆**：三层记忆、画像 Schema、来源质量、合并策略。
- **采集框架**：ChatGPT / Claude / Cursor / Trae / Browser 都已预留。
- **CLI 骨架**：`aid init`、`aid collect ...`、`aid profile ...` 已可继续扩展。
- **Web 入口**：FastAPI + Web 入口已存在，可继续扩展星链宇宙和模拟盘。
- **MCP 骨架**：已有 profile MCP server，可继续扩展自动注入链路。
- **代码结构**：`src/` 下 88 个 Python 文件，约束统一，适合继续扩展。

---

## 魔法时刻

> 用户运行 `aid profile mine --path .` 后，看到的不只是一张画像卡片。
> 他看到的是：系统已经从他的代码、对话、浏览器痕迹里认出了他。

这个瞬间说明你做的不只是工具，而是“数字存在”。

---

## 项目结构

```text
projects/
  src/
    alpha_id/       CLI、采集器、Web、MCP server
    core/           零外部依赖核心：DID、记忆、双大脑、关系/风险
    api/            FastAPI 路由
    auth/           JWT 鉴权
    tools/          桌面自动化工具
    entrypoints/    统一入口：CLI / MCP / API / Daemon
  docs/            核心文档与落地方案
  tests/           自动化测试
```

---

## 路线图

- **V1.0**：完整主链路 + Web 展示 + 模拟盘 MVP + 面试演示。
- **V1.1**：采集扩展、MCP 自动注入、稳定性修复。
- **V2.0**：双大脑拆分、因果图谱、A2A 轻量接入、语音通路。
- **V3.0**：I2I + A2A 完整闭环、数字遗产、生态标准组件。

---

## 商业价值

- **短期**：开源影响力 + 求职/面试叙事 + 本地主权 AI 顾问方案。
- **中期**：面向重度 AI 用户的订阅服务：备份、同步、高级记忆分析。
- **长期**：成为 A2A / Agent 生态里的“可信身份 + 记忆”标准层。

这个项目的价值不只是代码，而是：**谁能先定义“用户数字存在”的标准，谁就能占据下一波 AI 产品的基础设施位。**

---

## License

MIT
