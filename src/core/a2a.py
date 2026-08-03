# -*- coding: utf-8 -*-
"""
A2A Protocol - Agent-to-Agent Communication

Real HTTP/WebSocket cross-Agent communication, replacing the local call_skill() mock.

Protocol:
  - Call:   POST /a2a/call
  - Discover: GET /a2a/discover
  - Register: POST /a2a/register
  - Health: GET /a2a/health

Security:
  - Ed25519 signature verification
  - Proof of Execution (PoE) for every execution
  - Optional TLS encryption
"""
import json
import logging
import time
import uuid
import asyncio
from core.http_client import request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover
    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int = 500, detail: str = "") -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

logger = logging.getLogger(__name__)


# -- Data Models --

@dataclass
class A2ACallRequest:
    """A2A call request"""
    caller: str = ""
    target: str = ""
    skill: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    proof: str = ""  # Ed25519 signature (hex)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def signable_bytes(self) -> bytes:
        """Generate signable data (without proof field)"""
        data = {
            "caller": self.caller,
            "target": self.target,
            "skill": self.skill,
            "params": self.params,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
        }
        return json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")


@dataclass
class A2ACallResponse:
    """A2A call response"""
    success: bool = True
    result: Any = None
    error: str = ""
    request_id: str = ""
    executor: str = ""
    proof: str = ""
    timestamp: float = field(default_factory=time.time)
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "request_id": self.request_id,
            "executor": self.executor,
            "proof": self.proof,
            "timestamp": self.timestamp,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class A2AAgentInfo:
    """Agent registration info"""
    did: str
    agent_id: str = ""
    endpoint: str = ""
    skills: List[str] = field(default_factory=list)
    public_key_hex: str = ""
    status: str = "online"
    last_seen: float = field(default_factory=time.time)
    alpha_id: str = ""
    capability_card: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["agent_id"] = self.did
        return payload


# -- A2A Governance Models --


@dataclass
class A2ARegisterRequest:
    """Register an Agent into the runtime governance registry."""

    agent_id: str = ""
    did: str = ""
    endpoint: str = ""
    public_key_hex: str = ""
    skill_list: List[str] = field(default_factory=list)
    permission_scope: List[str] = field(default_factory=list)
    call_constraint: Dict[str, Any] = field(default_factory=dict)
    memory_policy: str = "write_summary"


@dataclass
class A2ARegisterResponse:
    """Registration response."""

    success: bool = True
    agent_id: str = ""
    message: str = "registered"
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class A2ADiscoverResponse:
    """Discovery response."""

    success: bool = True
    agent: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class A2AAuditFilter:
    """Audit query filter."""

    caller_agent_id: str = ""
    target_agent_id: str = ""
    skill: str = ""


# -- Registry --


# -- Skill Registry --

class A2ASkillRegistry:
    """
    A2A Skill registry - manages skills exposed by this Agent for A2A protocol.

    Usage:
        registry = A2ASkillRegistry()

        @registry.skill("greet")
        def greet(params):
            return f"Hello, {params.get('name', 'World')}!"

        registry.execute("greet", {"name": "Alice"})
    """

    def __init__(self):
        self._skills: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, name: str, func: Callable, description: str = ""):
        """Register a skill"""
        self._skills[name] = func
        self._descriptions[name] = description or (func.__doc__ or "")

    def skill(self, name: str, description: str = ""):
        """Decorator to register a skill"""
        def decorator(func: Callable) -> Callable:
            self.register(name, func, description)
            return func
        return decorator

    def execute(self, name: str, params: Dict[str, Any]) -> Any:
        """Execute a skill (sync functions only)"""
        func = self._skills.get(name)
        if func is None:
            raise ValueError(f"Skill not found: {name}")
        return func(params)

    async def execute_async(self, name: str, params: Dict[str, Any]) -> Any:
        """Execute a skill (supports both sync and async functions)

        For async skills (e.g. ghost.sample.fetch), this properly awaits
        the coroutine instead of blocking the event loop with asyncio.run().
        """
        func = self._skills.get(name)
        if func is None:
            raise ValueError(f"Skill not found: {name}")
        if asyncio.iscoroutinefunction(func):
            return await func(params)
        return func(params)

    def list_skills(self) -> List[Dict[str, str]]:
        """List all skills"""
        return [
            {"name": name, "description": self._descriptions.get(name, "")}
            for name in self._skills
        ]

    def has_skill(self, name: str) -> bool:
        return name in self._skills


