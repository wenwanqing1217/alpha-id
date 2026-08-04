# Alpha-ID Projects

Alpha-ID 核心代码包。

- `src/` — 源代码（FastAPI + 业务逻辑）
- `pyproject.toml` — 依赖声明
- `.env` — 环境变量

## 脚本

```bash
pip install -e ".[mcp,fairy]"   # 安装含可选依赖
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## 测试

```bash
pytest tests/ -v
ruff check src/
```
