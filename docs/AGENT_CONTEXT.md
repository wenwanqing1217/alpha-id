---
id: AID-CTX-001
title: Alpha-ID Agent Context
version: 5.0.0
status: Active
last_reviewed: 2026-07-06
effective: 2026-07-06
---

# Alpha-ID — Agent Context

> 当前生效上下文。以本文件、`decisions.md`、`TODO.md` 为准；旧 archive 仅作历史参考。
> 过时约束已明确废除，不再自动生效。

---

## 当前入口文档

| 文档 | 用途 |
|------|------|
| **AGENT_CONTEXT.md**（本文件） | 当前定位、约束、Phase |
| **decisions.md** | 已确认决策，旧结论可被当前 Phase 覆盖 |
| **TODO.md** | 当前在做什么、下一步、阻塞点 |

冲突时以**今天的执行现实**为准，不自动服从历史文档。

---

## 项目定位

把散落在数字世界里的你捡起来——收集、重组、延续，让它替你活着、替你社交、替你学习。

Ghost Layer：坐在所有 AI 工具上面的那一层。

---

## 当前聚焦

- 先做完整链路：`aid init → aid profile mine --path . → aid profile show → aid profile web → aid-mcp`
- 再做画像质量：confidence / provenance / completeness / privacy scrubbing
- 保留全系统愿景：DID / I2I / A2A / 双大脑 / 模拟盘 / MCP 注入

---

## 当前暂缓

- 当前阶段不做模型、不做平台、不造协议（聚焦核心能力）
- 多源采集器暂缓（P1 再扩展）
- Computer Use Plan/Safety 层暂缓（先做 Skill 层）

---

## 保留红线

- 私钥永远在客户端，不上传
- DID 对用户无意义，藏在体验下面
- I2I + A2A 两者都要（核心定位）

---

## 当前议题

- 画像置信度、完整度、脱敏策略
- mining 层如何扩展为多源采集器
- Web / MCP / A2A 的接入顺序
- 语音通路是否进入 Phase 1

---

## 约束变了怎么办

可以直接重新评估；历史好决策不等于今天的硬规则。

---

## 项目当前状态

```
Phase 0 ✅ 画像骨架
  aid init → aid collect chatgpt <zip> → aid profile show

Phase 1 🔄 完整链路（当前）
  aid profile mine --path . → aid profile show → aid profile web → aid-mcp

Phase 2 ⏳ 稳定扩展
  Claude / Cursor / Git / Browser 扩展 + 测试基线修复

Phase 3 ⏳ 生态
  双大脑拆分、因果图谱、A2A、数字遗产
```

---

## 关键设计原则

1. **Don't touch stable code** — 803+ 测试不能破
2. **只建缺失就会断的东西** — 不建“以后可能有用”的
3. **Graceful degradation** — 没 API key、没 GPU、没网络也能工作
4. **用户感受效果，不感受技术** — 用户不说“我的 DID”，说“它认识我”
5. **少就是多** — 700 行闭环比 1500 行半成品强
6. **过时约束可废除** — 过去的好决策不代表现在是硬规则
7. **完整系统优先** — 先做可演示的完整链路，不做最小 demo

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
- 优先保持 `core/` 稳定性，不为了新功能盲目加依赖
- 测试策略：优先新增回归测试，再按需修正旧测试
- 依赖/框架引入：允许重新评估，不自动沿用旧禁令
- 每次改动前以 `decisions.md` 和 `TODO.md` 为准
