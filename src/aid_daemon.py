"""
NURO Ghost — 启动入口（向后兼容）

用法：
  python src/aid_daemon.py [--check] [--no-mcp] [--no-brain] [--blind]

实际逻辑委托给 entrypoints.cli.main()
"""

import sys
import os

# 确保 src/ 在路径中（关键：add src/ 而非父目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from entrypoints.cli import main

if __name__ == "__main__":
    main()
