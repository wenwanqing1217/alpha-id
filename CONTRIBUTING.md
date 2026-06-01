# AID 项目 — 贡献指南

## 开发环境

请先运行 `scripts\dev_setup.bat` 一键初始化。

详见 [DEVENV.md](../DEVENV.md)。

## 分支策略

```
master          → 稳定版本（只从 PR 合并）
feature/*       → 新功能
fix/*           → 修 Bug
refactor/*      → 重构
docs/*          → 文档
chore/*         → CI/依赖/杂项
```

## Commit 格式

```
<type>: <简短描述>

类型: feat / fix / docs / style / refactor / perf / test / chore
```

示例：
```
feat: 冷启动向导 — 首次运行自动创建身份
fix: 记忆查询返回空列表时的类型错误
```

pre-commit 会自动校验格式。详情见 `.pre-commit-config.yaml`。

## 提交前检查

```bash
task check-all
```

这条命令会自动运行：
1. `ruff format` — 格式化代码
2. `ruff check` — Lint 检查
3. `pyright` — 类型检查
4. `pytest` — 全部测试

## 测试规范

- 所有新功能必须有对应测试
- 测试放在 `tests/` 目录下
- 命名: `test_<模块名>.py`
- 覆盖率不低于 70%

```bash
# 只跑相关测试
python -m pytest tests/test_你的模块.py -q --tb=short

# 带覆盖率
python -m pytest tests/ -q --cov=src --cov-report=term-missing
```

## 代码风格

- 用 ruff 自动格式化（已在 pre-commit 中配置）
- 行宽: 120 字符
- 引号: 双引号
- 目标 Python: 3.12+
- 类型注解: 所有公开函数必须带类型注解

## 架构原则

1. **不改 525+ 已通过的测试代码** — 只新增文件
2. **优雅降级** — 没有 API Key 能跑、没有 GPU 能跑
3. **用户感知效果，不感知技术** — 不暴露 DID/Ed25519/PoE/MCP 等术语
4. **代码即文档** — 好代码不需要长篇注释
