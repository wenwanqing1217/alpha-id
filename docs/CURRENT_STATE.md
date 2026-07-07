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

## 下一步

- 画像质量：置信度 + 脱敏 + 多轮合并
- 采集扩展：Claude / Cursor / Git / Browser 真实数据回流
- 测试修复：剩余 21 个历史失败用例
- 面试包：30s/3min demo script + Web 展示优化
