---
name: ai-context-loader
description: 自动加载 Alpha-ID 项目上下文。每次会话开始前加载核心文档，确保 AI 不丢失项目记忆和约束。
model_invocation: true
user_invocation: false
---

# Alpha-ID 项目上下文

## 必须加载的文档

| 文件 | 路径 |
|:----|:----|
| **AGENT_CONTEXT.md** | `D:\AID\projects\docs\AGENT_CONTEXT.md` |
| **PLAN.md** | `D:\AID\projects\docs\PLAN.md` |
| **decisions.md** | `D:\AID\projects\docs\decisions.md` |
| **FRAMEWORK.md** | `D:\AID\projects\docs\FRAMEWORK.md` |
| **MANIFESTO.md** | `D:\AID\projects\docs\MANIFESTO.md` |

## 关键约束速查

- 当前: Phase 1 多源采集（6 个任务）
- Phase 0 已完成: `aid init → collect chatgpt → profile show` 闭环
- 禁止: LangChain / 改已有测试 / git commit / 版权头
- 核心层 `src/core/` 零外部依赖
- Python 3.12+, pytest, ruff, 行宽 120, 双引号
- 用户习惯: 中文确认，不自动打开浏览器
