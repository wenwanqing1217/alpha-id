# 继续

用户说「继续」时，执行以下步骤：

## 1. 读上下文

```bash
type ROADMAP.md
```

**重点关注：** 「前沿调研 & 关键洞察」章节（第 252 行起）—— 6 个洞察优化了原计划。

## 2. 确认当前状态

```bash
cd /d D:\Software\AID\projects
python -m pytest tests/ -q
```

## 3. Phase 1 执行顺序（已按前沿洞察优化）

| # | 模块 | 文件 | 核心改动 |
|---|------|------|---------|
| 1 | **最小 DID 实现** | `src/core/did.py` | Ed25519 密钥 + DID Document JSON（50 行） |
| 2 | **Agent：LLM+Tools+Loop** | `src/core/agent.py` | 简单循环，不依赖任何框架（<200 行） |
| 3 | **向量记忆（长期）** | `src/core/memory_store.py` | ChromaDB + 重要性过滤 |
| 4 | **Agent 接入 TwinBrain** | `src/core/twin_brain.py` | `think()` → Agent，Tool 注册 |
| 5 | **数据库加密** | `src/core/storage_sqlite.py` | Fernet 透明加解密 |
| 6 | **ML 风控增强** | `src/core/risk_engine.py` | IsolationForest + 特征工程 |
| 7 | **身份导出/导入** | `src/core/user_identity.py` | 签名 bundle + 验证 |
| 8 | **CLI 工具** | `src/alpha_id/cli.py` | Typer |
| 9 | **演示 Web App** | `src/alpha_id/web.py` | FastAPI + Jinja2 |
| — | 技术债务修复 | 多处 | numpy import, found_code 哈希, hardcoded sender |

**设计原则（来自 Anthropic / AT Protocol / W3C 前沿实践）：**
- Agent = 简单 `LLM + tools + loop`，不要框架
- Tool API 设计比 Prompt 更重要
- DID = 50 行 JSON，立即受益
- 记忆分两层：工作记忆（消息列表）+ 长期记忆（向量）

## 4. 每次修改后跑测试

```bash
python -m pytest tests/ -q
```

## 5. 全部通过后提交

```bash
git add -A && git commit -m "Phase 1: ..."
```

---

**状态记录：**
- Phase 1 进度: 0/9 ❌（核心 6 → 优化后 9 项）
- 当前评分: 2.7/5.0
- 上次操作: 前沿调研，优化路线图
- 日期: 2025-06-28
