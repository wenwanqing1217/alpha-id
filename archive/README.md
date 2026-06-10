# archive/ — 历史文档归档

> 这些文件的内容已被合并到核心文档中。存档目的是保留历史上下文，不丢失任何原始信息。
>
> 每个文件都标注了：①它有什么 ②哪些内容已提取到主文档 ③它还保留了什么历史价值

---

## 一、已提取内容至主文档

| 文件 | 提取了什么 | 提取到 |
|:----|:----------|:-------|
| `ROADMAP.md` | 7 条前沿调研洞察（Anthropic Agent、W3C DID、MiMo-Skills、AT Protocol、LangGraph 等）——每条洞察对应的设计决策和代码影响 | `ARCHITECTURE.md` Appendix: Research Sources |
| `FINAL_PLAN.md` | "VISION 路线 vs ROADMAP 路线"的完整辩论记录，包括选择产品优先路线的原因 | `decisions.md` §路线选择 |

---

## 二、文件索引

### 核心文档的前身（内容已并入 AGENT_CONTEXT.md）

| 文件 | 原始内容 | 历史价值 |
|:----|:--------|:---------|
| `AGENTS.md` | 早期战术手册，包含"一句话定位/架构快照/阶段方向" | 记录了 2026-05-30 时刻的项目认知状态，可用于对比项目理解的变化 |
| `CARRY_OVER.md` | "给新窗口的信"——2026-05-30 写给 AI Agent 的历史上下文。包含"核心问题诊断"和"现有代码清单" | **最高历史价值。** 代码清单中标注了哪些文件"不改"、哪些"待重写"，是项目从 SDK 转向产品的起点记录 |
| `CHATLOG.md` | 2026-05-29 完整对话记录（8 轮对话：问题诊断→理念完善→技术分析→6个升级→冷启动悖论→产品形态→商业模式→插件生态） | 记录了"冷启动悖论"和"Ghost Layer"概念的原始诞生过程 |
| `CONTINUE.md` | AI Agent 的"继续"工作指令，包含 2025-07 的 Phase 1 执行顺序 | 已过时，执行顺序已完全被 PLAN.md 替代 |
| `FINAL_PLAN.md` | 2026-05-30 的最终方案总汇，包含"市场格局一览"、"两套路线冲突"、"最小惊艳版本"建议 | **路线选择决策的原始论证。** "最小惊艳版本"建议（2周MVP）的思想依然有效，详见 PLAN.md P0 |

### 旧路线图

| 文件 | 原始内容 | 历史价值 |
|:----|:--------|:---------|
| `ROADMAP.md` | 2025-07 的技术驱动路线（评分 2.7→4.5，Phase 1-3 的技术基建计划），以及 7 条前沿调研洞察 | **调研洞察已提取到 ARCHITECTURE.md。** 原始评分体系和三阶段计划记录了项目从技术角度的演进思路 |

### 对话记录

| 文件 | 原始内容 | 历史价值 |
|:----|:--------|:---------|
| `ki.md` | 2026-05-30 的 AI 分析对话。回答"这个项目解决了什么痛点、填补了什么空缺、优劣在哪" | 一次性的分析输出，内容已并入星链报告 和 AGENT_CONTEXT.md |

### 旧技术文档（已合并入 ARCHITECTURE.md）

| 文件 | 原始内容 | 已提取至 |
|:----|:--------|:---------|
| `docs/alpha-id-schemes.md` | 技术方案概述 | ARCHITECTURE.md 全文 |
| `docs/arch-v2.md` | 架构版本 v2 设计 | ARCHITECTURE.md §3 四层架构 |
| `docs/architecture-review.md` | 架构评审记录 | ARCHITECTURE.md §12 设计原则 |
| `docs/project-blueprint.md` | 项目蓝图（Coze 原型阶段） | VISION.md §1 核心理念 |
| `docs/security-optimization.md` | 安全优化方案（加密/风控/密钥管理） | ARCHITECTURE.md §10 安全架构 |
| `docs/twin-brain-architecture.md` | TwinBrain 状态机详细设计 | ARCHITECTURE.md §5 TwinBrain |

