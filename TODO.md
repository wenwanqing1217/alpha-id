# Alpha-ID 执行追踪

> 最后更新: 2026-06-11
> 接手 AI 的第一件事：读这个文件。

## 已完成

- [x] 根目录清理（68/, datalog/, node_modules/ 等已删除）
- [x] 包结构收紧（pyproject.toml include 精确化）
- [x] egg-info 清理（删除了重复的 alpha_id.egg-info / alpha_id_zix.egg-info）
- [x] identity_cli.py 语法错误修复（空 else: 块 + 重复函数定义清理）
- [x] _CONFIG_DIR 未定义修复（改为 _KEY_DIR）
- [x] agent.py parse_tool_call 支持旧格式（无 id:xxx 前缀）
- [x] agent_react.py 解包错误修复（2值变3值）
- [x] 核心测试 715 通过 0 失败（排除 fairy_agent + aid_daemon + integration）
- [x] ghost.html 内容更新（Hero 文案 + Codex CLI 提及）
- [x] index.html 恢复为原 Vue.js 控制台页面

## 待做

- [ ] fairy_agent.py 测试修复（20 个环境依赖失败，需要 mock API key）
- [ ] aid_daemon.py 超时问题（某个测试启动持久进程不退出）
- [ ] integration/ 测试（8 个 E2E 测试，依赖数据库）
- [ ] src/ 根下松散 .py 文件收拢（aid_daemon.py 等 7 个文件）
- [ ] ruff lint 清理（192 个错误，55 个可自动修复）
- [ ] Web 端完善（ghost.html 对接真实 API）
- [ ] 模拟盘概念设计

## 关键决策

- 项目核心定位：跨工具身份连续性（不是工具，是坐在所有 AI 工具之上的 Ghost Layer）
- 当前聚焦：Phase 0 整容（目录清理 + 测试全绿 + lint 零错误）
- 面试展示策略：Web 端（ghost.html）+ CLI 工具完整可用
- Codex CLI 是重点集成目标
