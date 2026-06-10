---
id: AID-CTX-001
title: Alpha-ID Agent Context
version: 4.0.0
status: Active
last_reviewed: 2026-06-08
---

# Alpha-ID — Agent Context

> 最小上下文。Agent 读完即开工，不需要读 archive/ 或历史讨论。

---

## 唯一真相源（必读）

| 文档 | 内容 |
|------|------|
| **AGENT_CONTEXT.md**（本文件） | 项目定位、约束、当前状态 |
| **decisions.md** | 所有已确认决策（§十四 是最新约定） |
| **TODO.md** | 现在做什么、下一步、卡在哪里 |

规则：三份核心文档 > 其他任何文档。冲突以此为准。

archive/ 目录为历史思考，完整但不需要全部读。

---

## 是什么

把散落在数字世界里的你捡起来——收集、重组、延续，让它替你活着、替你社交、替你学习。

Ghost Layer：坐在所有 AI 工具上面的那一层。

---

## 当前聚焦的事（⏸ 不是永久禁止，只是当前阶段不做）

- 当前阶段不做模型、不做平台、不造协议（聚焦核心能力）
- 当前阶段不引入 LangChain（避免复杂度）
- 多源采集器暂缓（P1 再扩展）
- Computer Use Plan/Safety 层暂缓（先做 Skill 层）

## 永久不变的事（🚫 永远不做）

- 私钥永远在客户端，不上传
- core/ 零外部依赖
- DID 对用户无意义，藏在体验下面
- I2I + A2A 两者都要（核心定位）

---

## 正在想的事（可以讨论，还没定）

- A2A 和 I2I 具体怎么配合
- 冷启动怎么做（3个问题太 low，但还没想到更好的）
- 语音通路怎么做（ASR/TTS 的具体实现）
- 数字遗产是不是现在该做

---

## 约束变了怎么办

告诉我不变，不要直接执行。

---

## 项目当前状态

```
Phase 0 ✅ 画像骨架
  aid init → aid collect chatgpt <zip> → aid profile show → 说"有了"

Phase 1 🔄 多源采集（当前）
  从"一个导入器"升级到"一套采集器框架"
  aid collect scan → aid collect list → 场景识别

Phase 2 ⏳ 思维复制与注入
  MCP Profile Server + 思维框架引擎 + 语音通路

Phase 3 ⏳ 关系网络 + 数字遗嘱
  I2I + A2A 完整闭环
```

---

## 关键设计原则

1. **Don't touch stable code** — 803+ 测试不能破
2. **只建缺失就会断的东西** — 不建"以后可能有用"的
3. **Graceful degradation** — 没 API key、没 GPU、没网络也能工作
4. **用户感受效果，不感受技术** — 用户不说"我的 DID"，说"它认识我"
5. **少就是多** — 700 行闭环比 1500 行半成品强

---

## 七框架（用于判断决策）

| 框架 | 含义 |
|:-----|:-----|
| 宇宙星链 | 点→线→面→球→超球，多维发散 |
| 第一性原理 | 压到本质再重建 |
| 反向推翻 | 假设自己错，找致命反例 |
| 递归降维 | 太复杂就降一层 |
| 反脆弱 | 波动让系统更强 |
| 节律控制 | 扩散↔收缩节奏 |
| 全息追溯 | 每个结论可溯源 |

---

## 代码约束

- Python 3.12+, pytest, ruff
- CLI: typer, 入口 `aid = "alpha_id.cli:app"`
- 核心逻辑在 `core/`，零外部依赖
- ❌ 禁止 LangChain / 改已有测试 / 版权头 / 改无关代码
- 每次改动前读 `decisions.md` 确认约束类型

---

> *Classification: Internal | Version 4.0.0 | 2026-06-08*
