"""
Token 撤销存储（文件后端，与存储后端解耦）

支持 JWT 令牌撤销/轮换：
- 记录已撤销的 jti（JWT ID）
- 自动清理过期条目（基于 exp 时间戳）
- 线程安全 + 跨进程文件锁（防止多 worker 竞态）
"""

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Optional

from core.settings import settings

# 默认存储路径（可通过 settings.token_store_path 覆盖）
_DEFAULT_PATH = settings.token_store_path or os.path.join(tempfile.gettempdir(), "alpha_id_revoked_tokens.json")


class _FileLock:
    """跨进程文件锁（Windows: msvcrt / Unix: fcntl）"""

    def __init__(self, lock_path: str):
        self._lock_path = lock_path
        self._lock_file = None

    def acquire(self):
        os.makedirs(os.path.dirname(self._lock_path) or ".", exist_ok=True)
        self._lock_file = open(self._lock_path, "w")
        try:
            if os.name == "nt":
                # Windows: msvcrt 阻塞锁定（LK_LOCK 默认等待 10 秒后抛 OSError）
                # 注意：不能用 LK_NBLCK + while True 循环，同一进程重复锁定同一字节会
                # 持续 OSError 导致死循环（见 test_access_token_subject 卡死问题）
                import msvcrt
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                # Unix: fcntl 排他锁
                import fcntl
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)
        except Exception:
            # 锁定失败时仍继续（降级为仅线程锁）
            self._lock_file.close()
            self._lock_file = None

    def release(self):
        if self._lock_file:
            try:
                if os.name == "nt":
                    import msvcrt
                    self._lock_file.seek(0)
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_file.close()
                self._lock_file = None


@contextmanager
def _file_lock(lock_path: str):
    """文件锁上下文管理器"""
    fl = _FileLock(lock_path)
    fl.acquire()
    try:
        yield
    finally:
        fl.release()


class TokenStore:
    """令牌撤销存储（文件后端，线程安全 + 跨进程安全）"""

    def __init__(self, store_path: Optional[str] = None):
        self._path = store_path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._file_lock_path = self._path + ".lock"
        # 确保目录存在
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)

    def _read(self) -> dict:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict):
        # 原子写入：先写临时文件再重命名，防止写入过程中断导致数据损坏
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._path)

    def revoke(self, jti: str, exp: int):
        """撤销指定 jti（记录 exp 以便自动清理）"""
        with self._lock:
            with _file_lock(self._file_lock_path):
                store = self._read()
                store[jti] = {"exp": exp, "revoked_at": int(time.time())}
                self._write(store)

    def is_revoked(self, jti: str) -> bool:
        """检查 jti 是否已被撤销（自动清理过期条目）"""
        with self._lock:
            with _file_lock(self._file_lock_path):
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
            with _file_lock(self._file_lock_path):
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
            with _file_lock(self._file_lock_path):
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
