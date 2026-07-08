# Alpha-ID 当前状态（2026-07-08）

## 一句话现状

- 项目已经不是一个概念 demo，而是一个**可运行、可展示、可继续扩展**的系统原型。
- 当前核心链路已通：`aid init → aid profile mine --path . → aid profile show → aid profile web → aid-mcp`
- 当前重点不是“继续加功能”，而是**把已有系统讲清楚、展示清楚、继续稳定化**。

---

## 已完成（可直接演示）

- **DID 身份层**：本地生成 `did:aid:`，私钥不离开本机。
- **本机痕迹挖掘**：`aid profile mine --path .` 能从实际存在的文件/项目里生成画像，不是先假设你有什么。
- **Web 个人空间**：可打开 `aid profile web` 查看数字身份与记忆信号。
- **MCP 注入**：`aid-mcp` 可对外暴露 `profile://identity`、`profile://style`、`profile://memory` 等资源。
- **Git 采集**：`aid collect git --path .` 已可用，可把项目痕迹回填进画像。
- **测试基线**：`tests/test_mcp_server.py` 的 Codex / MemoryGraph / tool list 组已验证通过；`tests/test_aid_daemon.py` 兼容层已恢复。
- **扩展验证**：`tests/test_mining.py`、`tests/test_signer.py`、`tests/test_did.py`、`tests/test_memory_graph.py`、`tests/test_codex.py`、`tests/test_ocr.py`、`tests/test_identity_tool.py`、`tests/test_cli.py`、`tests/test_api.py`、`tests/test_web.py`、`tests/test_daemon.py`、`tests/test_collectors.py`、`tests/test_git_collect_cli.py`、`tests/test_cursor_collector.py`、`tests/test_agent_cli.py`、`tests/test_agent.py`、`tests/test_agent_react.py`、`tests/test_action_engine.py` 均已通过。

---

## 商业/面试叙事（当前最值得讲的版本）

- **不是另一个 AI 助理**：大多数项目都在做“新增一个助手”，Alpha-ID 做的是**让所有现有工具都认识同一个你**。
- **Ghost Layer 定位**：坐落在所有 AI 工具之上的身份/记忆层，不替换现有工具，只增强连续性。
- **本地主权**：私钥在本地，画像可导出，不把用户锁在某个平台。
- **先看本机有什么**：不强依赖 ChatGPT/Claude/Cursor 导入，而是先扫描用户电脑里实际存在的痕迹。
- **面试官最可能追问的点**：
  1. 你和其他 AI 助理/工作流项目最大的区别是什么？
  2. 为什么 DID 重要？为什么不能只做一个用户画像文件？
  3. 你们到底是在做模型、平台还是协议？
  4. 商业价值到底在哪里？
  5. 现在这个项目能证明什么？

---

## 当前阶段的核心判断

- **保留全系统愿景**：DID / I2I / A2A / 双大脑 / 模拟盘 / MCP 注入都保留。
- **当前聚焦 Phase 1 demo**：优先保证完整链路可演示，不继续抽象扩圈。
- **过时约束不自动生效**：历史好决策不等于今天必须遵守；需要就保留，不需要就调整。
- **稳定比完美重要**：先做一个能打开的 GitHub、能讲的 demo、能继续演进的项目。

---

## 已修复/已清理

- 统一 MCP server 入口与兼容层：`src/entrypoints/aid_mcp_server.py`
- 统一 daemon 兼容入口：`src/aid_daemon.py`
- 修复 legacy 测试导入与兼容方法暴露
- 清理旧版 `src/entrypoints/mcp.py` 遗留模块
- README / demo / CURRENT_STATE 对外呈现已对齐当前 Phase

---

## 下一步（按优先级）

1. **展示优先**：把 GitHub README、demo 脚本、30s/3min 叙事继续打磨到可直接对外发。
2. **稳定性次优先**：继续修复剩余历史测试，尤其是 daemon/MCP 边缘用例。
3. **采集扩展**：Browser / Trae / Cursor 真实数据回流与 provenance 展示。
4. **Phase 2 铺垫**：双大脑拆分、因果图谱、A2A 轻量适配。

---

## 当前可直接使用的命令

```bash
cd D:\AID\projects
pip install -e ".[dev]"
aid init
aid profile mine --path .
aid profile show
aid profile web
python scripts/demo.py
```

## 当前可直接运行的测试（已验证通过）

```bash
cd D:\AID\projects
python -m pytest tests/test_mcp_server.py::TestCodexTools -q
python -m pytest tests/test_mcp_server.py::test_all_tools_listed -q
python -m pytest tests/test_mcp_server.py::TestMemoryGraphTools -q
python -m pytest tests/test_mining.py tests/test_signer.py tests/test_did.py tests/test_memory_graph.py tests/test_codex.py tests/test_ocr.py tests/test_identity_tool.py -q
python -m pytest tests/test_cli.py tests/test_api.py tests/test_web.py tests/test_daemon.py -q
python -m pytest tests/test_collectors.py tests/test_git_collect_cli.py tests/test_cursor_collector.py tests/test_agent_cli.py tests/test_agent.py tests/test_agent_react.py tests/test_action_engine.py -q
```
