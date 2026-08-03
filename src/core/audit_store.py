"""
A2A 审计日志持久化存储 — SQLite 后端

继承 A2AAuditLog 的内存快速路径，同时将记录异步写入 SQLite，
确保服务重启后审计记录不丢失。

schema: ~/.alpha-id/audit_log.db (WAL 模式)
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class SqliteAuditStore:
    """SQLite 持久化审计日志存储

    线程安全，使用 WAL 模式，支持并发读写。
    表结构：audit_logs (id, timestamp, event, caller_agent_id, target_agent_id,
           skill, request_id, success, error, detail_json)
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            alpha_id_path = os.environ.get(
                "ALPHA_ID_PATH",
                os.path.expanduser("~/.alpha-id"),
            )
            os.makedirs(alpha_id_path, exist_ok=True)
            db_path = os.path.join(alpha_id_path, "audit_log.db")
        self.db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                event           TEXT    NOT NULL,
                caller_agent_id TEXT,
                target_agent_id TEXT,
                skill           TEXT,
                request_id      TEXT,
                success         INTEGER NOT NULL DEFAULT 1,
                error           TEXT,
                detail_json     TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_logs (timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_caller
            ON audit_logs (caller_agent_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_request
            ON audit_logs (request_id)
        """)
        conn.commit()
        conn.close()

    def record(self, **fields: Any) -> Optional[int]:
        """写入一条审计记录，返回自增 id（失败返回 None）"""
        try:
            conn = self._get_conn()
            ts = fields.get("timestamp") or datetime.now(timezone.utc).isoformat()
            detail = {k: v for k, v in fields.items() if k not in {
                "timestamp", "event", "caller_agent_id", "target_agent_id",
                "skill", "request_id", "success", "error",
            }}
            detail_json = json.dumps(detail, ensure_ascii=False, default=str) if detail else None
            cursor = conn.execute(
                """
                INSERT INTO audit_logs
                    (timestamp, event, caller_agent_id, target_agent_id,
                     skill, request_id, success, error, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    fields.get("event", ""),
                    fields.get("caller_agent_id"),
                    fields.get("target_agent_id"),
                    fields.get("skill"),
                    fields.get("request_id"),
                    1 if fields.get("success", True) else 0,
                    fields.get("error"),
                    detail_json,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception:
            # 审计日志写入失败不应阻塞主流程
            return None

    def list_records(
        self,
        caller_agent_id: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询审计记录（支持筛选 + 分页）"""
        conn = self._get_conn()
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params: List[Any] = []
        if caller_agent_id:
            query += " AND caller_agent_id = ?"
            params.append(caller_agent_id)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count(
        self,
        caller_agent_id: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> int:
        """统计审计记录数"""
        conn = self._get_conn()
        query = "SELECT COUNT(*) FROM audit_logs WHERE 1=1"
        params: List[Any] = []
        if caller_agent_id:
            query += " AND caller_agent_id = ?"
            params.append(caller_agent_id)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        cursor = conn.execute(query, params)
        return cursor.fetchone()[0]

    def prune(self, older_than_days: int = 90) -> int:
        """清理超过指定天数的审计记录，返回删除的行数"""
        conn = self._get_conn()
        cutoff = datetime.now(timezone.utc).isoformat()
        # 简单处理：用字符串比较（ISO 格式可排序）
        import datetime as dt
        cutoff_dt = datetime.now(timezone.utc) - dt.timedelta(days=older_than_days)
        cutoff = cutoff_dt.isoformat()
        cursor = conn.execute(
            "DELETE FROM audit_logs WHERE timestamp < ?",
            (cutoff,),
        )
        conn.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d.pop("detail_json", None)
        return d

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            with self._local.conn:
                pass
            self._local.conn.close()
            self._local.conn = None