### 行业分析记录

| 文件 | 原始内容 | 已提取至 |
|:----|:--------|:---------|
| `2026-06-04-行业对标与文件整理.md` | 当天行业对标分析（OpenCLI/A2A/MCP）和优先级调整建议 | 建议已写入 PLAN.md；完整记录保留供历史参考 |

### 2026-06 新增归档（来自根目录）

| 文件 | 原始内容 | 历史价值 |
|:----|:--------|:---------|
| `元宝.md` | 元宝 AI 对 Alpha-ID 的分析建议 | 6家AI情报之一，Schema先锁定的建议来自这里 |
| `千问.md` | 千问 AI 对 Alpha-ID 的评审 | 6家AI情报之一 |
| `文心.md` | 文心 AI 对 Alpha-ID 的评审 | 6家AI情报之一 |
| `智普.md` | 智谱 AI 对 Alpha-ID 的评审 | 6家AI情报之一 |
| `AI项目方向探讨快速模式.md` | 与 DeepSeek 的完整对话记录（宇宙星链思维、五框架、市场分析） | 记录了"宇宙星链"思维和"五框架"的原始诞生过程 |
| `项目评估与AI选择.md` | 项目评估报告和 AI 工具选择分析 | 早期评估记录 |
| `Alpha-ID 项目全方位规划书.md` | 项目全方位规划书 | 早期规划文档 |
| `deep seek.md` | DeepSeek 对话记录 | 早期讨论记录 |
| `Kimi 分析 2026-06-07.md` | Kimi 深度阅读 15 份文档后的独立判断 | 五星球框架、让人哇塞的瞬间标准、数字主权起义叙事参考。⚠️ 含已知错误，以 decisions.md 为准 |

### 2026-06-06 新增归档（来自 docs/）

| 文件 | 原始内容 | 已提取至 |
|:----|:--------|:---------|
| `CHANGELOG.md` | 版本历史日志（v0.0.1 ~ v0.1.2） | 内容已覆盖在 AGENT_CONTEXT.md 项目状态中 |
| `CONTRIBUTING.md` | 贡献指南（开发环境/分支策略/commit规范） | 单人开发阶段不需要，内容与 AGENT_CONTEXT.md 代码约束重叠 |
| `CONVERSATION_CLEAN.md` | 项目方向探讨结论整理 | 已融入 AGENT_CONTEXT.md + FRAMEWORK.md |
| `DEVELOPER.md` | 开发者文档（目录结构/测试/代码约束/版本历史） | 已融入 AGENT_CONTEXT.md 项目结构表 |
| `MANIFESTO.md` | 战略宣言（五层思维/竞品分析/三条路径） | 已融入 VISION.md + decisions.md |

---

## 三、核心文档与历史文件的对应关系

| 当前核心文档 | 对应历史文件 |
|:------------|:------------|
| `VISION.md` | CHATLOG.md（理念来源）+ project-blueprint.md（原型期蓝图） |
| `ARCHITECTURE.md` | docs/ 下全部 6 个技术文档 + ROADMAP.md（调研洞察） |
| `AGENT_CONTEXT.md` | AGENTS.md + CARRY_OVER.md + CHATLOG.md + CONTINUE.md + FINAL_PLAN.md |
| `PLAN.md` | ROADMAP.md（旧路线图） |
| `decisions.md` | FINAL_PLAN.md（路线选择论证）+ ki.md（策略分析） |
| ~~`LANDSCAPE.md`~~（已删除） | 已被 `archive/private/星链级全维度竞品检索报告.md` 替代。CHATLOG.md（市场分析部分）+ ki.md（痛点分析）曾是旧版来源 |

---

> *归档索引维护原则：每次新增核心文档时，更新此索引。*
> *Last updated: 2026-06-08*
