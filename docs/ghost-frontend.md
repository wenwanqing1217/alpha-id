# Ghost.html 前端 — 技术文档

> **版本 2.0** | **2026-07-27**
> **Web 展示层 — 单文件 2,515 行前端 + 969 行 JavaScript**

---

## 目录

1. [定位与架构](#1-定位与架构)
2. [文件结构](#2-文件结构)
3. [两视图架构](#3-两视图架构)
4. [API 调用清单](#4-api-调用清单)
5. [注册流程前端实现](#5-注册流程前端实现)
6. [依赖与技术栈](#6-依赖与技术栈)
7. [主要 JavaScript 函数](#7-主要-javascript-函数)
8. [视图切换机制](#8-视图切换机制)
9. [样式系统](#9-样式系统)

---

## 1. 定位与架构

Ghost.html 是 Ghost 项目的 **Web 展示层**，不是主入口。它提供：

- **首页展示**: 愿景、核心概念、路线图
- **A2A 生态区** (workbenchView): 意图解析、Skill路由、决策树、记忆图谱、Agent广场、豆包桥
- **Mindflow 协作台** (mindflowView): 思维画布、任务看板、笔记库、人格画像
- **注册/登录**: 手机号→短信→人脸→DID 完整流程

### 在 Ghost 生态中的位置

```
Ghost.html (浏览器)
    │
    ├─ fetch(GATEWAY_URL + '/v1/human/*')
    │
    ▼
Gateway :18080
    │
    ├─ Alpha-ID :8000 (身份/记忆/AgentLoop)
    ├─ Nebula :2002 (工作流/地图)
    └─ Flow :3036 (注册链路/Computer Use)
```

---

## 2. 文件结构

| 文件 | 行数 | 职责 |
|:-----|:----:|:-----|
| `ghost.html` | 2,515 | 单文件 HTML — 结构+样式+内联脚本 |
| `ghost.css` | — | TailwindCSS 编译产物 |
| `ghost.js` | 969 | 前端逻辑 — 精灵互动+注册+API调用 |

### 目录布局

```
alphaid/projects/src/alpha_id/templates/
├── ghost.html    (2,515L 主文件)
├── ghost.css     (TailwindCSS 编译)
└── ghost.js      (969L JavaScript)
```

---

## 3. 两视图架构

Ghost.html 采用**两视图架构**，通过 `view-panel` 类切换显示：

### 视图清单

| 视图 ID | 名称 | 内容 | 入口 |
|:---------|:-----|:-----|:-----|
| `homepageView` | 首页 | 愿景、概念、路线图、Hero | 默认加载 |
| `workbenchView` | A2A 生态区 | 意图解析、Skill路由、决策树、记忆图谱、Agent广场、豆包桥 | 注册后/点击"已登录" |
| `mindflowView` | Mindflow 协作台 | 思维画布、任务看板、笔记库、人格画像 | 点击"协作模式" |

### 视图切换函数

```javascript
function showHomepage()    // 显示首页
function showWorkbench()   // 显示 A2A 生态区
function showMindflow()    // 显示 Mindflow 协作台
```

---

## 4. API 调用清单

### 注册链路 (Gateway 代理到 Alpha-ID)

| 步骤 | 方法 | URL | 后端 |
|:-----|:-----|:----|:-----|
| 发送短信 | POST | `/v1/register/send-sms` | alphaid :8000 |
| 验证短信 | POST | `/v1/register/verify-sms` | alphaid :8000 |
| 人脸核身 | POST | `/v1/register/face-verify` | alphaid :8000 |
| 生成 DID | POST | `/v1/register/generate-did` | alphaid :8000 |
| 完成注册 | POST | `/v1/register/complete` | alphaid :8000 |

### 仪表盘数据

| 功能 | 方法 | URL | 说明 |
|:-----|:-----|:----|:-----|
| 身份信息 | GET | `/v1/identity` | 当前 Alpha-ID 身份 |
| 双链记忆统计 | GET | `/api/v1/dual-chain/stats` | 直接调 Alpha-ID |
| 健康检查 | GET | `/health` | Gateway 三后端健康 |
| 记忆搜索 | GET | `/v1/memory/search?keyword=` | 知识查询 |
| 记忆图谱 | GET | `/v1/memory/graph` | 知识图谱数据 |
| 服务健康 | GET | `/:port/health` | 各服务健康检查 |

### 服务端口

| 服务 | 端口 | 检测 URL |
|:-----|:----:|:---------|
| Alpha-ID | 8000 | `http://localhost:8000/api/health` |
| Gateway | 18080 | `http://localhost:18080/v1/internal/health` |
| Nebula | 2002 | `http://localhost:2002/health` |
| Orchestrator | 19090 | `http://localhost:19090/health` |
| Flow | 3036 | `http://localhost:3001/health` |

---

## 5. 注册流程前端实现

### 四步注册流程

```
Step 1: 手机号 → 发送短信验证码
    ↓
Step 2: 手机号验证成功 (显示 ✓)
    ↓
Step 3: 支付宝人脸核身 (扫码或跳转)
    ↓
Step 4: Alpha-ID 开通成功 (显示 DID)
```

### 前端状态

| 元素 | ID | 作用 |
|:-----|:-----|:-----|
| 手机号输入 | `reg-phone` | 输入手机号 |
| 短信验证码输入 | `reg-sms-input` | 输入验证码 |
| 发送短信按钮 | `reg-send-sms-btn` | 触发 sendSMSCode() |
| 下一步按钮 | `reg-step1-btn` | 触发 verifySMS() |
| 人脸核身按钮 | `reg-face-btn` | 触发 startFaceVerify() |
| DID 显示 | `reg-did-result` | 显示生成的 DID |
| 步骤指示器 | `step-dot-1` ~ `step-dot-4` | 当前步骤高亮 |

### 关键函数

```javascript
function sendSMSCode()
    // POST /v1/register/send-sms {phone}

function verifySMS()
    // POST /v1/register/verify-sms {phone, code}
    // 成功 → goToStep(2) → startFaceVerify()

function startFaceVerify()
    // POST /v1/register/face-verify {phone, session_id}
    // 成功 → generateAndCompleteDID()

function generateAndCompleteDID()
    // POST /v1/register/generate-did {phone, name}
    // POST /v1/register/complete {phone, did, face_token}
    // 成功 → goToStep(4) → 显示 DID

function finishRegistration()
    // 关闭模态框 → showWorkbench()

function skipFaceVerify()
    // 跳过人脸步骤（测试用）
```

---

## 6. 依赖与技术栈

### 技术栈

| 类别 | 技术 | 说明 |
|:-----|:-----|:-----|
| CSS 框架 | TailwindCSS (编译) | utility-first，暗色主题 |
| JavaScript | 原生 JS (无框架) | 无 React/Vue，直接 DOM 操作 |
| 字体 | Inter / JetBrains Mono | 系统字体 + 等宽字体 |
| 图标 | 内联 SVG | 无外部图标库 |
| 动画 | CSS Animation + JS | IntersectionObserver 滚动显现 |

### 外部依赖

| 依赖 | 来源 | 用途 |
|:-----|:-----|:-----|
| TailwindCSS | CDN 或本地编译 | 样式框架 |
| 无其他外部依赖 | — | 纯原生实现 |

### 配置常量

```javascript
const GATEWAY_URL = 'http://localhost:18080';
const ALPHAID_URL = 'http://localhost:8000';
```

---

## 7. 主要 JavaScript 函数

### 精灵互动系统 (ghost.js)

| 函数 | 行号 | 作用 |
|:-----|:----:|:-----|
| `showBubble(category)` | 41 | 显示互动气泡 |
| `createRipple(x, y)` | 85 | 点击涟漪效果 |
| `resetIdleTimer()` | 204 | 重置空闲计时器 |
| `animate()` | 279 | 主动画循环 |
| `generateDid()` | 336 | 生成测试 DID |
| `generateRandomHex(len)` | 327 | 随机十六进制 |

### 注册流程

| 函数 | 行号 | 作用 |
|:-----|:----:|:-----|
| `resetRegistration()` | 399 | 重置注册状态 |
| `goToStep(step)` | 416 | 切换到指定注册步骤 |
| `sendSMSCode()` | ~445 | 发送短信验证码 |
| `verifySMS()` | ~499 | 验证短信码 |
| `startFaceVerify()` | ~536 | 启动人脸核身 |
| `generateAndCompleteDID()` | ~575 | 生成 DID 并完成注册 |

### 仪表盘

| 函数 | 行号 | 作用 |
|:-----|:----:|:-----|
| `fetchDashboard()` | ~735 | 拉取仪表盘数据 |
| `renderGraph()` | ~907 | 渲染记忆图谱 SVG |
| `showNodeDetail(d)` | ~954 | 显示节点详情 |

---

## 8. 视图切换机制

### 视图切换函数

```javascript
function showHomepage() {
    document.getElementById('homepageView').classList.remove('hidden');
    document.getElementById('workbenchView').classList.add('hidden');
    document.getElementById('mindflowView').classList.add('hidden');
}

function showWorkbench() {
    document.getElementById('homepageView').classList.add('hidden');
    document.getElementById('workbenchView').classList.remove('hidden');
    document.getElementById('mindflowView').classList.add('hidden');
}

function showMindflow() {
    document.getElementById('homepageView').classList.add('hidden');
    document.getElementById('workbenchView').classList.add('hidden');
    document.getElementById('mindflowView').classList.remove('hidden');
}
```

### 路由侧边栏 (workbenchView)

A2A 生态区包含 8 个功能路由，通过 `data-route` 属性切换：

| 路由 | 图标 | 内容 |
|:-----|:-----|:-----|
| `intent` | ⚡ | 意图解析面板 |
| `routing` | 🔀 | Skill 路由面板 |
| `decision` | 🌳 | 决策树面板 |
| `memory` | 🧠 | 记忆图谱面板 |
| `agents` | 🤖 | Agent 广场 |
| `doubao` | 💬 | 豆包记忆桥 (iframe 嵌入) |
| `graph` | 🌌 | 记忆星云 (知识图谱 SVG) |
| `logs` | 📋 | 执行日志 |
| `settings` | ⚙️ | 设置 |

### Mindflow 侧边栏

| 标签 | 内容 |
|:-----|:-----|
| 思维画布 | 自由拖拽节点（项目构想/MVP/技术选型等） |
| 任务看板 | 待办事项管理 |
| 笔记库 | 笔记浏览 |
| 人格画像 | AI 生成的用户画像 |

---

## 9. 样式系统

### 颜色系统 (CSS 变量)

| 变量 | 用途 |
|:-----|:-----|
| `--nebula-*` | 紫色系（主色调） |
| `--cosmic-*` | 深紫/蓝色 |
| `--pink-*` | 粉色（Mindflow 专用） |
| `--amber-*` | 金色（高亮） |
| `--emerald-*` | 绿色（成功/在线） |
| `--sky-*` | 天蓝色（豆包桥） |

### 关键 CSS 类

| 类 | 作用 |
|:-----|:-----|
| `.glass-soft` | 毛玻璃效果 |
| `.cosmic-bg` | 星空背景 |
| `.view-panel` | 视图面板（hidden 切换） |
| `.router-node` | 路由节点卡片 |
| `.nav-pill` | 导航胶囊 |
| `.tag` | 状态标签 |
| `.reveal` | 滚动显现动画 |
| `.code-block` | 等宽代码块 |
| `.reg-overlay` | 注册模态框遮罩 |
| `.reg-modal` | 注册模态框 |

### 动画

| 动画 | 说明 |
|:-----|:-----|
| `animate-pulse-soft` | 柔和脉动 |
| `animate-spin-slow` | 慢速旋转 |
| `reveal` + `visible` | 滚动显现（IntersectionObserver） |
| `bubble-char` | 气泡文字逐个出现 |

---

## 变更记录

| 日期 | 版本 | 变更 |
|:-----|:----|:-----|
| 2026-07-27 | 2.0 | 文档初版：两视图架构、API清单、注册流程、JS函数索引 |
| 2026-07-26 | 1.0 | 删除重复 Mindflow 面板，精简至 2,515 行 |
