# /test — 快速运行 Alpha-ID 测试

运行全部测试（首次失败即停止，跳过冗长输出）：
```
python -m pytest D:\MW\alphaid\projects\tests\ -q --tb=short -x
```

运行指定测试文件：
```
python -m pytest D:\MW\alphaid\projects\tests\test_xxx.py -q --tb=short
```

运行用户故事测试（P0 核心）：
```
python -m pytest D:\MW\alphaid\projects\tests\test_user_stories.py -q --tb=short -v
```

运行带覆盖率：
```
python -m pytest D:\MW\alphaid\projects\tests\ -q --tb=short --cov=src --cov-report=term-missing
```
