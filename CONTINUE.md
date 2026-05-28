# 继续

用户说「继续」时，执行以下步骤：

## 1. 读上下文

```bash
cat ROADMAP.md
```

## 2. 确认当前状态

```bash
cd /d D:\Software\AID\projects
python -m pytest tests/ -q
```

## 3. 开始 Phase 1

从 P1-1 开始，按 ROADMAP.md 顺序执行：

### P1-1 ReAct Agent
- 新建 `src/core/agent_react.py`
- 修改 `src/core/twin_brain.py`

### P1-2 向量记忆
- 修改 `src/core/memory_store.py`

### P1-3 数据库加密
- 修改 `src/core/storage_sqlite.py`

### P1-4 ML 风控
- 修改 `src/core/risk_engine.py`

### P1-5 CLI 工具
- 新建 `src/alpha_id/cli.py`

### P1-6 演示 Web App
- 新建 `src/alpha_id/web.py`

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
- Phase 1 进度: 0/6 ✅
- 当前评分: 2.7/5.0
- 上次操作: 创建 ROADMAP.md 和 CONTINUE.md
- 日期: 2025-06-28
