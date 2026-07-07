# Alpha-ID 当前状态（2026-07-06）

## 已确认

- 保留完整系统愿景：DID / I2I / A2A / 双大脑 / 模拟盘 / MCP 注入
- 当前主链路：`aid init → aid profile mine --path . → aid profile show → aid profile web → aid-mcp`
- 新增 mining 层：`src/alpha_id/mining/{scanner,extractor,inferrer}.py`
- 新增 `aid profile mine --path ...` 命令
- Web 新增 `/profile` 与 `/simulation` 页面
- 新增 `tests/test_mining.py`

## 旧约束处理

- 保留有效红线：私钥不上传、DID 隐藏体验、I2I + A2A 都要
- 废除自动生效：旧版“core/ 永远零外部依赖”“永远不用 LangChain”“绝对不改旧测试”
- 当前策略：优先新增测试；依赖/框架重新评估，不自动沿用旧禁令

## 下一步

- 画像置信度 + 来源追溯
- 完整度评分
- 隐私脱敏
- 扩展采集器：Claude / Cursor / Git / Browser
