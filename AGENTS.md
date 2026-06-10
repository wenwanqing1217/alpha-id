# Alpha-ID 项目 — Agent 交接文档

## 接手必读

1. 先读 TODO.md — 知道当前进度和待办
2. 读 docs/AGENT_CONTEXT.md — 项目约束和状态
3. 读 docs/PLAN.md — 执行路线图
4. 读 docs/decisions.md — 已确认决策

## 技术栈

Python 3.12+, Typer (CLI), FastAPI (API), SQLite, MCP 协议
Three.js (Web 端), TailwindCSS (前端)

## 入口命令

aid = "alpha_id.cli:app"

## 当前状态

- 核心测试 715 通过 ✅（排除 fairy_agent + daemon + integration）
- 根目录已清理 ✅
- ghost.html 已更新（含 Codex CLI 集成）
