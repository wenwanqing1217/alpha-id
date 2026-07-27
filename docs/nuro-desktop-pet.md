# NURO 桌面精灵 — 技术文档

> **版本 3.0** | **2026-07-27**
> **纯本地 AI 贾维斯，运行在 Windows 桌面上的悬浮精灵。**

---

## 目录

1. [定位与愿景](#1-定位与愿景)
2. [模块结构](#2-模块结构)
3. [14步启动序列详解](#3-14步启动序列详解)
4. [语音链路](#4-语音链路)
5. [视觉系统](#5-视觉系统)
6. [VRAM 预算表](#6-vram-预算表)
7. [功能标志系统](#7-功能标志系统)
8. [MCP 后台服务器](#8-mcp-后台服务器)
9. [隐私模式](#9-隐私模式)
10. [安装指南](#10-安装指南)
11. [开发与调试](#11-开发与调试)

---

## 1. 定位与愿景

NURO 是 Ghost 项目的**桌面伴侣层**。它是一个纯本地运行的 AI 助手，以悬浮精灵的形式存在于 Windows 桌面上。

### 核心理念

- **纯本地**：不依赖云端 API，所有推理在本地 GPU 完成
- **永远在线**：开机自驻，随时响应语音唤醒或点击
- **隐私优先**：数据不出本地，支持 blind/deaf 隐私模式
- **多模态**：语音对话 + 视觉理解 + 屏幕观察

### 在 Ghost 生态中的位置

```
[你]
  │
  ├─ 语音/点击 → NURO 桌宠 (本地 Ollama + 双链记忆)
  │                │
  │                ├─ MiniCPM-o-4.5 (视觉)
  │                ├─ Whisper (语音识别)
  │                ├─ Coqui TTS (语音合成)
  │                └─ MCP 后台服务器 (工具调用)
  │
  ├─ 飞书 → Gateway → Alpha-ID
  ├─ Ghost.html → Gateway → Alpha-ID
  └─ 豆包 → 豆包阅读器 → Gateway → Alpha-ID
```

NURO 是**唯一不经过 Gateway 的入口**，因为它完全运行在本地。

---

## 2. 模块结构

路径: `D:\MW\alphaid\projects\src\entrypoints/`

| 模块 | 行数 | 职责 | 依赖 |
|:-----|:----:|:-----|:-----|
| `app.py` | 1,047 | AidNuro 主类 — 14步启动序列、UI布局、事件循环 | 所有子模块 |
| `cli.py` | 190 | CLI 入口 — 参数解析、环境检测、安全打印 | feature_flags |
| `feature_flags.py` | 171 | 功能标志 — 所有 `_HAS_*` 能力检测 | fairy/* (可选) |
| `daily_summary.py` | 95 | 每日总结调度 — 22:00 自动 + 手动触发 | datetime |
| `acrylic.py` | 56 | DWM 亚克力效果 — Win10/11 窗口模糊 | ctypes |
| `palette.py` | 24 | UI 调色板 — 深色主题配色 | 无 |
| `daemon.py` | 136 | 向后兼容 re-export shim | 所有上述模块 |

**总计: 1,719 行 / 7 文件**

### 依赖的外部模块（可选）

这些模块位于 `nuro/` 目录（项目外部），缺失时自动降级：

| 模块 | 职责 | 缺失时降级 |
|:-----|:-----|:-----------|
| `fairy_brain.py` | AI 大脑（MiniCPM-o + Ollama） | 纯文本模式 |
| `fairy_voice.py` | 语音（Whisper + Coqui TTS + 唤醒监听） | 纯文本模式 |
| `fairy_character.py` | 2D 卡通角色 + 状态机 | 降级为 emoji |
| `fairy_observer.py` | 主动观察循环（截屏+分析） | 无观察 |
| `fairy_popup.py` | 通知气泡/弹幕/Toast | 无通知 |
| `fairy_identity.py` | 身份初始化（FOUNDER → NURO DID） | 匿名模式 |
| `fairy_memory.py` | 双链记忆接入 | 无记忆 |
| `fairy_daily.py` | 每日总结生成 | 无总结 |

---

## 3. 14步启动序列详解

`AidNuro.__init__` 中的 14 步启动序列，每步都有优雅降级：

### 步骤详解

| # | 步骤 | 作用 | 降级策略 |
|:-:|:-----|:-----|:---------|
| 1 | 身份初始化 | FOUNDER → NURO DID 派生 | 跳过，匿名运行 |
| 2 | 记忆接入 | 连接双链记忆 SQLite | 跳过，无记忆模式 |
| 3 | 大脑 | 加载 MiniCPM-o + Ollama | 纯文本回退 |
| 4 | 语音 | 初始化 Whisper + Coqui TTS | 纯文本模式 |
| 5 | 通知气泡 | 创建 Popup 管理器 | 静默模式 |
| 6 | 主动观察器 | 启动观察循环（截屏+OCR+分析） | 不观察 |
| 7 | 每日总结 | 调度 22:00 自动总结 | 无总结 |
| 8 | Tkinter 角色窗口 | 创建透明悬浮窗口 | 基础窗口 |
| 9 | 2D 角色 | 加载 FairyCharacter 或降级 emoji | 显示 emoji |
| 10 | 右键菜单 | 绑定操作菜单（总结/设置/退出） | 无菜单 |
| 11 | 语音唤醒监听 | WakeupListener 后台线程 | 仅手动触发 |
| 12 | MCP 后台服务器 | 启动本地 MCP 工具服务器 | 无 MCP |
| 13 | 启动观察循环 | 开始主动观察调度 | 不观察 |
| 14 | 气泡绑定 + 呼吸动画 | UI 动效和交互绑定 | 静态显示 |

### 启动时序图

```
main() → AidNuro.__init__()
  │
  ├─ 1. _init_identity()     → FOUNDER → NURO DID
  ├─ 2. _init_memory()       → 双链记忆 SQLite
  ├─ 3. _init_brain()        → Ollama + MiniCPM-o
  ├─ 4. _init_voice()        → Whisper + Coqui TTS
  ├─ 5. _init_popup()        → 通知气泡管理器
  ├─ 6. _init_observer()     → 主动观察器
  ├─ 7. _init_daily()        → 每日总结调度
  │
  ├─ 8. _create_window()     → Tkinter 透明窗口
  ├─ 9. _create_character()  → 2D 角色/emoji
  ├─ 10. _bind_context_menu()→ 右键菜单
  │
  ├─ 11. _start_wakeup()     → 语音唤醒监听线程
  ├─ 12. _start_mcp_server() → MCP 后台服务器
  ├─ 13._start_observer_loop()→ 观察循环
  │
  └─ 14._finalize_ui()       → 气泡绑定 + 呼吸动画 + 定时器
```

---

## 4. 语音链路

### 完整语音链路

```
[你说话]
    │
    ▼
Whisper (tiny) ──→ 文本 ──→ Ollama (MiniCPM-o-4.5)
                                      │
                                      ▼
                                   AI 回复文本
                                      │
                                      ▼
                              Coqui TTS ──→ [NURO说话]
```

### 组件

| 组件 | 模型 | 平台 | VRAM |
|:-----|:-----|:-----|:----:|
| STT | Whisper tiny | CPU | ~0.5GB |
| LLM | MiniCPM-o-4.5 Q4_K_M | CUDA | ~5.5GB |
| TTS | Coqui TTS (VITS) | CUDA | ~1.5GB |

### 语音唤醒

`WakeupListener` 后台线程持续监听麦克风，检测到唤醒词后激活对话。

---

## 5. 视觉系统

### MiniCPM-o-4.5 多模态

NURO 使用 MiniCPM-o-4.5 作为视觉理解模型，支持：

- **屏幕观察**：定时截屏 → 视觉理解 → 主动提醒
- **应用窗口识别**：识别当前活动窗口
- **OCR 辅助**：读取屏幕文字

### 主动观察循环

```
每 N 秒:
  1. 截屏 (screen_capture)
  2. MiniCPM-o 分析
  3. 判断是否需要主动通知
  4. 如需 → 弹出气泡/弹幕
```

---

## 6. VRAM 预算表

**显卡: RTX 5070 Ti 16GB**

| 组件 | 显存 | 说明 |
|:-----|:----:|:-----|
| MiniCPM-o-4.5 Q4_K_M | ~5.5GB | 主 LLM + 视觉 |
| Whisper tiny | ~0.5GB | CPU 模式，显存占用极小 |
| Coqui TTS | ~1.5GB | VITS 语音合成 |
| CUDA + 系统 | ~2.5GB | CUDA 上下文 + 系统预留 |
| Tkinter + 2D角色 | ~0.3GB | 窗口和角色渲染 |
| **总计** | **~10.3GB** | **剩余 5.7GB** |

### 降级策略

如果显存不足，按以下顺序降级：

1. MiniCPM-o Q4 → Q3_K_M（节省 ~1.5GB）
2. Coqui TTS → SAPI TTS（节省 ~1.5GB）
3. Whisper → 纯文本输入（节省 ~0.5GB）
4. 2D 角色 → emoji（节省 ~0.2GB）

---

## 7. 功能标志系统

所有功能标志集中在 `feature_flags.py`，便于统一管理和测试。

### 标志列表

| 标志 | 含义 | 检测方式 |
|:-----|:-----|:---------|
| `_HAS_BRAIN` | AI 大脑可用 | `from fairy.fairy_brain import FairyBrain` |
| `_HAS_VOICE` | 语音可用 | `from fairy.fairy_voice import FairyVoice` |
| `_HAS_CHARACTER` | 2D 角色可用 | `from fairy.fairy_character import FairyCharacter` |
| `_HAS_OBSERVER` | 观察器可用 | `from fairy.fairy_observer import FairyObserver` |
| `_HAS_POPUP` | 通知气泡可用 | `from fairy.fairy_popup import FairyPopup` |
| `_HAS_IDENTITY` | 身份系统可用 | `from fairy.fairy_identity import FairyIdentity` |
| `_HAS_MEMORY` | 记忆系统可用 | `from fairy.fairy_memory import FairyMemory` |
| `_HAS_DAILY` | 每日总结可用 | `from fairy.fairy_daily import FairyDaily` |
| `_HAS_SCREEN` | 截屏可用 | `from tools.screen_capture import ...` |
| `_HAS_WINDOW` | 窗口枚举可用 | `from tools.window_tools import ...` |

### 设计原则

- 每个 `try/except` 只负责一个能力域
- 失败时静默降级，不中断启动
- 单元测试可以 monkeypatch 任意标志

---

## 8. MCP 后台服务器

NURO 内置 MCP（Model Context Protocol）服务器，允许外部工具通过标准协议调用 NURO 的能力。

### 提供的工具

| 工具 | 输入 | 输出 |
|:-----|:-----|:-----|
| `nuro_screenshot` | 无/区域坐标 | 截屏图片 |
| `nuro_ocr` | 图片 | 识别文本 |
| `nuro_chat` | 消息文本 | AI 回复 |
| `nuro_status` | 无 | NURO 运行状态 |
| `nuro_windows` | 无 | 窗口列表 |

### 启动方式

MCP 服务器在启动序列第 12 步自动启动，监听本地端口。

---

## 9. 隐私模式

NURO 提供两种隐私模式，可通过右键菜单或语音命令切换：

### blind 模式（盲人模式）

- **关闭**: 所有截屏和视觉观察
- **保留**: 语音对话、记忆、通知
- **适用**: 处理敏感内容时不希望 NURO 看到屏幕

### deaf 模式（聋人模式）

- **关闭**: 语音唤醒监听、Whisper 识别
- **保留**: 文字输入、视觉观察、通知
- **适用**: 公共场合或不希望被监听时

### 实现

隐私模式通过功能标志控制：
- blind: 禁用 `_HAS_SCREEN` 和 `_HAS_OBSERVER`
- deaf: 禁用 `_HAS_VOICE` 和唤醒监听线程

---

## 10. 安装指南

### 一键安装

```bash
install_deskpet.bat
```

安装脚本自动完成：
1. 检查 Python 版本（需要 3.11-3.13）
2. 安装 `alpha-id-zix` 核心包
3. 检查/提示安装 Ollama
4. 安装桌面精灵依赖（pyautogui, pillow）
5. 初始化配置（`aid init`）

### 手动安装

```bash
# 1. 安装核心包
pip install alpha-id-zix

# 2. 安装桌面精灵依赖
pip install pyautogui pillow

# 3. 安装 Ollama（如果未安装）
# 下载地址: https://ollama.ai

# 4. 拉取 LLM 模型
ollama pull minicpm-o:4.5

# 5. 初始化配置
aid init
```

### 启动

```bash
# 正常启动
python -m entrypoints.cli

# 环境检测模式
python -m entrypoints.cli --check

# 或直接运行
python -m entrypoints.app
```

### 系统要求

| 项目 | 最低 | 推荐 |
|:-----|:-----|:-----|
| OS | Windows 10 1803+ | Windows 11 |
| Python | 3.11 | 3.13 |
| RAM | 16GB | 32GB |
| GPU | GTX 1060 6GB | RTX 5070 Ti 16GB |
| 显存 | 6GB | 16GB |
| 磁盘 | 20GB 可用 | 50GB SSD |

---

## 11. 开发与调试

### 环境检测

```bash
python -m entrypoints.cli --check
```

输出示例:
```
NURO 桌面精灵 v3.0.0 — 环境检测
========================================
Python:    ✅ 3.12.4
Ollama:    ✅ 运行中（minicpm-o:4.5, whisper:tiny）
大脑:      ✅ FairyBrain 已加载
语音:      ✅ Whisper + Coqui TTS
角色:      ✅ FairyCharacter
观察器:    ✅ FairyObserver
记忆:      ✅ 双链记忆 (SQLite)
DWM亚克力: ✅ 可用
```

### 日志

NURO 使用 Python `logging` 模块，日志名为 `entrypoints.app`。

```python
import logging
logging.getLogger('entrypoints.app').setLevel(logging.DEBUG)
```

### 常见问题

| 问题 | 原因 | 解决 |
|:-----|:-----|:-----|
| 启动后无显示 | Tkinter 初始化失败 | 检查 Python Tkinter 支持 |
| 语音无响应 | Whisper/Ollama 未运行 | `ollama serve` + 检查模型 |
| 角色不显示 | fairy_character 缺失 | 安装 nuro/ 包或接受 emoji 降级 |
| 亚克力效果无效 | DWM 不可用 | Win10 1803+ 且启用透明效果 |
| 显存不足 | 模型太大 | 使用量化版或降级策略 |

---

## 变更记录

| 日期 | 版本 | 变更 |
|:-----|:----|:-----|
| 2026-07-27 | 3.0 | 文档初版：14步启动、语音链路、VRAM预算、隐私模式 |
| 2026-07-25 | 2.0 | v3 重构：拆分子模块、MiniCPM-o 接入、Whisper+Coqui |
| 2026-07-20 | 1.0 | v2：Dynamic Island 药丸形态 |
