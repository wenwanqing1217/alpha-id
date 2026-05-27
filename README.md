# Alpha-ID: 数字身份智能管理系统

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 面向 AI Agent 的数字身份与风控系统。为每个用户生成唯一数字身份（Alpha-ID），
> 通过多维度风险评估、跨设备同步、社交网络和 JWT 认证，构建可信的 AI 交互身份层。

---

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI Layer                     │
│  /register  /login  /refresh  /me  /evaluate  ...   │
│  ┌──────────────────────────────────────────────┐   │
│  │           Auth Middleware (JWT)               │   │
│  │  require_user() / optional_user()             │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│               Core Business Logic                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ Identity │ │  Social  │ │   Risk   │ │  Auth  │ │
│  │ Manager  │ │ Manager  │ │  Engine  │ │ (JWT)  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┘ │
├───────┴────────────┴────────────┴───────────────────┤
│              Storage Abstraction                     │
│         JSON File (dev) / PostgreSQL (prod)          │
└─────────────────────────────────────────────────────┘
```

### 设计原则

| 层级 | 职责 | 外部依赖 |
|---|---|---|
| **FastAPI** | HTTP 路由、请求/响应序列化 | fastapi, pydantic, uvicorn |
| **auth/** | JWT 签发、验证、中间件 | **零依赖（纯标准库）** |
| **core/** | 身份、社交、风控业务逻辑 | **零依赖** |
| **storage/** | JSON / PostgreSQL 存储抽象 | psycopg2 (可选) |

核心设计理念：**依赖向内**。`core/` 和 `auth/` 层零外部依赖，可独立测试、可嵌入任何框架。

---

## 认证系统

使用 **HMAC-SHA256** 自研 JWT 实现，不依赖 `PyJWT` 等第三方库。

| 令牌类型 | 有效期 | 用途 |
|---|---|---|
| `access_token` | 30 分钟 | API 请求认证（`Authorization: Bearer <token>`）|
| `refresh_token` | 7 天 | 换取新的 access_token |

```
POST /api/v1/identity/login    →  { access_token, refresh_token }
POST /api/v1/identity/refresh  →  新 access_token
GET  /api/v1/identity/me       →  当前用户信息（需 Bearer）
```

环境变量配置（可选，不设置时使用开发密钥）：

```bash
export AUTH_MASTER_KEY="your-256-bit-secret-here"
export JWT_ACCESS_EXPIRE_MINUTES=30
export JWT_REFRESH_EXPIRE_DAYS=7
```

---

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/alpha-id.git
cd alpha-id

# Python 3.12+ 推荐
pip install -e ".[dev]"

# 或者使用 uv（更快）
pip install uv
uv sync
```

### 运行测试

```bash
# 全部测试（核心模块 + JWT 认证）
pytest tests/ -v

# 仅核心模块（零依赖，纯 Python）
pytest tests/test_user_identity.py tests/test_alpha_social.py tests/test_risk_assessment.py -v

# 仅 JWT 认证（零依赖）
pytest tests/test_auth.py -v

# 仅 API 集成测试（需要 FastAPI）
pytest tests/test_api.py -v

# 带覆盖率
pytest tests/ --cov=src --cov-report=term-missing
```

### 启动服务

```bash
# 开发模式（热重载）
uvicorn src.main:app --reload --port 8000

# 生产模式
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker 部署

```bash
# 构建并启动
docker compose up --build

# 运行测试
docker compose -f docker-compose.yml run test
```

---

## API 参考

### 公开端点（无需认证）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/identity/register` | 用户注册（设备指纹绑定） |
| GET | `/api/v1/identity/stats/overview` | 系统统计概览 |
| POST | `/api/v1/risk/evaluate` | 风险评估 |

### 认证端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/identity/login` | 登录，返回 JWT 令牌对 |
| POST | `/api/v1/identity/refresh` | 刷新 access_token |

### 受保护端点（需 `Authorization: Bearer <token>`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/identity/me` | 当前用户信息 |
| GET | `/api/v1/identity/{alpha_id}` | 用户档案 |
| POST | `/api/v1/identity/{alpha_id}/devices` | 绑定新设备 |
| POST | `/api/v1/identity/{alpha_id}/sync` | 跨设备同步 |
| POST | `/api/v1/identity/{alpha_id}/session` | 记录会话 |

### 社交网络（公开）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/social/friend-request` | 发送好友请求 |
| PUT | `/api/v1/social/friend-request/{id}` | 接受/拒绝请求 |
| GET | `/api/v1/social/{alpha_id}/friends` | 好友列表 |
| GET | `/api/v1/social/{alpha_id}/requests` | 待处理请求 |
| POST | `/api/v1/social/message` | 发送消息 |
| GET | `/api/v1/social/{alpha_id}/messages` | 消息列表 |

---

## 项目结构

