"""
cachetools 内存缓存层 — 为用户身份查找和记忆/知识查找提供 TTL 缓存。

- _user_cache: 用户身份查找缓存（500 条 / 5 分钟）
- _memory_cache: 记忆/知识查找缓存（200 条 / 1 分钟）
"""

import threading

from cachetools import TTLCache, cached

_user_cache = TTLCache(maxsize=500, ttl=300)
_memory_cache = TTLCache(maxsize=200, ttl=60)

_user_cache_lock = threading.Lock()
_memory_cache_lock = threading.Lock()


def _method_key(*args, **kwargs):
    return (args[1:], frozenset(kwargs.items()))


def cached_user_lookup(func):
    """用户身份查找缓存装饰器 — 跳过 self，按参数缓存结果。"""
    return cached(cache=_user_cache, key=_method_key, lock=_user_cache_lock)(func)


def cached_memory_lookup(func):
    """记忆/知识查找缓存装饰器 — 跳过 self，按参数缓存结果。"""
    return cached(cache=_memory_cache, key=_method_key, lock=_memory_cache_lock)(func)


def invalidate_user_cache(alpha_id: str):
    """清除指定 alpha_id 的用户缓存条目。"""
    with _user_cache_lock:
        keys_to_delete = []
        for key in _user_cache:
            if key[0] and key[0][0] == alpha_id:
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del _user_cache[key]


def clear_user_cache():
    """清空全部用户缓存。"""
    with _user_cache_lock:
        _user_cache.clear()


def clear_memory_cache():
    """清空全部记忆缓存。"""
    with _memory_cache_lock:
        _memory_cache.clear()