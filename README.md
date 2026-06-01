# AID — Agent Identity Layer

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-525-passing-green.svg)](tests/)

> **身份优先、协议驱动的 Agent 生态层。**  
> 任何 Agent 框架、任何模型都能接入的身份层——技能签名可验证、作者信誉可追溯、执行证明可审计。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **DID 身份** | `did:aid:` 方法，Ed25519 密钥对，W3C DID Document 兼容 |
| **Agent 大脑** | TwinBrain — LLM + Tools + Loop，ReAct 引擎，多状态管理 |
| **技能 SDK** | 签名/验签、注册表管理、吊销列表、运行时执行 |
| **信誉图谱** | Skill 归因追踪、作者信誉评分（使用量 × 成功率 × 覆盖面）|
| **执行证明** | Ed25519 签名的 PoE 记录，链式调用追溯 |
| **去中心化仓库** | Git-based 技能发现、自托管仓库协议 |
| **多 Agent 协作** | DID 互认证、技能调用链、多方 PoE 聚合 |
| **Web 演示** | FastAPI + Vue 3 前端，聊天式 Agent 交互 |

---

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/aid.git
cd projects

# 使用虚拟环境
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -e ".[dev]"
```

### 运行测试

```bash
pytest tests/ -q
# 525 passed ✅
```

### CLI 快速体验

```bash
# 1. 创建身份
aid identity init

# 2. 查看身份
aid identity show

# 3. 创建并签名技能
echo "def main(p): return f'Hello, {p.get(\"name\", \"World\")}'" > greet.py
aid skill sign greet.py --name greet --register

# 4. 运行技能
aid skill run greet '{"name": "Alice"}'
# → Hello, Alice

# 5. 查看归因统计
aid skill stats leaderboard

# 6. 启动 Web 演示
uvicorn src.alpha_id.web:app --port 8000
# → http://localhost:8000
```

---

## 桌面精灵（AID Desktop Fairy）

> 桌面悬浮球助手 — 截图 / OCR / 窗口控制，一句指令搞定。

![demo](https://img.shields.io/badge/demo-Tkinter-blueviolet)

```bash
# 启动（确保装了依赖）
pip install pyautogui pygetwindow Pillow pytesseract
python src/aid_daemon.py
```

**效果：** 桌面右上角暗色磨砂玻璃球。  
**用法：** 双击输指令 · 右键菜单 · 拖拽移动

| 指令 | 效果 |
|------|------|
| `看屏幕` / `截图` | 截屏并 OCR 识别文字 |
| `窗口列表` | 列出所有窗口标题 |
| `鼠标位置` | 显示当前鼠标坐标 |
| `点击 500 300` | 模拟点击指定坐标 |
| `输入 你好世界` | 在当前窗口打字 |

**启动脚本：** `scripts/aid_daemon.bat`（双击即可启动）

---

## 架构

```
┌────────────────────────────────────────────────────────┐
│                    SDK (alpha_id)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐   │
│  │  Agent   │ │Container │ │    DID + Signer      │   │
│  │ (入口)   │ │ (DI容器) │ │ (身份/签名/验签)      │   │
│  └────┬─────┘ └────┬─────┘ └──────────┬───────────┘   │
│       │            │                  │               │
│  ┌────┴────────────┴──────────────────┴───────────┐   │
│  │              Core Layer (零外部依赖)             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐   │   │
│  │  │ TwinBrain│ │ AgentLoop│ │ ReActEngine  │   │   │
│  │  │ (大脑)   │ │ (LLM循环) │ │ (思考引擎)    │   │   │
│  │  └────┬─────┘ └────┬─────┘ └──────┬───────┘   │   │
│  │  ┌────┴────────────┴────────────────┐         │   │
│  │  │ MemoryStore | Social | Risk      │         │   │
│  │  └──────────────────────────────────┘         │   │
│  └───────────────────────────────────────────────┘   │
│                                                       │
│  ┌───────────────────────────────────────────────┐   │
│  │         Skill System (P2/P3)                  │   │
│  │  sign → register → execute → attribute → PoE  │   │
│  │  ↑ revoke ↗ reputation ↗ chain ↗ aggregate    │   │
│  └───────────────────────────────────────────────┘   │
│                                                       │
│  ┌───────────────────────────────────────────────┐   │
│  │         Decentralized Protocol (P3)           │   │
│  │  DIDResolver → SkillRepository → AgentNetwork │   │
│  └───────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────┤
│  CLI (typer)              │  Web (FastAPI + Vue 3)   │
└──────────────────────────────────────────────────────┘
```

### 设计原则

- **依赖向内**: `core/` 层零外部依赖，可嵌入任何框架
- **身份优先**: 所有能力围绕 DID 身份层组织
- **不造框架，只造桥**: Skill 可运行在 Claude Code / Cursor / OpenClaw 上
- **简单 = 有效**: Agent = LLM + Tools + Loop，不要复杂框架

---

## CLI 命令

### 身份管理

| 命令 | 说明 |
|------|------|
| `aid identity init` | 生成 DID + Ed25519 密钥对 |
| `aid identity show` | 查看当前 DID Document |
| `aid identity export` | 导出加密身份 Bundle |
| `aid identity import <file>` | 导入身份 Bundle |
| `aid identity sign <file>` | 用身份签名文件 |
| `aid identity verify <file>` | 验证文件签名 |

### 技能管理

| 命令 | 说明 |
|------|------|
| `aid skill sign <file> --name <name>` | 签名技能并注册 |
| `aid skill verify <file> <package>` | 验签技能 |
| `aid skill list` | 列出已注册技能 |
| `aid skill info <name>` | 技能详情 |
| `aid skill run <name> [params]` | 执行技能（自动归因）|
| `aid skill revoke <name>` | 吊销技能 |
| `aid skill stats leaderboard` | 作者信誉排行榜 |

### 大脑控制

| 命令 | 说明 |
|------|------|
| `aid brain awake` | 唤醒大脑 |
| `aid brain sleep` | 休眠大脑 |
| `aid brain think` | 主动思考 |
| `aid brain status` | 查看大脑状态 |

---

## Python SDK 示例

```python
from alpha_id import Agent, AIDSigner
from alpha_id.skill_signer import sign_skill, SkillRegistry, SkillRuntime

