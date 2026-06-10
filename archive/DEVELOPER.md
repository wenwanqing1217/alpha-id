# Alpha-ID 开发者文档

## 目录结构

```
src/
  alpha_id/      # CLI 入口 + Profile 系统
    collectors/  # 数据采集器（chatgpt、claude、cursor）
    did.py       # DID 身份系统（did:aid:xxx + Ed25519）
    profile_*.py # 画像管理（CLI、Schema、MCP、Wizard）
    agent_cli.py # A2A Agent 连接（scan、handshake）
    suggest_cli.py # 多源扩散推荐
  core/          # 核心逻辑（DID、Agent、记忆、风控）
  api/           # FastAPI 接口
  auth/          # JWT 认证
  tools/         # 屏幕截图、OCR、窗口控制
tests/           # pytest 测试
docs/            # 文档
```

## 六框架检验（当前状态）

| 框架 | 预埋位置 | 进度 |
|:----|:---------|:----:|
| 宇宙星链 | 点→线→面→球→球变新点→复刻。不是线性扩散 | 🔄 第一节已跑通 |
| 第一性原理 | Profile模型自带身份校验 | ✅ DID+记忆 |
| 反向推翻 | 每个采集器自带 fallback | 🔴 待实现 |
| 递归降维 | 700行闭环已跑通，再决定是否升维 | ✅ 已降维到最小 |
| 反脆弱 | 分析引擎带失败模式记录 | 🔴 待实现 |
| 择优融合 | 取A的核+B的核，砍冗余拼成C | 🔴 待写suggest用 |
| 得失同源 | 每加一个东西，先问解决了什么、增加了什么负担 | 🔴 待执行中验证 |

## 测试

```bash
pytest tests/ -q              # 快速跑
pytest tests/ -v              # 详细模式
pytest tests/ --cov=src       # 覆盖率
```

当前 855 个测试（852 passed, 3 skipped），覆盖率目标 ≥68%。

## 代码约束

- 测试: pytest, 每次修改后跑 `python -m pytest tests/ -q`
- 格式化: ruff（配置在 ruff.toml）
- CLI 入口: pyproject.toml 中 `aid = "alpha_id.cli:app"`, 用 typer
- 新增模块必须加 `__init__.py`, 导出公共接口
- 核心逻辑写在 `core/`, 不依赖外部包
- ❌ 禁止引入 LangChain 作为依赖
- ❌ 禁止修改已有测试文件（除非只改预期值）
- ❌ 禁止发 git commit / 建分支
- ❌ 禁止加版权头
- ❌ 禁止改与当前任务无关的代码

## 版本历史

| 版本 | 日期 | 改动 |
|------|------|------|
| v0.0.1 | 2026-06-28 | 首次 PyPI 发布 |
| v0.0.4 | 2026-06-28 | DID 生成、README 精简、MCP 修复、SQLite 泄漏修复 |
| v0.0.5 | 2026-06-28 | 零数据魔法时刻、Web UI、英文 README |
| v0.0.6 | 2026-06-28 | Lint 修复、代码清理 |
| v0.0.7 | 2026-06-28 | 删 Codex、GitHub URLs 修复 |
| v0.0.8 | 2026-06-28 | HTML 身份卡片导出 |
| v0.0.9 | 2026-06-28 | MCP 一键安装 (`--install`) |
| v0.1.0 | 2026-06-28 | 稳定版 + Web 自动打开浏览器 |
| v0.1.1 | 2026-06-28 | 后台常驻 daemon |
| v0.1.2 | 2026-06-28 | A2A 验证工具 + 用户引导升级 |
| (当前) | 2026-06-28 | agent scan/handshake、cursor 采集器、suggest 推荐、端到端测试 |
