"""
Alpha-ID 豆包数据采集器 — 从豆包历史对话中提取数据
===================================================
支持多种数据入口：
  1. 豆包桌面端 LevelDB（现有 doubao_reader 兼容）
  2. 豆包导出文件（JSON/TXT）
  3. 手动粘贴文本
  4. 豆包网页版（浏览器 Agent，未来）

设计原则：
  - 采集器只管"拿原始文本"，不做分析
  - 分析统一交给 LLMEnricher
  - 数据立刻归本地
"""

import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DoubaoCollector:
    """
    豆包数据采集器 — 多种入口，统一输出。
    
    输出格式：
      [{"text": "对话内容", "source": "doubao", "timestamp": "...", "session_id": "..."}]
    """

    def __init__(self):
        self.collected_count = 0

    def collect(self, method: str = "auto", **kwargs) -> List[Dict[str, str]]:
        """
        统一采集入口。
        
        Args:
            method: 采集方式
              - "auto": 自动检测可用方式
              - "leveldb": 从豆包桌面端 LevelDB 读取
              - "export": 从导出文件读取
              - "manual": 手动输入/粘贴文本
              - "directory": 从目录批量读取文本文件
              
        Returns:
            统一格式的对话列表
        """
        if method == "auto":
            return self._auto_detect()

        handlers = {
            "leveldb": self._from_leveldb,
            "export": self._from_export,
            "manual": self._from_manual,
            "directory": self._from_directory,
        }

        handler = handlers.get(method)
        if not handler:
            raise ValueError(f"未知采集方式: {method}，可选: {list(handlers.keys())}")

        return handler(**kwargs)

    def _auto_detect(self) -> List[Dict[str, str]]:
        """自动检测可用数据源"""
        # 优先级：LevelDB > 导出文件 > 目录批量
        if self._leveldb_path():
            logger.info("检测到豆包 LevelDB，使用 leveldb 模式")
            return self._from_leveldb()

        export_files = self._find_export_files()
        if export_files:
            logger.info("检测到 %d 个导出文件，使用 export 模式", len(export_files))
            return self._from_export(files=export_files)

        logger.warning("未检测到任何豆包数据源，请手动提供")
        return []

    # ─── 方式 1: LevelDB（桌面端） ────────────────────────────────

    def _leveldb_path(self) -> Optional[Path]:
        """定位豆包桌面端 LevelDB"""
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Doubao" / "User Data" / "Default" / "Local Storage" / "leveldb",
            Path(os.environ.get("LOCALAPPDATA", "")) / "豆包" / "User Data" / "Default" / "Local Storage" / "leveldb",
            Path.home() / "AppData" / "Local" / "Doubao" / "User Data" / "Default" / "Local Storage" / "leveldb",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    def _from_leveldb(self, **kwargs) -> List[Dict[str, str]]:
        """从 LevelDB 提取对话（兼容现有 doubao_reader）"""
        leveldb_path = self._leveldb_path()
        if not leveldb_path:
            logger.error("未找到豆包 LevelDB 目录")
            return []

        # 尝试使用现有 doubao_reader
        try:
            sys_path = str(Path(__file__).resolve().parents[3])
            if sys_path not in os.sys.path:
                os.sys.path.insert(0, sys_path)
            from doubao_reader.log_reader import LogReader

            reader = LogReader()
            convs = reader.read_all()
            results = []
            for conv in convs:
                payload = conv.to_dict()
                messages = payload.get("messages", [])
                if not messages:
                    continue
                text = self._messages_to_text(messages)
                if len(text) > 50:
                    results.append({
                        "text": text,
                        "source": "doubao_leveldb",
                        "timestamp": payload.get("captured_at", ""),
                        "session_id": payload.get("session_id", ""),
                    })
            self.collected_count = len(results)
            logger.info("LevelDB 采集完成: %d 条对话", len(results))
            return results

        except ImportError:
            logger.warning("doubao_reader 不可用，尝试直接读取 LevelDB")
            return self._read_leveldb_direct(leveldb_path)

    def _read_leveldb_direct(self, path: Path) -> List[Dict[str, str]]:
        """直接读取 LevelDB（备用方案）"""
        results = []
        try:
            db = sqlite3.connect(str(path / "CURRENT" / "LOG") if (path / "CURRENT").exists() else str(path))
            # LevelDB 是 key-value 存储，需要遍历
            # 这里简化处理：尝试读取常见的 key 模式
            cursor = db.cursor()
            try:
                cursor.execute("SELECT key, value FROM entries")
                for key, value in cursor.fetchall():
                    try:
                        text = value.decode("utf-8", errors="ignore")
                        if len(text) > 100:
                            results.append({
                                "text": text[:5000],
                                "source": "doubao_leveldb_raw",
                                "timestamp": "",
                                "session_id": key.decode("utf-8", errors="ignore")[:32],
                            })
                    except Exception:
                        continue
            except Exception:
                pass
            db.close()
        except Exception as e:
            logger.error("直接读取 LevelDB 失败: %s", e)

        self.collected_count = len(results)
        return results

    # ─── 方式 2: 导出文件 ─────────────────────────────────────────

    def _find_export_files(self) -> List[Path]:
        """搜索可能的导出文件"""
        search_dirs = [
            Path.home() / "Downloads",
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / ".alpha-id",
        ]
        patterns = ["*豆包*", "*doubao*", "*对话*", "*chat*"]
        found = []
        for d in search_dirs:
            if not d.exists():
                continue
            for pat in patterns:
                found.extend(d.glob(pat))
        return [f for f in found if f.suffix in (".json", ".txt", ".md", ".zip")]

    def _from_export(self, files: Optional[List[Path]] = None, **kwargs) -> List[Dict[str, str]]:
        """从导出文件读取"""
        if files is None:
            files = self._find_export_files()

        results = []
        for f in files:
            try:
                if f.suffix == ".json":
                    results.extend(self._parse_json_file(f))
                elif f.suffix in (".txt", ".md"):
                    results.extend(self._parse_text_file(f))
                elif f.suffix == ".zip":
                    results.extend(self._parse_zip_file(f))
            except Exception as e:
                logger.warning("解析文件 %s 失败: %s", f, e)

        self.collected_count = len(results)
        logger.info("导出文件采集完成: %d 条对话（来自 %d 个文件）", len(results), len(files))
        return results

    def _parse_json_file(self, path: Path) -> List[Dict[str, str]]:
        """解析 JSON 格式导出"""
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)

        conversations = []
        if isinstance(data, list):
            conversations = data
        elif isinstance(data, dict):
            conversations = data.get("conversations", data.get("data", [data]))

        results = []
        for conv in conversations:
            messages = conv.get("messages", conv.get("chat_messages", []))
            if not messages:
                continue
            text = self._messages_to_text(messages)
            if len(text) > 50:
                results.append({
                    "text": text,
                    "source": "doubao_export",
                    "timestamp": conv.get("create_time", conv.get("timestamp", "")),
                    "session_id": conv.get("id", conv.get("session_id", "")),
                })
        return results

    def _parse_text_file(self, path: Path) -> List[Dict[str, str]]:
        """解析纯文本格式（每段对话用分隔线隔开）"""
        text = path.read_text(encoding="utf-8")
        # 尝试按常见分隔符拆分
        separators = ["\n---\n", "\n===\n", "\n\n\n", "---\n"]
        for sep in separators:
            if sep in text:
                chunks = [c.strip() for c in text.split(sep) if len(c.strip()) > 50]
                return [
                    {
                        "text": chunk,
                        "source": "doubao_text_export",
                        "timestamp": "",
                        "session_id": f"chunk_{i}",
                    }
                    for i, chunk in enumerate(chunks)
                ]

        # 没有分隔符 → 整文件作为一条
        if len(text) > 50:
            return [{"text": text, "source": "doubao_text_export", "timestamp": "", "session_id": "full"}]
        return []

    def _parse_zip_file(self, path: Path) -> List[Dict[str, str]]:
        """解析 ZIP 导出（跟 ChatGPT 导出类似）"""
        import zipfile

        results = []
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".json"):
                    data = json.loads(zf.read(name))
                    if isinstance(data, list):
                        for conv in data:
                            messages = conv.get("messages", [])
                            text = self._messages_to_text(messages)
                            if len(text) > 50:
                                results.append({
                                    "text": text,
                                    "source": "doubao_zip_export",
                                    "timestamp": conv.get("create_time", ""),
                                    "session_id": conv.get("id", ""),
                                })
        return results

    # ─── 方式 3: 手动输入 ─────────────────────────────────────────

    def _from_manual(self, text: str = "", **kwargs) -> List[Dict[str, str]]:
        """手动粘贴文本"""
        if not text:
            return []
        return [{"text": text, "source": "doubao_manual", "timestamp": "", "session_id": "manual"}]

    # ─── 方式 4: 目录批量 ─────────────────────────────────────────

    def _from_directory(self, directory: str = "", pattern: str = "*.txt", **kwargs) -> List[Dict[str, str]]:
        """从目录批量读取文本文件"""
        if not directory:
            directory = str(Path.home() / "Downloads")
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.error("目录不存在: %s", directory)
            return []

        results = []
        for f in dir_path.glob(pattern):
            try:
                text = f.read_text(encoding="utf-8")
                if len(text) > 50:
                    results.append({
                        "text": text,
                        "source": "doubao_directory",
                        "timestamp": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                        "session_id": f.stem,
                    })
            except Exception:
                continue

        self.collected_count = len(results)
        return results

    # ─── 工具方法 ─────────────────────────────────────────────────

    @staticmethod
    def _messages_to_text(messages: List[Dict]) -> str:
        """把消息列表转成纯文本（用于 LLM 分析）"""
        lines = []
        for msg in messages:
            role = msg.get("role", msg.get("sender", "unknown"))
            content = msg.get("content", msg.get("text", ""))

            # 处理 content 是 list 的情况（多模态消息）
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = " ".join(text_parts)

            if isinstance(content, str) and content.strip():
                role_label = {"user": "用户", "assistant": "AI", "human": "用户"}.get(role, role)
                lines.append(f"[{role_label}] {content}")

        return "\n".join(lines)
