# Alpha-ID — 战术手册

> 每次对话前自动注入。不需要再读其他文档。
> 深度引用请走 decision.md。

---

## 一句话定位

Alpha-ID 是你的**数字灵魂 / Ghost Layer**。它坐在所有 AI 工具（ChatGPT/Claude/Cursor）上面，提供「跨平台属于你」的身份、记忆和操作能力。

## 当前状态（2026-05-30）

- **评分**: ~4.0/5.0 | **测试**: 525 passed | **源文件**: 86 (src/) + 26 (tests/)
- **Phase 1 身份地基**: ✅ 100%
- **Phase 2 信誉网络**: ✅ 80%
- **Phase 3 身份自治**: ✅ 75%

## 核心架构（原始设计）

```
用户客户端（私钥在本地，只能签名不能伪造）
    ↓ API
TwinBrain（大脑/云端，只能验证/执行，不能伪造身份）
    ↓
存储层（Postgres + Vector DB，日志/关系全在服务端）
```

## 关键结论（不再讨论）

- 不做模型、不做框架、不造协议、不做平台
- 搭便车：MCP（工具层）+ A2A（社交层）
- 私钥**不在大脑里**，大脑只做验证
- Agent = 简单 LLM + Tools + Loop
- core/ 层零外部依赖
- DID 对用户无意义，藏起来

## 语音（已确认——双向交互）

- 输入：麦克风 → ASR → TwinBrain
- 输出：Agent 回答 → TTS 播报
- 声线人格：Phase 2 再定

## 架构快照

```
src/alpha_id/     # SDK — Agent, Container, DID, Signer, CLI(typer), Web(FastAPI)
src/core/         # 核心层 — TwinBrain, ReAct, MemoryStore, Social, Risk, Reputation, PoE
│  └── action_engine/  # 操作引擎
src/tools/        # Agent 工具 — screen_capture, OCR, window_control, identity...
src/storage/      # 存储 — database, memory, S3
src/api/          # FastAPI 路由
src/auth/         # JWT 认证
src/utils/        # 工具函数
```

## 阶段方向

**P0** 遗留清理（删 agents/ 和 graphs/）+ 文档名称统一
**Phase 0** 语音输入 Tool + 导入器（ChatGPT/GitHub）
**Phase 1** MCP Server + Daemon
**Phase 2** Computer Use + 声线 TTS
**Phase 3** 自主生存 + 晨报
