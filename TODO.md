# Alpha-ID 执行追踪（拍板版）

> 最后更新: 2026-07-06
> 当前阶段：从“完整野心”切换为“可演示的完整链路执行”。

## 已拍板

- [x] 完整审阅项目全部核心 Markdown / 归档 Markdown。
- [x] 确认保留全系统愿景：DID / I2I / A2A / 双大脑 / 模拟盘 / MCP 注入。
- [x] 确认不做模型、不做平台、不造协议、不做通用助理 demo。
- [x] 确认商业叙事升级：记忆基础设施 + 可信代理层 + 本地主权 AI。
- [x] 更新落地文档：`docs/IMPLEMENTATION_PLAN.md`。
- [x] 更新 README 主视角：从零散功能改为完整系统展示。

## 当前基线

- [x] `src/` 下 88 个 Python 文件，结构已基本成形。
- [x] 代码约束已统一：`core/` 零外部依赖、CLI 使用 Typer、Web 使用 FastAPI。
- [x] 采集器框架已覆盖：ChatGPT / Claude / Cursor / Trae / Browser。
- [x] 已知阻塞点：`tests/test_mcp_server.py` 旧模块名导入；Windows `tmp_path` 权限问题。

## 立即执行（Phase 1 — 完整链路，进行中）

- [x] 新增 `src/alpha_id/mining/`：`scanner.py` / `extractor.py` / `inferrer.py`。
- [x] 新增 `aid profile mine --path ...`：把本机痕迹变成第一版画像。
- [ ] 补齐 `aid profile show`：完整度 + 来源追溯 + JSON/彩色双模式。
- [x] 补齐 `aid profile web`：个人空间 + 星链宇宙 + 模拟盘入口。
- [ ] 补齐 `aid-mcp` 对外资源：`profile://identity` / `profile://style` / `profile://memory`。
- [ ] 更新 `README.md` / `README.zh.md` / 面试 narrative：30s + 3min demo script。

## 下一阶段（Phase 2 — 稳定扩展）

- [ ] 扩展采集器：Claude / Cursor / Git / 浏览器历史。
- [ ] 修复 MCP / 测试基线问题，恢复完整测试通行。
- [ ] 拆分双大脑：理解脑 + 执行脑，明确职责边界。
- [ ] 轻量 A2A 适配器：完成协议宣誓，不追求深度实现。
- [ ] 因果图谱 MVP：先做展示，再做自动抽取。

## 远期（Phase 3 — 生态）

- [ ] I2I + A2A 完整闭环。
- [ ] 数字遗产 / 继承规则。
- [ ] 对外开源标准组件：记忆格式 / 身份适配层。

## 关键决策

- 项目定位：跨工具身份连续性 + 本地主权 AI。
- 当前聚焦：先做“可演示的完整系统”，不做“最小 demo”。
- 面试展示策略：Web 端 + CLI 主链路 + 模拟盘魔法时刻。
- 商业路径：开源影响力 -> 订阅/企业 -> 生态标准组件。
