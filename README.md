# alpha-id-zix

<p align="center">
  <a href="https://pypi.org/project/alpha-id-zix/"><img src="https://img.shields.io/pypi/v/alpha-id-zix.svg?logo=pypi&label=PyPI&logoColor=gold" alt="PyPI"></a>
  <a href="https://pypi.org/project/alpha-id-zix/"><img src="https://img.shields.io/pypi/pyversions/alpha-id-zix.svg?logo=python&label=Python&logoColor=gold" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
</p>

---

你在 ChatGPT 里聊了三个月，它已经了解你的表达方式、你的技术栈、你犯过的错。然后你打开 Claude——一切归零。你要重新介绍自己是谁。

这不是不便。这是你的数字存在被碎片化了。

Alpha-ID 是 [Ghost](https://github.com/wenwanqing1217/ghost-showcase) 矩阵的**身份层核心包**。Ghost 是一个 A2A 智能体生态——身份、记忆、Agent 协作、商业闭环。Alpha-ID 为其提供底层身份基础设施。

This package is the identity layer of the [Ghost](https://github.com/wenwanqing1217/ghost-showcase) ecosystem — an A2A agent matrix for identity, memory, collaboration, and commerce.

---

## Quick Start / 快速开始

```bash
pip install alpha-id-zix
aid init                  # Create your DID / 创建数字身份
aid detect                # Scan local data / 扫描本机数据
aid profile show          # View digital profile / 查看数字画像
```

Web 注册分配的 Alpha-ID 格式：`Alpha-{3位随机前缀}-{顺序号}`（例：`Alpha-C82-777`），随机前缀防枚举，顺序号唯一递增。

实名绑定：注册后的人脸核验通过支付宝完成，服务端签发实名凭证写入你的 DID Document。该凭证仅证明"此 DID 已完成实名认证"，不会记录你的身份证号或人脸信息。

```bash
aid collect chatgpt ~/Downloads/chatgpt-data-export.zip
aid profile web
```

启动 API 服务：

```bash
cd projects
python -m src.main          # 默认端口 8000
# 或安装后：aid-api
```

---

## Capabilities / 能力

| Module | EN | CN |
|:-------|:---|:----|
| DID identity | `did:aid` with Ed25519, locally generated | 本地生成的去中心化身份 |
| Dual-chain memory | Encrypted private + plaintext knowledge | 私链加密 + 知识链明文分离 |
| JWT auth | HMAC-SHA256 tokens with revocation | 令牌认证与撤销 |
| Agent SDK | Single `Agent` class for all operations | 一站式 Agent 接口 |
| Agent network | P2P friend system with trace | P2P 好友系统 |
| Skill signing | Package verification & attribution | 技能包签名与验证 |
| Proof of Execution | Verifiable execution records | 可验证的执行记录 |
| Digital profiling | Import from ChatGPT, Claude, Cursor, Trae | 多平台数据采集与画像 |
| REST API | FastAPI-based web service | FastAPI 后端服务 |
| MCP server | Model Context Protocol interface | MCP 协议接入 |
| TwinBrain | Digital entity runtime with state machine | 孪生大脑状态机 |
| AgentLoop | LLM + Tools + Loop, no framework dependency | 纯循环 Agent 引擎 |
| A2A protocol | Agent-to-Agent communication | Agent 间通信协议 |
| Risk engine | Device / behavior / voice 3D scoring | 三维风控评估 |
| GDPR compliance | Data export + right to be forgotten | 数据导出与被遗忘权 |
| Observability | Prometheus metrics + readiness probe | 可观测性指标 |
| **Orchestrator** | Master scheduler with 5 background loops | 总调度器：串联所有模块 |
| **Smart Capture** | Detective not mover — finds contradictions | 智能采集：发现矛盾/卡住/偏离 |
| **Agent Feed** | GitHub/HN/ArXiv/RSS → Agent learning | 资讯采集：Agent 学习养料 |
| **Self Evolution** | Learn lessons, audit preferences | 自进化：从纠正中学习教训 |
| **Obsidian Bridge** | Bidirectional sync with Obsidian vault | Obsidian 双向同步 |
| **NURO Bridge** | Desktop pet ↔ Alpha-ID connection | 桌宠连接：本地+云端 |
| **Feishu Bridge** | Feishu ↔ Alpha-ID + Code Mode | 飞书集成：消息→记忆 + 代码模式（atomcode/zcode/codex） |
| **Tool Orchestrator** | Multi-tool coding orchestration (serial/parallel) | 编程工具协同调度：串行/并行 + 线程池 + TTL 清理 |
| **Codex API** | HTTP wrapper for Codex CLI | Codex CLI HTTP 接口：atomcode/codex 后端 + API Key 认证 |
| **Baidu Map** | Baidu Map AI skill client | 百度地图 AI 技能：地点/路线/天气/地理编码 |
| **MCP Tools** | 24 tools exposing all new capabilities | 24个 MCP 工具 |

---

## Orchestrator CLI / 总调度器

```bash
# 基础启动（Feed + Capture + NURO + Evolution）
python -m alpha_id.orchestrate_cli start

# 完整启用（包括 Obsidian 和飞书）
python -m alpha_id.orchestrate_cli start \
    --obsidian-vault "D:/MyVault" \
    --git-repos "D:/MW,D:/Projects"

# 查看状态 / 单次资讯 / 单次扫描 / NURO 聊天
python -m alpha_id.orchestrate_cli status
python -m alpha_id.orchestrate_cli feed
python -m alpha_id.orchestrate_cli scan
python -m alpha_id.orchestrate_cli chat "你好"
```

---

## API Endpoints / API 端点

服务启动后监听 `:8000`，完整端点参考 [`docs/api-reference.md`](docs/api-reference.md)。

| 模块 | 路径前缀 | 端点数 | 说明 |
|:-----|:---------|:-------|:-----|
| 健康检查 | `/health`, `/ready`, `/metrics` | 3 | 存活/就绪/Prometheus |
| 身份认证 | `/api/v1/identity/*` | 7 | 注册/登录/令牌/设备绑定 |
| 社交网络 | `/api/v1/social/*` | 5 | 好友/消息/请求 |
| 双链记忆 | `/api/v1/dual-chain/*` | 7 | 写入/查询/迁移/删除 |
| Agent 对话 | `/api/v1/agent/*` | 2 | 聊天/状态 |
| 风控评估 | `/api/v1/risk/*` | 2 | 全量评估/声纹验证 |
| GDPR | `/api/v1/gdpr/*` | 2 | 数据导出/删除 |
| 注册流程 | `/api/v1/register/*` | 6 | SMS/人脸/DID 生成 |

Swagger UI: `http://localhost:8000/docs`
ReDoc: `http://localhost:8000/redoc`

---

## Architecture / 架构

详细架构文档见 [`docs/architecture.md`](docs/architecture.md)。

```
alpha-id / 身份层
  DID · JWT · signing · collectors · CLI
  TwinBrain · AgentLoop · A2A · DualChain
  Orchestrator · SmartCapture · AgentFeed
  SelfEvolution · ObsidianBridge · NUROBridge
  FeishuBridge · MCPTools

mindflow-map / 执行层
  workflow engine · intent recognition

zcode-brain / 编排层
  role matching · safety guardrails · task scheduling
```

### 内部模块结构（v0.4.0）

```
src/
├── main.py                  ← FastAPI 入口 + lifespan + 中间件栈
├── api/                     ← HTTP 路由层
│   ├── identity.py          ← /api/v1/identity/*
│   ├── registration.py      ← /api/v1/register/*
│   ├── social.py            ← /api/v1/social/*
│   ├── dual_chain.py        ← /api/v1/dual-chain/*
│   ├── agent.py             ← /api/v1/agent/*
│   ├── risk.py              ← /api/v1/risk/*
│   ├── gdpr.py              ← /api/v1/gdpr/*
│   └── observability.py     ← /ready, /metrics
├── core/                    ← 核心业务逻辑
│   ├── container.py         ← 依赖注入容器（单例 + FastAPI DI）
│   ├── settings.py          ← 统一配置（pydantic-settings）
│   ├── storage.py           ← 存储抽象（ABC + SQLite/Postgres）
│   ├── dual_chain.py        ← 双链记忆隔离（AES-256-GCM）
│   ├── twin_brain.py        ← 孪生大脑状态机 + BrainRegistry
│   ├── agent.py             ← AgentLoop（LLM+Tools+Loop）
│   ├── agent_react.py       ← ReAct 思考引擎
│   ├── a2a.py               ← A2A 协议服务器
│   ├── risk_engine.py       ← 风控评估引擎
│   ├── user_identity.py     ← 用户身份管理
│   ├── alpha_social.py      ← 社交网络管理
│   ├── memory_store.py      ← 记忆存储
│   ├── event_bus.py         ← 事件总线（blinker）
│   ├── orchestrator.py      ← MasterOrchestrator 总调度
│   └── observability.py     ← Prometheus 指标
├── alpha_id/                ← 子包（DID/skill/新模块等）
│   ├── did.py               ← DID 生成/解析/验证
│   ├── signer.py            ← 数字签名 ed25519
│   ├── agent_network.py     ← Agent 网络
│   ├── container.py         ← 应用级依赖容器（lazy init）
│   ├── orchestrator.py      ← 总调度器定义
│   ├── feed.py              ← AgentFeed 资讯采集
│   ├── smart_capture.py     ← SmartCapture 智能采集
│   ├── self_evolution.py    ← SelfEvolution 自进化
│   ├── obsidian_bridge.py   ← ObsidianBridge 双向同步
│   ├── nuro_bridge.py       ← NUROBridge 桌宠连接
│   ├── feishu_bridge.py     ← FeishuBridge 飞书集成
│   ├── mcp_tools.py         ← 18个 MCP 工具
│   ├── orchestrate_cli.py   ← Orchestrator CLI
│   ├── web.py               ← FastAPI Web 应用
│   ├── collectors/          ← 采集器×9
│   ├── mining/              ← 挖矿扫描
│   └── *_cli.py             ← 各类 CLI 工具
├── auth/                    ← 认证与安全
│   ├── jwt.py               ← JWT 签发/验证/轮换
│   ├── csrf.py              ← CSRF 防护中间件
│   ├── middleware.py         ← require_user 依赖
│   └── token_store.py       ← 令牌撤销存储
├── entrypoints/             ← 入口点（CLI/MCP/daemon）
└── tools/                   ← 工具集
```

---

## Configuration / 配置

通过环境变量或 `.env` 文件配置。完整列表见 [`docs/architecture.md`](docs/architecture.md)。

| 变量 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `AUTH_MASTER_KEY` | *(必填)* | JWT 签名主密钥 |
| `LLM_API_KEY` | *(可选)* | LLM API 密钥（兼容 OPENAI_API_KEY） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM 端点 |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `DATABASE_URL` | *(可选)* | PostgreSQL 连接（空则用 SQLite） |
| `STORAGE_BACKEND` | *(自动)* | `sqlite` 或 `postgres` |
| `A2A_ENABLED` | `true` | 是否启动 A2A 服务器 |
| `A2A_PORT` | `9001` | A2A 服务端口 |
| `RATE_LIMIT_ENABLED` | `true` | 是否启用限流 |
| `RATE_LIMIT_RPM` | `60` | 每分钟请求数限制 |
| `CORS_ORIGINS` | `http://localhost:3000,...` | 允许的跨域来源 |
| `OBSIDIAN_VAULT` | *(可选)* | Obsidian 笔记库路径 |
| `FEISHU_APP_ID` | *(可选)* | 飞书 App ID |
| `FEISHU_APP_SECRET` | *(可选)* | 飞书 App Secret |
| `GITHUB_TOKEN` | *(可选)* | GitHub API Token（提高速率限制） |

---

## Development / 开发

```bash
git clone https://github.com/wenwanqing1217/alpha-id.git
cd alpha-id/projects
pip install -e ".[dev]"
pytest tests/ -v --noconftest
```

运行单个测试文件：

```bash
pytest tests/test_registration.py -v --noconftest
```

---

## Documentation / 文档

| 文档 | 说明 |
|:-----|:-----|
| [`docs/architecture.md`](docs/architecture.md) | 内部架构深潜（DI 容器、双链记忆、TwinBrain、AgentLoop、A2A、中间件栈） |
| [`docs/api-reference.md`](docs/api-reference.md) | 全部 API 端点参考（请求/响应/认证） |
| [`docs/EXPERT_AUDIT_2026-07-27.md`](docs/EXPERT_AUDIT_2026-07-27.md) | 专家级项目审计报告 |

---

## License / 许可证

[MIT](LICENSE)

---

<p align="center">
  <a href="https://pypi.org/project/alpha-id-zix/">PyPI</a> · <a href="https://github.com/wenwanqing1217/alpha-id">GitHub</a>
</p>
