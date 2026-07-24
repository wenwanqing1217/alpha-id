"""
Token 撤销存储（文件后端，与存储后端解耦）

支持 JWT 令牌撤销/轮换：
- 记录已撤销的 jti（JWT ID）
- 自动清理过期条目（基于 exp 时间戳）
- 线程安全
"""

import json
import os
import tempfile
import threading
import time
from typing import Optional

# 默认存储路径
_DEFAULT_PATH = os.path.join(tempfile.gettempdir(), "alpha_id_revoked_tokens.json")


class TokenStore:
    """令牌撤销存储（文件后端）"""

    def __init__(self, store_path: Optional[str] = None):
        self._path = store_path or os.environ.get(
            "TOKEN_STORE_PATH", _DEFAULT_PATH
        )
        self._lock = threading.Lock()
        # 确保目录存在
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)

    def _read(self) -> dict:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def revoke(self, jti: str, exp: int):
        """撤销指定 jti（记录 exp 以便自动清理）"""
        with self._lock:
            store = self._read()
            store[jti] = {"exp": exp, "revoked_at": int(time.time())}
            self._write(store)

    def is_revoked(self, jti: str) -> bool:
        """检查 jti 是否已被撤销（自动清理过期条目）"""
        with self._lock:
            store = self._read()
            if jti not in store:
                return False
            entry = store[jti]
            # 如果令牌已过期，清理并返回 False
            if entry.get("exp", 0) < time.time():
                del store[jti]
                self._write(store)
                return False
            return True

    def rotate(self, old_jti: str, new_jti: str, new_exp: int):
        """轮换：撤销旧 jti，记录新 jti"""
        with self._lock:
            store = self._read()
            # 撤销旧令牌
            store[old_jti] = {"exp": store.get(old_jti, {}).get("exp", int(time.time())), "revoked_at": int(time.time())}
            # 记录新令牌（非撤销，仅用于追踪）
            store[new_jti] = {"exp": new_exp, "revoked_at": 0}
            # 清理过期条目
            now = time.time()
            expired = [k for k, v in store.items() if v.get("exp", 0) < now]
            for k in expired:
                del store[k]
            self._write(store)

    def cleanup(self) -> int:
        """清理所有过期条目，返回清理数量"""
        with self._lock:
            store = self._read()
            now = time.time()
            expired = [k for k, v in store.items() if v.get("exp", 0) < now]
            for k in expired:
                del store[k]
            self._write(store)
            return len(expired)


# 模块级单例
_token_store: Optional[TokenStore] = None
_store_lock = threading.Lock()


def get_token_store() -> TokenStore:
    """获取全局 TokenStore 单例"""
    global _token_store
    if _token_store is None:
        with _store_lock:
            if _token_store is None:
                _token_store = TokenStore()
    return _token_store
