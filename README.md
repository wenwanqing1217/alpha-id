# Alpha-ID — 你的数字灵魂

[![PyPI version](https://img.shields.io/pypi/v/alpha-id-zix.svg)](https://pypi.org/project/alpha-id-zix/)
[![Python](https://img.shields.io/pypi/pyversions/alpha-id-zix.svg)](https://pypi.org/project/alpha-id-zix/)
[![License](https://img.shields.io/pypi/l/alpha-id-zix.svg)](https://github.com/wenwanqing1217/alpha-id/blob/main/LICENSE)
[![Tests](https://img.shields.io/badge/tests-928%20passing-brightgreen.svg)](https://github.com/wenwanqing1217/alpha-id)
[![Coverage](https://img.shields.io/badge/coverage-68%25-blue.svg)](https://github.com/wenwanqing1217/alpha-id)

> **让每个 AI Agent 都认识你是谁。**

Alpha-ID 是 [Ghost](https://github.com/wenwanqing1217) 矩阵的**身份层核心包**。当越来越多的 AI 工具涌现，每次使用新工具都像遇到陌生人 —— 你要重新介绍自己、重新解释需求、重新建立偏好。Alpha-ID 终结这件事：**一次注册，所有 Agent 都认识你**。

Ghost 是坐在所有 AI 工具之上的 **Ghost Layer** — 一个 AI Agent 应用矩阵。Alpha-ID 是其身份基础设施，所有上层应用都依赖它。

---

## ✨ 特性

| 模块 | 说明 |
|------|------|
| 🆔 **DID 身份** | 去中心化标识符 `did:aid`，纯 Python 实现 Ed25519，零外部依赖 |
| 🧠 **记忆双链** | 行为链 + 偏好链，让 Agent 真正"记住"你 |
| 🔐 **JWT 认证** | 基于主密钥的身份验证与 Token 防护 |
| 🤖 **Agent SDK** | 一站式 `Agent` 类：注册、登录、社交、思考 |
| 🔗 **Agent 网络** | P2P 好友系统 + 调用链追踪 |
| ✍️ **技能签名** | 技能包签名/验证 + 归属追踪 + 注册表 |
| 📜 **执行证明** | Proof of Execution — 可验证的执行记录 |
| 📊 **数字画像** | 从 ChatGPT / Claude / Trae / Cursor / 浏览器 采集痕迹，生成你的数字画像 |
| 🌐 **Web API** | FastAPI 服务，RESTful 接口 |
| 🔌 **MCP Server** | Model Context Protocol 接入 |
| 🖥️ **CLI 工具** | `aid` 命令行 — 扫描、采集、画像、社交、技能 |

---

## 🚀 快速开始

### 安装

```bash
pip install alpha-id
```

可选功能组：

```bash
pip install alpha-id[web]      # Web API 服务
pip install alpha-id[mcp]      # MCP Server
pip install alpha-id[fairy]    # AI 自动化（OpenAI + PyAutoGUI）
```

### CLI — 把你的数字痕迹收回来

```bash
# 初始化数字身份
aid init

# 扫描本机有哪些数据可以采集
aid detect

# 从 ChatGPT 导出导入
aid collect chatgpt ~/Downloads/chatgpt-export.zip

# 从 Trae 取回代码痕迹
aid collect trae

# 查看你的数字画像
aid profile show

# 浏览器查看画像卡片
aid profile web

# 3 个问题快速生成画像
aid wizard start
```

### SDK — 代码中构建有身份的 Agent

```python
from alpha_id import Agent

agent = Agent()
agent.register("my-device-fingerprint")  # 注册身份
agent.connect("Alpha-002")               # 加好友
agent.think("来聊天吧")                   # TwinBrain 自主思考
```

### Web API — 启动服务

```bash
pip install alpha-id[web]
export AUTH_MASTER_KEY="your-random-key-here"
aid-api --reload --port 8000
```

### MCP Server — 接入 AI 工具链

```bash
pip install alpha-id[mcp]
aid-mcp
```

---

## 📐 Ghost 矩阵架构

```
┌─────────────────────────────────────────────┐
│          AI Agent 应用矩阵（建设中）            │
│   电商 · 内容 · 办公 · 社交 · 出行 · 更多      │
├─────────────────────────────────────────────┤
│              执行层 — mindflow-map           │
│       工作流引擎 · LLM 意图识别 · 多平台接入    │
├─────────────────────────────────────────────┤
│              编排层 — zcode-brain            │
│         角色匹配 · 安全护栏 · 任务调度          │
├─────────────────────────────────────────────┤
│              身份层 — alpha-id  ← 本包        │
│       DID · 记忆双链 · JWT · Token 经济        │
└─────────────────────────────────────────────┘
```

---

## 📦 数据采集器

从以下平台回收你的数字痕迹：

| 数据源 | 命令 | 说明 |
|--------|------|------|
| ChatGPT | `aid collect chatgpt <zip>` | 从 OpenAI 导出导入 |
| Claude | 自动检测 | Claude 对话记录 |
| Trae | `aid collect trae` | 代码痕迹 |
| Cursor | 自动检测 | 编辑器行为 |
| 浏览器 | 自动检测 | 浏览历史与偏好 |
| Git | 自动检测 | 代码提交记录 |

---

## 🛠️ 开发

```bash
git clone https://github.com/wenwanqing1217/alpha-id.git
cd alphaid/projects
pip install -e ".[dev]"
pytest tests/ -q
```

### 项目结构

```
src/
├── alpha_id/          # 核心 SDK
│   ├── agent.py       # Agent 一站式入口
│   ├── did.py         # DID 身份（Ed25519）
│   ├── signer.py      # 签名/验签
│   ├── skill_signer.py# 技能签名与归属
│   ├── poe.py         # 执行证明
│   ├── collectors/    # 数据采集器
│   └── ...
├── api/               # FastAPI 路由
├── auth/              # JWT 认证
├── core/              # 核心引擎（TwinBrain、记忆双链）
├── entrypoints/       # CLI/MCP/API 入口
└── feishu_bot/        # 飞书机器人
```

---

## 📦 Ghost 项目矩阵

| 项目 | 定位 | 技术栈 | 状态 |
|------|------|--------|------|
| **alpha-id**（本包） | 身份层 — DID + 记忆 + JWT | Python + FastAPI | PyPI 已发布 |
| [mindflow-map](https://github.com/wenwanqing1217/mindflow-map) | 执行层 — 工作流引擎 | Python + FastAPI | 可用 |
| [zcode-brain](https://github.com/wenwanqing1217/zcode-brain) | 编排层 — 角色匹配 + 护栏 | TypeScript | 可用 |
| [mindflow](https://github.com/wenwanqing1217/mindflow) | 前端门户 — AI 控制台 | Next.js | 可用 |

---

## 📄 许可证

[MIT](https://github.com/wenwanqing1217/alpha-id/blob/main/LICENSE)

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/wenwanqing1217">wenwanqing1217</a> — Ghost Layer sitting on top of all AI tools.</sub>
</p>