```
alpha-id/
├── src/
│   ├── api/                    # FastAPI 路由层
│   │   ├── identity.py         #   身份 API
│   │   ├── social.py           #   社交 API
│   │   ├── risk.py             #   风控 API
│   │   └── models.py           #   Pydantic 请求/响应模型
│   │
│   ├── auth/                   # JWT 认证（纯标准库）
│   │   ├── jwt.py              #   令牌签发/验证
│   │   └── middleware.py        #   FastAPI 依赖注入
│   │
│   ├── core/                   # 核心业务逻辑（零外部依赖）
│   │   ├── user_identity.py    #   用户身份管理器
│   │   ├── alpha_social.py     #   社交网络管理器
│   │   ├── risk_engine.py      #   风险评估引擎
│   │   ├── storage.py          #   JSON 存储实现
│   │   └── storage_postgres.py #   PostgreSQL 存储实现
│   │
│   ├── tools/                  # LangChain 工具层
│   │   ├── agent_social_tool.py
│   │   ├── user_identity_tool.py
│   │   └── risk_assessment_tool.py
│   │
│   └── main.py                 # FastAPI 应用入口
│
├── tests/                      # 测试套件
│   ├── test_user_identity.py   #   身份核心（10 ✅）
│   ├── test_alpha_social.py    #   社交核心（14 ✅）
│   ├── test_risk_assessment.py #   风控核心（11 ✅）
│   ├── test_auth.py            #   JWT 认证（31 ✅）
│   └── test_api.py             #   API 集成测试（35 ✅）
│
├── assets/                     # 默认 JSON 数据目录
├── scripts/                    # 工具脚本
├── Dockerfile                  # 生产镜像
├── Dockerfile.test             # 测试镜像
├── docker-compose.yml          # 容器编排
└── .github/workflows/ci.yml    # CI 流水线
```

---

## 测试矩阵

### 当前状态：101 个测试 ✅ 全部通过

| 套件 | 文件 | 数量 | 依赖 | 类型 |
|---|---|---|---|---|
| 用户身份核心 | `test_user_identity.py` | 10 | 无 | 单元 |
| 社交网络核心 | `test_alpha_social.py` | 14 | 无 | 单元 |
| 风控引擎核心 | `test_risk_assessment.py` | 11 | 无 | 单元 |
| JWT 认证 | `test_auth.py` | 31 | 无 | 单元 |
| API 集成 | `test_api.py` | 35 | FastAPI | 集成 |
| **合计** | | **101** | | |

> **核心模块（66 个测试）纯 Python 标准库即可运行，无需任何第三方依赖。**

### 测试覆盖率

```
Name                             Stmts   Miss  Cover
----------------------------------------------------
src/auth/__initutes.py              25      0   100%
src/auth/jwt.py                    171      0   100%
src/auth/middleware.py              36      0   100%
src/core/user_identity.py          182      8    96%
src/core/alpha_social.py           170     12    93%
src/core/risk_engine.py            176     25    86%
----------------------------------------------------
TOTAL                              760     45    94%
```

---

## 环境要求

| 组件 | 要求 | 备注 |
|---|---|---|
| Python | 3.12+ | 3.14 需要 Visual C++ Redistributable |
| FastAPI | 0.110+ | 仅 API 层需要 |
| pydantic | 2.0+ | 仅 API 层需要 |
| 操作系统 | Windows / macOS / Linux | 跨平台 |

> **Windows 注意事项**：Python 3.14 上 `pydantic-core` 需要 Visual C++ Redistributable 2015-2022。
> 如遇 DLL 加载问题，降级到 Python 3.12 即可解决。

---

## 存储后端切换

```python
# JSON 文件（开发环境）
from core.storage import JsonStorage
storage = JsonStorage("assets/alpha_id_users.json")
manager = UserIdentityManager(storage=storage)

# PostgreSQL（生产环境）
from core.storage_postgres import PostgresStorage
storage = PostgresStorage("postgresql://user:pass@host:5432/aid")
manager = UserIdentityManager(storage=storage)
```

---

## 技术亮点

1. **纯标准库 JWT**：HMAC-SHA256 自实现，不依赖 `PyJWT` / `PyCryptodome`，零外部依赖
2. **分层解耦**：`core/` 和 `auth/` 不依赖 FastAPI / pydantic，可独立运行和测试
3. **多重风控**：设备指纹、硬件匹配、行为分析、声纹置信度加权评分
4. **存储抽象**：`StorageBackend` 接口，JSON ↔ PostgreSQL 一键切换
5. **防御性设计**：令牌类型分离（access vs refresh）、过期验证、异常场景全覆盖

---

## 路线图

- [x] 核心业务逻辑解耦（身份、社交、风控 → core/）
- [x] 存储抽象层（JSON / PostgreSQL 可切换）
- [x] bcrypt 密码加密
- [x] **JWT 认证系统（零依赖实现）**
- [x] **FastAPI REST API**
- [x] **Docker 容器化部署**
- [x] **CI 自动化流水线**
- [ ] Graph 知识图谱可视化
- [ ] 声纹识别集成
- [ ] 性能基准测试
- [ ] WebSocket 实时消息推送
