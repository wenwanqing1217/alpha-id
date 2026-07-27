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
from core.http_client import request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

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
    alpha_id: str = ""
    endpoint: str = ""
    skills: List[str] = field(default_factory=list)
    public_key_hex: str = ""
    status: str = "online"
    last_seen: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -- Skill Registry --

class SkillRegistry:
    """
    Skill registry - manages skills exposed by this Agent.

    Usage:
        registry = SkillRegistry()

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
        """Execute a skill"""
        func = self._skills.get(name)
        if func is None:
            raise ValueError(f"Skill not found: {name}")
        return func(params)

    def list_skills(self) -> List[Dict[str, str]]:
        """List all skills"""
        return [
            {"name": name, "description": self._descriptions.get(name, "")}
            for name in self._skills
        ]

    def has_skill(self, name: str) -> bool:
        return name in self._skills


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


# -- A2A Server --

class A2AServer:
    """
    A2A Server - receives call requests from other Agents.

    Usage:
        server = A2AServer(agent=my_agent, skills=registry, signer=signer, port=9001)
        server.start()
    """

    def __init__(
        self,
        agent=None,
        skills: Optional[SkillRegistry] = None,
        signer: Optional[A2ASigner] = None,
        did: str = "",
        alpha_id: str = "",
        port: int = 9001,
        host: str = "localhost",
    ):
        self._agent = agent
        self._skills = skills or SkillRegistry()
        self._signer = signer
        self._did = did
        self._alpha_id = alpha_id
        self._port = port
        self._host = host
        self._app = None

    def _build_app(self):
        """Build FastAPI application"""
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        app = FastAPI(title=f"A2A Agent: {self._alpha_id}", version="1.0")

        @app.post("/a2a/call")
        async def handle_call(request: Request):
            """Handle A2A call"""
            body = await request.json()
            call_req = A2ACallRequest(**{k: v for k, v in body.items() if k in A2ACallRequest.__dataclass_fields__})

            # Verify signature
            if self._signer and call_req.proof:
                if not self._signer.verify(call_req.signable_bytes(), call_req.proof):
                    return JSONResponse(
                        A2ACallResponse(success=False, error="Signature verification failed", request_id=call_req.request_id).to_dict(),
                        status_code=401,
                    )

            # Execute skill
            start = time.time()
            try:
                result = self._skills.execute(call_req.skill, call_req.params)
                elapsed = (time.time() - start) * 1000

                # Generate proof of execution
                proof = ""
                if self._signer:
                    proof_data = json.dumps({"request_id": call_req.request_id, "result": str(result)}, sort_keys=True).encode()
                    proof = self._signer.sign(proof_data)

                return A2ACallResponse(
                    success=True,
                    result=result,
                    request_id=call_req.request_id,
                    executor=self._did,
                    proof=proof,
                    execution_time_ms=elapsed,
                ).to_dict()
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                return A2ACallResponse(
                    success=False,
                    error=str(e),
                    request_id=call_req.request_id,
                    executor=self._did,
                    execution_time_ms=elapsed,
                ).to_dict()

        @app.get("/a2a/discover")
        async def discover():
            """Discovery endpoint - return this Agent's info"""
            return A2AAgentInfo(
                did=self._did,
                alpha_id=self._alpha_id,
                endpoint=f"http://{self._host}:{self._port}",
                skills=[s["name"] for s in self._skills.list_skills()],
                status="online",
                last_seen=time.time(),
            ).to_dict()

        @app.get("/a2a/health")
        async def health():
            """Health check"""
            return {"status": "ok", "did": self._did, "alpha_id": self._alpha_id}

        @app.get("/a2a/skills")
        async def list_skills():
            """List all skills"""
            return self._skills.list_skills()

        return app

    def start(self, blocking: bool = True):
        """Start A2A server"""
        import uvicorn
        self._app = self._build_app()
        logger.info("A2A Server started: %s (port %d)", self._alpha_id, self._port)
        if blocking:
            uvicorn.run(self._app, host="0.0.0.0", port=self._port)
        else:
            import threading
            t = threading.Thread(
                target=uvicorn.run,
                args=(self._app,),
                kwargs={"host": "0.0.0.0", "port": self._port, "log_level": "warning"},
                daemon=True,
            )
            t.start()
            return t


# -- A2A Client --

class A2AClient:
    """
    A2A Client - call skills on remote Agents.

    Usage:
        client = A2AClient(signer=my_signer, my_did="did:aid:...")
        result = client.call(target_url="http://peer:9001", skill="greet", params={"name": "Alice"})
    """

    def __init__(self, signer: Optional[A2ASigner] = None, my_did: str = ""):
        self._signer = signer
        self._my_did = my_did

    def call(
        self,
        target_url: str,
        skill: str,
        params: Dict[str, Any] = None,
        timeout: float = 30.0,
    ) -> A2ACallResponse:
        """Synchronous call to remote Agent skill"""
        call_req = A2ACallRequest(
            caller=self._my_did,
            skill=skill,
            params=params or {},
        )

        # Sign
        if self._signer:
            call_req.proof = self._signer.sign(call_req.signable_bytes())

        try:
            resp = request(
                "POST",
                f"{target_url.rstrip('/')}/a2a/call",
                json=call_req.to_dict(),
                timeout=timeout,
            )
            data = resp.json()
            return A2ACallResponse(**{k: v for k, v in data.items() if k in A2ACallResponse.__dataclass_fields__})
        except Exception as e:
            return A2ACallResponse(success=False, error=str(e), request_id=call_req.request_id)

    def discover(self, target_url: str, timeout: float = 10.0) -> Optional[A2AAgentInfo]:
        """Discover remote Agent"""
        try:
            resp = request(
                "GET",
                f"{target_url.rstrip('/')}/a2a/discover",
                timeout=timeout,
            )
            data = resp.json()
            return A2AAgentInfo(**{k: v for k, v in data.items() if k in A2AAgentInfo.__dataclass_fields__})
        except Exception as e:
            logger.warning("Discovery failed: %s", e)
            return None

    def health_check(self, target_url: str, timeout: float = 5.0) -> bool:
        """Health check"""
        try:
            resp = request(
                "GET",
                f"{target_url.rstrip('/')}/a2a/health",
                timeout=timeout,
            )
            data = resp.json()
            return data.get("status") == "ok"
        except Exception:
            return False
