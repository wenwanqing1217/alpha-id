# Alpha-ID 当前状态（2026-07-07）

## 已确认

- 保留完整系统愿景：DID / I2I / A2A / 双大脑 / 模拟盘 / MCP 注入
- Phase 1 主链路已通：`aid init → aid profile mine --path . → aid profile show → aid profile web → aid profile serve`
- mining 层已落地：`src/alpha_id/mining/{scanner,extractor,inferrer}.py`
- 新增画像质量字段：完整度、来源追溯
- Web 个人空间可运行：`src/alpha_id/web.py`
- MCP profile 资源已补齐：`profile://identity`、`profile://style`、`profile://memory`

## 旧约束处理

- 保留有效红线：私钥不上传、DID 隐藏体验、I2I + A2A 都要
- 废除自动生效：旧版“core/ 永远零外部依赖”“永远不用 LangChain”“绝对不改旧测试”
- 当前策略：优先新增测试；依赖/框架重新评估，不自动沿用旧禁令

## 已推进

- 采集器真实数据回流：Browser / Trae / Claude / Cursor / Git
- `aid collect scan` 已可自动发现并合并多源画像
- 测试修复：`tests/test_user_identity.py` 已恢复（10 passed）
- 面试包：30s/3min demo script + README 更新

## 下一步

- 画像质量：置信度 + 脱敏 + 多轮合并
- 测试修复：剩余 20 个历史失败用例
- Web/MCP：采集结果到个人空间与 MCP 资源

## 本次推进

- Web profile 数据层：新增 `/api/profile`，个人空间可展示 collected sources + provenance。
- Git 采集器：新增 `aid collect git --path .` 手工命令，scan 也会自动纳入 Git 检测。
- 测试一致性：修复 `tests/test_codex.py`、`tests/test_fairy_agent.py` 的 wording/availability 回归。
- 面试包：README 增加当前主链路、并行推进策略、公开状态说明。
