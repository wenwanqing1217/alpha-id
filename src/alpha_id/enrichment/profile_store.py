"""
Alpha-ID 统一画像存储 — 本地 SQLite + 可读 Markdown
===================================================
把 LLM Enricher 的输出持久化到本地。

设计原则：
  - 结构化数据 → SQLite（可查询、可增量更新）
  - 人类可读 → Markdown 摘要
  - 原始证据 → JSON（可追溯）
  - 一切本地，不归任何第三方
  
存储结构：
  alpha_id.db
    ├── profile_core      (核心画像，合并后的最终结果)
    ├── enrich_history    (每次分析的历史记录)
    ├── conversations     (原始对话存档，可选)
    └── data_sources      (数据来源追踪)
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    """数据库路径（本地 Alpha-ID 目录）"""
    base = Path.home() / ".alpha-id"
    base.mkdir(parents=True, exist_ok=True)
    return base / "profile.db"


class ProfileStore:
    """
    统一画像存储 — 本地 SQLite。
    
    用法：
      store = ProfileStore()
      store.save_enrichment(result)      # 保存一次分析结果
      profile = store.get_merged_profile()  # 获取合并后的画像
      store.export_markdown()            # 导出人类可读的 Markdown
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db = db_path or _db_path()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS enrich_history (
                    id TEXT PRIMARY KEY,
                    analyzed_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    model TEXT,
                    input_length INTEGER,
                    result_json TEXT NOT NULL,
                    evidence_json TEXT
                );
                
                CREATE TABLE IF NOT EXISTS profile_core (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER DEFAULT 1
                );
                
                CREATE TABLE IF NOT EXISTS data_sources (
                    name TEXT PRIMARY KEY,
                    last_collected TEXT,
                    item_count INTEGER DEFAULT 0,
                    first_collected TEXT
                );
                
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    source TEXT,
                    text TEXT,
                    timestamp TEXT,
                    session_id TEXT,
                    imported_at TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_enrich_source ON enrich_history(source);
                CREATE INDEX IF NOT EXISTS idx_conv_source ON conversations(source);
            """)

    # ─── 核心操作 ─────────────────────────────────────────────────

    def save_enrichment(self, result: Dict[str, Any]) -> str:
        """
        保存一次 LLM 分析结果，并更新合并画像。
        
        Args:
            result: LLMEnricher.analyze() 的输出
            
        Returns:
            记录 ID
        """
        record_id = uuid.uuid4().hex[:16]
        meta = result.get("_meta", {})
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db) as conn:
            # 1. 保存原始分析记录
            conn.execute(
                """INSERT INTO enrich_history 
                   (id, analyzed_at, source, model, input_length, result_json, evidence_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    meta.get("analyzed_at", now),
                    meta.get("source", "unknown"),
                    meta.get("model", ""),
                    meta.get("input_length", 0),
                    json.dumps(result, ensure_ascii=False),
                    json.dumps(result.get("evidence", {}), ensure_ascii=False),
                ),
            )

            # 2. 更新合并画像
            self._merge_into_core(conn, result)

            # 3. 更新数据来源追踪
            source = meta.get("source", "unknown")
            existing = conn.execute(
                "SELECT item_count FROM data_sources WHERE name = ?", (source,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE data_sources SET last_collected = ?, item_count = item_count + 1 WHERE name = ?",
                    (now, source),
                )
            else:
                conn.execute(
                    "INSERT INTO data_sources (name, last_collected, item_count, first_collected) VALUES (?, ?, 1, ?)",
                    (source, now, now),
                )

        logger.info("分析结果已保存 (id=%s, source=%s)", record_id, meta.get("source"))
        return record_id

    def save_conversation(self, conv: Dict[str, str]) -> str:
        """
        保存原始对话（可选，用于追溯）。
        
        Args:
            conv: {"text": "...", "source": "...", "timestamp": "...", "session_id": "..."}
        """
        record_id = conv.get("session_id", uuid.uuid4().hex[:16])
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO conversations (id, source, text, timestamp, session_id, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    conv.get("source", "unknown"),
                    conv.get("text", ""),
                    conv.get("timestamp", ""),
                    conv.get("session_id", ""),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return record_id

    def get_merged_profile(self) -> Dict[str, Any]:
        """获取合并后的核心画像"""
        with sqlite3.connect(self.db) as conn:
            row = conn.execute("SELECT data_json FROM profile_core WHERE id = 1").fetchone()
            if row:
                return json.loads(row[0])
        return self._empty_profile()

    def get_enrich_history(self, limit: int = 50) -> List[Dict]:
        """获取分析历史"""
        with sqlite3.connect(self.db) as conn:
            rows = conn.execute(
                "SELECT id, analyzed_at, source, model, input_length FROM enrich_history ORDER BY analyzed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {"id": r[0], "analyzed_at": r[1], "source": r[2], "model": r[3], "input_length": r[4]}
                for r in rows
            ]

    def get_data_sources(self) -> List[Dict]:
        """获取数据来源统计"""
        with sqlite3.connect(self.db) as conn:
            rows = conn.execute(
                "SELECT name, last_collected, item_count, first_collected FROM data_sources ORDER BY item_count DESC"
            ).fetchall()
            return [
                {"name": r[0], "last_collected": r[1], "item_count": r[2], "first_collected": r[3]}
                for r in rows
            ]

    def export_markdown(self, output_path: Optional[Path] = None) -> Path:
        """
        导出人类可读的 Markdown 摘要。
        
        Returns:
            输出文件路径
        """
        profile = self.get_merged_profile()
        sources = self.get_data_sources()
        
        lines = [
            f"# Alpha-ID 画像报告",
            f"",
            f"> 生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"> 数据来源: {', '.join(s['name'] for s in sources)}",
            f"",
            f"---",
            f"",
        ]

        tech = profile.get("technical", {})
        if tech:
            lines.append("## 技术能力")
            lines.append("")
            
            if tech.get("languages"):
                lines.append("### 编程语言")
                for lang, level in tech["languages"].items():
                    bar = self._level_bar(level)
                    lines.append(f"- **{lang}**: {level} {bar}")
                lines.append("")

            if tech.get("frameworks"):
                lines.append("### 框架/库")
                lines.append(f"- {', '.join(tech['frameworks'])}")
                lines.append("")

            if tech.get("tools"):
                lines.append("### 工具")
                lines.append(f"- {', '.join(tech['tools'])}")
                lines.append("")

            if tech.get("domains"):
                lines.append("### 领域")
                lines.append(f"- {', '.join(tech['domains'])}")
                lines.append("")

            if tech.get("current_projects"):
                lines.append("### 当前项目")
                for proj in tech["current_projects"]:
                    lines.append(f"- {proj}")
                lines.append("")

            if tech.get("learning"):
                lines.append("### 正在学习")
                lines.append(f"- {', '.join(tech['learning'])}")
                lines.append("")

        comm = profile.get("communication", {})
        if any(comm.values()):
            lines.append("## 沟通风格")
            lines.append("")
            if comm.get("tone"):
                lines.append(f"- **语气**: {comm['tone']}")
            if comm.get("style"):
                lines.append(f"- **风格**: {comm['style']}")
            if comm.get("languages"):
                lines.append(f"- **语言**: {', '.join(comm['languages'])}")
            lines.append("")

        work = profile.get("work_pattern", {})
        if any(v for v in work.values() if v):
            lines.append("## 工作模式")
            lines.append("")
            if work.get("rhythm"):
                lines.append(f"- **节奏**: {'夜猫子' if work['rhythm'] == 'night_owl' else '日间型'}")
            if work.get("peak_hours"):
                lines.append(f"- **高峰时段**: {', '.join(f'{h:02d}:00' for h in work['peak_hours'][:5])}")
            if work.get("recent_focus"):
                lines.append(f"- **近期焦点**: {work['recent_focus']}")
            lines.append("")

        # 数据来源
        if sources:
            lines.append("## 数据来源")
            lines.append("")
            lines.append("| 来源 | 首次采集 | 最近采集 | 数量 |")
            lines.append("|------|---------|---------|------|")
            for s in sources:
                lines.append(f"| {s['name']} | {s['first_collected'][:10]} | {s['last_collected'][:10]} | {s['item_count']} |")
            lines.append("")

        # 证据
        evidence = profile.get("evidence", {})
        if evidence:
            lines.append("## 推断依据")
            lines.append("")
            for field, desc in evidence.items():
                lines.append(f"- **{field}**: {desc}")
            lines.append("")

        # 输出
        if not output_path:
            output_path = Path.home() / ".alpha-id" / "profile_report.md"
            output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Markdown 报告已导出: %s", output_path)
        return output_path

    # ─── 内部方法 ─────────────────────────────────────────────────

    def _merge_into_core(self, conn: sqlite3.Connection, result: Dict):
        """将新分析结果合并到核心画像"""
        # 读取现有画像
        row = conn.execute("SELECT data_json FROM profile_core WHERE id = 1").fetchone()
        if row:
            existing = json.loads(row[0])
        else:
            existing = self._empty_profile()

        # 合并
        merged = self._deep_merge(existing, result)
        now = datetime.now(timezone.utc).isoformat()

        # 保存
        conn.execute(
            """INSERT OR REPLACE INTO profile_core (id, data_json, updated_at, version)
               VALUES (1, ?, ?, COALESCE((SELECT version FROM profile_core WHERE id = 1), 0) + 1)""",
            (json.dumps(merged, ensure_ascii=False), now),
        )

    def _deep_merge(self, base: Dict, new: Dict) -> Dict:
        """深度合并两个画像 dict"""
        result = dict(base)

        for key, value in new.items():
            if key.startswith("_"):
                continue  # 跳过元数据

            if key not in result:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result[key], dict):
                result[key] = self._merge_dict_values(result[key], value)
            elif isinstance(value, list) and isinstance(result[key], list):
                result[key] = list(dict.fromkeys(result[key] + value))
            elif value is not None:
                result[key] = value  # 新值覆盖

        return result

    @staticmethod
    def _merge_dict_values(base: Dict, new: Dict) -> Dict:
        """合并熟练度字典（取最高值）"""
        result = dict(base)
        for k, v in new.items():
            if k not in result:
                result[k] = v
            elif v and not result[k]:
                result[k] = v
            # 两者都有 → 保留（不做复杂比较，简化逻辑）
        return result

    @staticmethod
    def _empty_profile() -> Dict[str, Any]:
        """空画像模板"""
        return {
            "technical": {
                "languages": {},
                "frameworks": [],
                "tools": [],
                "domains": [],
                "current_projects": [],
                "learning": [],
            },
            "communication": {"tone": None, "style": None, "languages": [], "sentence_length": None},
            "work_pattern": {"rhythm": None, "peak_hours": [], "commit_frequency": None, "recent_focus": None},
            "thinking": {"approach": None, "depth": None, "breadth": None},
            "evidence": {},
        }

    @staticmethod
    def _level_bar(level: str) -> str:
        """熟练度可视化"""
        value = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}.get(str(level).lower(), 0)
        return "█" * value + "░" * (4 - value)
