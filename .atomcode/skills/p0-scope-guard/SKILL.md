---
name: p0-scope-guard
description: Phase 感知范围守卫。阻止当前 Phase 不该碰的内容，防止 scope creep。
model_invocation: true
user_invocation: false
---

# 范围守卫

## 当前 Phase: 1（多源采集）

### Phase 1 可以碰
- `collectors/` 目录（BaseCollector 协议、自动发现、采集器实现）
- `profile_cli.py`（collect scan / list / 场景识别）
- `profile_schema.py`（来源标记、merge 优化）

### Phase 1 禁止清单（Phase 2+ 才做）

| # | 禁止项 | 所属 Phase |
|:-:|--------|:---------:|
| 1 | MCP 身份注入到 Claude/Cursor/Trae | Phase 2 |
| 2 | 思维框架引擎（FrameworkEngine）| Phase 2 |
| 3 | 因果图谱 | Phase 2 |
| 4 | A/B 测试框架（`aid test ab`）| Phase 2 |
| 5 | A2A / I2I 协议 | Phase 3 |
| 6 | 完整七框架引擎 | Phase 3 |
| 7 | 数字遗嘱 | Phase 3 |
| 8 | Web 宇宙可视化 | Phase 3 |

## 检查逻辑

如果检测到改动涉及上述领域 → 打印警告并暂停，询问用户确认。
如果用户确认要做，不阻止（用户有权提前做后续 Phase 的内容）。
