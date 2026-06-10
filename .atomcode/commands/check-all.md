# /check-all — 完整质量检查 (format → lint → pyright → test)

一键执行：
```
cd /d D:\Software\AID\projects && python -m ruff format src/ tests/ --check --quiet && python -m ruff check src/ --quiet && python -m pyright src/ && python -m pytest tests/ -q --tb=short
```

分步执行：
```
1. Format:  python -m ruff format src/ tests/ --quiet
2. Lint:    python -m ruff check src/ --quiet
3. Type:    python -m pyright src/
4. Test:    python -m pytest tests/ -q --tb=short
```