# ── 创建 Agent ──
agent = Agent()
result = agent.identify("my-device-fp")
print(f"Welcome, {result['alpha_id']}")

# ── 签名并注册技能 ──
signer = AIDSigner()
signer.generate()

pkg = sign_skill("greet.py", signer, name="greet", version="1.0.0")
registry = SkillRegistry()
registry.register(pkg, content=open("greet.py", "rb").read())

# ── 执行技能 ──
runtime = SkillRuntime(registry)
result = runtime.execute("greet", '{"name": "World"}', executor_did=signer.did)
print(result)

# ── 多 Agent 协作 ──
from alpha_id.agent_network import AgentNetwork

network = AgentNetwork(local_signer, registry=registry)
network.register_peer(peer_did, public_key_hex=peer_pk)
result = network.call_skill(peer_did, "greet", {"name": "Alice"})
chain = network.get_call_chain(result["poe_id"])
print(chain.summary())
```

---

## 测试矩阵

### 当前：525 tests ✅

| 模块 | 测试数 | 覆盖内容 |
|------|--------|---------|
| 身份核心 | 10 | 注册、设备绑定、统计 |
| 社交网络 | 14 | 好友、消息、请求 |
| 风控引擎 | 11 | 设备/行为/声纹评分 |
| JWT 认证 | 31 | 签发、验证、刷新 |
| Agent / ReAct | 35 | AgentLoop、ReAct 引擎 |
| TwinBrain | 85 | 状态机、消息路由、思考周期 |
| DID / 签名 | 17 | 密钥生成、签名验签、Document |
| 记忆存储 | 8 | 保存、查询、语义搜索 |
| 信誉积分 | 8 | 评分计算、持久化 |
| PoE 证明 | 15 | 生成、验证、存储、查询 |
| Skill 签名 | 57 | 签名、验签、注册表、运行时 |
| 归因追踪 | 8 | 执行记录、作者统计 |
| CLI | 12 | identity / skill / brain 子命令 |
| Web 演示 | 17 | 登录、聊天、大脑控制 |
| API 集成 | 35 | 身份/社交/风控 API |
| E2E 集成 | 60+ | Skill 生命周期、PoE、Agent 协作 |
| **合计** | **525** | |

---

## 三阶段路线图

```
2.7 ── Phase 1 ── 3.5 ── Phase 2 ── 4.0 ── Phase 3 ── 4.5
      (身份地基)         (信誉网络)         (身份自治)
```

| 阶段 | 状态 | 主题 |
|------|------|------|
| **Phase 1: 身份地基** | ✅ 100% | DID 身份、TwinBrain、AgentLoop、Web 演示 |
| **Phase 2: 信誉网络** | ✅ 80% | Skill 签名验证、归因追踪、信誉图谱 |
| **Phase 3: 身份自治** | ✅ 75% | PoE 执行证明、去平台化仓库、多 Agent 协作 |

---

## 许可证

MIT