class A2AAuditLog:
    """A2A governance audit log with dual-layer storage.

    Fast path: in-memory list with automatic rotation (O(1) append, FIFO eviction).
    Persistent path: optional SqliteAuditStore for crash-safe, restart-surviving records.
    When a store is provided, every record() call writes to both layers.
    list_records() prefers the persistent store when available.
    """

    def __init__(
        self,
        max_size: int = 10000,
        store: Optional["SqliteAuditStore"] = None,
    ) -> None:
        self._records: List[Dict[str, Any]] = []
        self._max_size = max_size
        self._store = store

    def record(self, **fields: Any) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        # 内存快速路径
        self._records.append(entry)
        if len(self._records) > self._max_size:
            self._records = self._records[-self._max_size // 2:]
        # 持久化路径（不阻塞主流程）
        if self._store is not None:
            try:
                self._store.record(**entry)
            except Exception:
                pass
        return entry

    def list_records(
        self,
        caller_agent_id: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        # 优先从持久化存储查询（支持筛选、分页）
        if self._store is not None:
            return self._store.list_records(
                caller_agent_id=caller_agent_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )
        # 降级：内存查询
        if caller_agent_id:
            return [r for r in self._records if r.get("caller_agent_id") == caller_agent_id]
        return list(self._records)

    def count(
        self,
        caller_agent_id: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> int:
        if self._store is not None:
            return self._store.count(
                caller_agent_id=caller_agent_id,
                start_time=start_time,
                end_time=end_time,
            )
        if caller_agent_id:
            return sum(1 for r in self._records if r.get("caller_agent_id") == caller_agent_id)
        return len(self._records)


class A2APermissionDenied(Exception):
    """Raised when caller is not allowed to invoke the requested skill."""


class A2ARegistry:
    """In-memory A2A agent registry with capability discovery."""

    def __init__(self) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}

    def register_agent(self, agent_info: A2AAgentInfo) -> Dict[str, Any]:
        payload = agent_info.to_dict()
        self._agents[agent_info.did] = payload
        return payload

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        if agent_id not in self._agents:
            raise HTTPException(status_code=404, detail="agent not found")
        return self._agents[agent_id]

    def list_agents(self) -> List[Dict[str, Any]]:
        return list(self._agents.values())

    def authorize_call(self, caller: str, target: str, skill: str) -> Dict[str, Any]:
        target_agent = self.get_agent(target)
        allowed_skills = target_agent.get("skill_list", [])
        if skill not in allowed_skills:
            raise A2APermissionDenied(f"skill not allowed: {skill}")
        return target_agent

    def record_agent_call(self, agent_id: str, success: bool) -> None:
        entry = self._agents.get(agent_id)
        if not entry:
            return
        counts = entry.setdefault("call_counts", {"total": 0, "success": 0, "failure": 0})
        counts["total"] += 1
        counts["success" if success else "failure"] += 1
        entry["last_seen"] = time.time()

    def to_payload(self) -> Dict[str, Any]:
        return {"agents": list(self._agents.values())}


# -- Signature Verification --

class A2ASigner:
    """
    A2A signature verification - Ed25519 signatures.

    Prefers nacl (PyNaCl), falls back to pure Python HMAC.
    """

    def __init__(self, private_key_hex: str = "", public_key_hex: str = ""):
        self._private_key_hex = private_key_hex
        self._public_key_hex = public_key_hex
        self._signer = None
        self._verify_key = None

        if private_key_hex:
            try:
                from nacl.signing import SigningKey
                self._signer = SigningKey(bytes.fromhex(private_key_hex))
            except ImportError:
                raise ImportError(
                    "PyNaCl is required for A2A signing. "
                    "Install with: pip install pynacl"
                )

        if public_key_hex:
            try:
                from nacl.signing import VerifyKey
                self._verify_key = VerifyKey(bytes.fromhex(public_key_hex))
            except ImportError:
                raise ImportError(
                    "PyNaCl is required for A2A verification. "
                    "Install with: pip install pynacl"
                )

    def sign(self, data: bytes) -> str:
        """Sign data with Ed25519, return hex signature.
        
        Raises:
            RuntimeError: If no signer is available (PyNaCl not installed).
        """
        if not self._signer:
            raise RuntimeError(
                "A2A signing unavailable: PyNaCl is required. "
                "Install with: pip install pynacl"
            )
        return self._signer.sign(data).signature.hex()

    def verify(self, data: bytes, signature_hex: str, public_key_hex: str = "") -> bool:
        """Verify Ed25519 signature.
        
        Args:
            data: Original signed data
            signature_hex: Hex-encoded Ed25519 signature
            public_key_hex: Sender's public key (overrides instance key)
            
        Returns:
            True if signature is valid
        """
        pk = public_key_hex or self._public_key_hex
        if not pk:
            return False

        try:
            from nacl.signing import VerifyKey
            verify_key = VerifyKey(bytes.fromhex(pk))
            verify_key.verify(data, bytes.fromhex(signature_hex))
            return True
        except Exception:
            return False

    @staticmethod
    def generate_keypair() -> tuple:
        """Generate Ed25519 keypair, return (private_key_hex, public_key_hex).
        
        Raises:
            ImportError: If PyNaCl is not installed.
        """
        try:
            from nacl.signing import SigningKey
            import os
            sk = SigningKey(os.urandom(32))
            return sk.encode().hex(), sk.verify_key.encode().hex()
        except ImportError:
            raise ImportError(
                "PyNaCl is required for A2A key generation. "
                "Install with: pip install pynacl"
            )


# -- A2A Server (DEPRECATED) --
# A2AServer 作为独立 FastAPI app 运行的时代已经结束。
# 2026-08-03 重构后，A2A 端点通过 api/a2a.py 的 APIRouter 集成到 main.py 路由系统。
# 本类保留作为参考实现，包含端点逻辑和防护代码的原始版本。
# 如无特殊需求，不应再实例化 A2AServer。
#
# 迁移路径:
#   旧: A2AServer(skills=..., signer=..., port=9001).start(blocking=False)
#   新: app.state.a2a_state = {skills, registry, audit, signer, ...} + a2a_router

class A2AServer:
    """
    A2A Server - receives call requests from other Agents.

    Usage:
        server = A2AServer(agent=my_agent, skills=registry, signer=signer, port=9001)
        server.start()
    """

    # Replay protection: deque with max size for FIFO eviction
    MAX_REQUEST_AGE = 300  # 5 minutes
    _replay_cache_size = 10000

    def __init__(
        self,
        agent=None,
        skills: Optional[A2ASkillRegistry] = None,
        signer: Optional[A2ASigner] = None,
        did: str = "",
        alpha_id: str = "",
        port: int = 9001,
        host: str = "localhost",
    ):
        self._agent = agent
        self._skills = skills or A2ASkillRegistry()
        self._signer = signer
        self._did = did
        self._alpha_id = alpha_id
        self._port = port
        self._host = host
        self._app = None
        # Replay protection: ordered list of (caller, request_id) for FIFO eviction
        self._seen_requests: list = []

    def _build_app(self):
        """Build FastAPI application"""
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel, Field

        app = FastAPI(title=f"A2A Agent: {self._alpha_id}", version="1.0")

        registry = A2ARegistry()
        audit = A2AAuditLog()

        class _RegisterBody(BaseModel):
            agent_id: str = Field("", description="Agent ID (or did)")
            did: str = Field("", description="DID")
            endpoint: str = Field("", description="Agent endpoint")
            public_key_hex: str = Field("", description="Public key hex")
            skill_list: List[str] = Field(default_factory=list)
            permission_scope: List[str] = Field(default_factory=list)
            call_constraint: Dict[str, Any] = Field(default_factory=dict)
            memory_policy: str = Field("write_summary")

        class _AuditQuery(BaseModel):
            caller_agent_id: str = Field("", description="Filter by caller")
            target_agent_id: str = Field("", description="Filter by target")
            skill: str = Field("", description="Filter by skill name")

        @app.post("/a2a/call")
        async def handle_call(request: Request):  # type: ignore[no-redef]
            """Handle A2A call (with replay protection + governance)"""
            body = await request.json()
            call_req = A2ACallRequest(**{k: v for k, v in body.items() if k in A2ACallRequest.__dataclass_fields__})

            # --- Replay protection ---
            if abs(time.time() - call_req.timestamp) > A2AServer.MAX_REQUEST_AGE:
                return JSONResponse(
                    A2ACallResponse(success=False, error="Request expired (replay?)", request_id=call_req.request_id).to_dict(),
                    status_code=401,
                )
            replay_key = (call_req.caller, call_req.request_id)
            if replay_key in self._seen_requests:
                return JSONResponse(
                    A2ACallResponse(success=False, error="Duplicate request (replay)", request_id=call_req.request_id).to_dict(),
                    status_code=401,
                )
            self._seen_requests.append(replay_key)
            # FIFO eviction: keep only the most recent entries
            if len(self._seen_requests) > A2AServer._replay_cache_size:
                self._seen_requests = self._seen_requests[-A2AServer._replay_cache_size // 2:]

            if self._signer and call_req.proof:
                if not self._signer.verify(call_req.signable_bytes(), call_req.proof):
                    return JSONResponse(
                        A2ACallResponse(success=False, error="Signature verification failed", request_id=call_req.request_id).to_dict(),
                        status_code=401,
                    )

            auth_scope = [s.strip() for s in (call_req.params.get("auth", {}).get("scope") or []) if str(s).strip()]
            try:
                registry.authorize_call(caller=call_req.caller, target=call_req.target, skill=call_req.skill)
            except A2APermissionDenied as exc:
                audit.record(
                    event="permission_denied",
                    caller_agent_id=call_req.caller,
                    target_agent_id=call_req.target,
                    skill=call_req.skill,
                    request_id=call_req.request_id,
                    error=str(exc),
                )
                return JSONResponse(
                    A2ACallResponse(success=False, error=str(exc), request_id=call_req.request_id).to_dict(),
                    status_code=403,
                )

            start = time.time()
            try:
                result = self._skills.execute(call_req.skill, call_req.params)
                elapsed = (time.time() - start) * 1000
                proof = ""
                if self._signer:
                    proof_data = json.dumps({"request_id": call_req.request_id, "result": str(result)}, sort_keys=True).encode()
                    proof = self._signer.sign(proof_data)
                audit.record(
                    event="call_completed",
                    caller_agent_id=call_req.caller,
                    target_agent_id=call_req.target,
                    skill=call_req.skill,
                    request_id=call_req.request_id,
                    success=True,
                    auth_scope=auth_scope,
                )
                registry.record_agent_call(self._did, success=True)
                return JSONResponse(
                    A2ACallResponse(
                        success=True,
                        result=result,
                        request_id=call_req.request_id,
                        executor=self._did,
                        proof=proof,
                        execution_time_ms=elapsed,
                    ).to_dict(),
                    status_code=200,
                )
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                audit.record(
                    event="call_completed",
                    caller_agent_id=call_req.caller,
                    target_agent_id=call_req.target,
                    skill=call_req.skill,
                    request_id=call_req.request_id,
                    success=False,
                    error=str(e),
                )
                registry.record_agent_call(self._did, success=False)
                return JSONResponse(
                    A2ACallResponse(
                        success=False,
                        error=str(e),
                        request_id=call_req.request_id,
                        executor=self._did,
                        execution_time_ms=elapsed,
                    ).to_dict(),
                    status_code=500,
                )

        @app.get("/a2a/discover")
        async def discover():
            """Discovery endpoint - return this Agent's info and all registered agents"""
            agents = registry.list_agents()
            return A2ADiscoverResponse(
                success=True,
                agent={
                    "self": A2AAgentInfo(
                        did=self._did,
                        alpha_id=self._alpha_id,
                        endpoint=f"http://{self._host}:{self._port}",
                        skills=[s["name"] for s in self._skills.list_skills()],
                        status="online",
                        last_seen=time.time(),
                    ).to_dict(),
                    "registered": agents,
                },
            ).to_dict()

        @app.get("/a2a/health")
        async def health():
            """Health check"""
            return {"status": "ok", "did": self._did, "alpha_id": self._alpha_id}

        @app.post("/a2a/register")
        async def register_agent(body: _RegisterBody):  # type: ignore[no-redef]
            if not body.agent_id and not body.did:
                raise HTTPException(status_code=400, detail="agent_id or did is required")
            agent_id = body.agent_id or body.did
            info = A2AAgentInfo(
                did=agent_id,
                agent_id=agent_id,
                endpoint=body.endpoint,
                public_key_hex=body.public_key_hex,
                skills=body.skill_list,
                capability_card={
                    "permission_scope": body.permission_scope,
                    "call_constraint": body.call_constraint,
                    "memory_policy": body.memory_policy,
                },
            )
            registry.register_agent(info)
            audit.record(event="register", agent_id=agent_id)
            return A2ARegisterResponse(success=True, agent_id=agent_id, message="registered").to_dict()

        @app.get("/a2a/agents")
        async def list_agents():
            return registry.to_payload()

        @app.get("/a2a/audit")
        async def list_audit(query: _AuditQuery = ...):  # type: ignore[no-redef]
            records = audit.list_records()
            if query.caller_agent_id:
                records = [r for r in records if r.get("caller_agent_id") == query.caller_agent_id]
            if query.target_agent_id:
                records = [r for r in records if r.get("target_agent_id") == query.target_agent_id]
            if query.skill:
                records = [r for r in records if r.get("skill") == query.skill]
            return {"records": records, "total": len(records)}

        @app.get("/a2a/skills")
        async def list_skills():
            """List all skills"""
            return self._skills.list_skills()

        return app
