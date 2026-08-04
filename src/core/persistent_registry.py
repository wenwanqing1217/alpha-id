"""
A2A Agent 注册表持久化存储

提供两种后端：
1. FileRegistryStore — 文件持久化（默认，无需额外依赖）
2. RedisRegistryStore — Redis 持久化（可选，需要 redis-py）

注册表数据在服务重启后自动恢复，避免惊群效应。
每个 Agent 通过 TTL 心跳续约，超时自动淘汰。
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional


# ── 文件后端（默认）─────────────────────────────────────────


class FileRegistryStore:
    """基于 JSON 文件的 Agent 注册表持久化

    路径: ~/.alpha-id/a2a_registry.json
    线程安全，每次写入原子覆盖。
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            alpha_id_path = os.environ.get(
                "ALPHA_ID_PATH",
                os.path.expanduser("~/.alpha-id"),
            )
            os.makedirs(alpha_id_path, exist_ok=True)
            db_path = os.path.join(alpha_id_path, "a2a_registry.json")
        self.db_path = db_path
        self._lock = threading.Lock()

    def load(self) -> Dict[str, Dict[str, Any]]:
        """加载所有注册 Agent（已过期的除外）"""
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 过滤掉 TTL 过期的记录
            now = time.time()
            return {
                did: agent for did, agent in data.items()
                if agent.get("expires_at", 0) > now
            }
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self, agents: Dict[str, Dict[str, Any]]) -> None:
        """原子写入所有注册 Agent"""
        with self._lock:
            tmp_path = self.db_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(agents, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.db_path)

    def get(self, did: str) -> Optional[Dict[str, Any]]:
        data = self.load()
        return data.get(did)

    def set(self, did: str, agent: Dict[str, Any], ttl: int = 300) -> None:
        """写入单个 Agent，设置 TTL（秒）"""
        data = self.load()
        agent["expires_at"] = time.time() + ttl
        agent["updated_at"] = time.time()
        data[did] = agent
        self.save(data)

    def delete(self, did: str) -> None:
        data = self.load()
        data.pop(did, None)
        self.save(data)

    def prune_expired(self) -> int:
        """清理过期 Agent，返回删除的数量"""
        data = self.load()
        now = time.time()
        before = len(data)
        data = {did: a for did, a in data.items() if a.get("expires_at", 0) > now}
        self.save(data)
        return before - len(data)


# ── Redis 后端（可选）────────────────────────────────────────


class RedisRegistryStore:
    """基于 Redis 的 Agent 注册表持久化

    使用 Hash 存储 Agent 信息，Key 带 TTL 自动过期。
    需要 pip install redis。
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl: int = 300) -> None:
        try:
            import redis as redis_sync
            self._client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
            self._ttl = ttl
            self._prefix = "a2a:agent:"
            # 测试连接
            self._client.ping()
        except ImportError:
            raise ImportError("redis package required: pip install redis")
        except Exception as exc:
            raise RuntimeError(f"Redis connection failed: {exc}") from exc

    def load(self) -> Dict[str, Dict[str, Any]]:
        """加载所有未过期 Agent"""
        agents = {}
        for key in self._client.scan_iter(f"{self._prefix}*"):
            data = self._client.hgetall(key)
            if data:
                did = key[len(self._prefix):]
                agents[did] = {k: json.loads(v) for k, v in data.items()}
        return agents

    def save(self, agents: Dict[str, Dict[str, Any]]) -> None:
        for did, agent in agents.items():
            self.set(did, agent)

    def get(self, did: str) -> Optional[Dict[str, Any]]:
        key = f"{self._prefix}{did}"
        if not self._client.exists(key):
            return None
        data = self._client.hgetall(key)
        return {k: json.loads(v) for k, v in data.items()}

    def set(self, did: str, agent: Dict[str, Any], ttl: int = 0) -> None:
        key = f"{self._prefix}{did}"
        pipe = self._client.pipeline()
        for k, v in agent.items():
            pipe.hset(key, k, json.dumps(v, ensure_ascii=False, default=str))
        pipe.expire(key, ttl or self._ttl)
        pipe.execute()

    def delete(self, did: str) -> None:
        self._client.delete(f"{self._prefix}{did}")

    def prune_expired(self) -> int:
        # Redis TTL handles expiration automatically
        return 0


# ── 统一接口 ─────────────────────────────────────────────────


class PersistentA2ARegistry:
    """持久化 A2A 注册表

    包装 A2ARegistry，在内存操作的同时同步到持久化后端。
    支持 file（默认）和 redis 两种存储后端。

    用法:
        store = FileRegistryStore()
        registry = PersistentA2ARegistry(A2ARegistry(), store=store)
        # 与 A2ARegistry 接口完全兼容
        registry.register_agent(info)
        agent = registry.get_agent(did)
    """

    def __init__(self, registry: Any, store: Any, ttl: int = 300) -> None:
        self._registry = registry
        self._store = store
        self._ttl = ttl
        self._dirty = False  # 是否需要同步到后端

    # ── 代理 A2ARegistry 的所有方法 ──

    def register_agent(self, agent_info: Any) -> Dict[str, Any]:
        result = self._registry.register_agent(agent_info)
        try:
            self._store.set(agent_info.did, result, ttl=self._ttl)
        except Exception:
            pass
        return result

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        return self._registry.get_agent(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return self._registry.list_agents()

    def to_payload(self) -> Dict[str, Any]:
        """代理 to_payload 到内部 A2ARegistry"""
        return self._registry.to_payload()

    def authorize_call(self, caller: str, target: str, skill: str) -> Dict[str, Any]:
        return self._registry.authorize_call(caller, target, skill)

    def record_agent_call(self, agent_id: str, success: bool) -> None:
        self._registry.record_agent_call(agent_id, success)

    def unregister(self, agent_id: str) -> None:
        self._registry._agents.pop(agent_id, None)
        try:
            self._store.delete(agent_id)
        except Exception:
            pass

    # ── 持久化专属方法 ──

    def load_from_store(self) -> int:
        """从持久化后端恢复注册表，返回恢复的 Agent 数量"""
        try:
            data = self._store.load()
            count = 0
            for did, agent_data in data.items():
                from core.a2a import A2AAgentInfo
                try:
                    info = A2AAgentInfo(
                        did=agent_data.get("did", did),
                        endpoint=agent_data.get("endpoint", ""),
                        public_key_hex=agent_data.get("public_key_hex", ""),
                        skill_list=agent_data.get("skill_list", []),
                        permission_scope=agent_data.get("permission_scope", []),
                        call_constraint=agent_data.get("call_constraint", {}),
                        memory_policy=agent_data.get("memory_policy", "write_summary"),
                        alpha_id=agent_data.get("alpha_id", ""),
                    )
                    self._registry.register_agent(info)
                    count += 1
                except Exception:
                    continue
            return count
        except Exception:
            return 0

    def prune_expired(self) -> int:
        """清理持久化后端中过期的 Agent"""
        try:
            return self._store.prune_expired()
        except Exception:
            return 0
