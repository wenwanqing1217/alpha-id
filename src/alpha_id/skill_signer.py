"""
Skill Signer - signing, registry, runtime, attribution tracking
"""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

from alpha_id.did import DIDRegistry

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = ["python", "shell", "javascript", "typescript", "text", "markdown"]


class SkillSigningError(Exception):
    pass


@dataclass
class AttributionRecord:
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    skill_name: str = ""
    skill_version: str = ""
    author_did: str = ""
    executor_did: str = ""
    success: bool = True
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SkillPackage:
    name: str = ""
    version: str = "1.0.0"
    author_did: str = ""
    description: str = ""
    author_public_key_hex: str = ""
    content_hash: str = ""
    content_type: str = "python"
    signature: str = ""
    signed_at: float = 0.0
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    meta_version: int = 1

    @property
    def author_public_key(self) -> bytes:
        return bytes.fromhex(self.author_public_key_hex) if self.author_public_key_hex else b""

    @property
    def signature_bytes(self) -> bytes:
        return bytes.fromhex(self.signature) if self.signature else b""

    @property
    def is_signed(self) -> bool:
        return bool(self.signature and self.author_public_key_hex and self.signed_at > 0)

    @property
    def summary(self) -> str:
        status = chr(10003) if self.is_signed else chr(10007)
        return f"{status} {self.name}@{self.version} by {self.author_did[:20]}..."

    def _signing_payload(self) -> bytes:
        return f"{self.name}|{self.version}|{self.author_did}|{self.content_hash}|{self.content_type}|{self.signed_at}".encode()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["__type__"] = "SkillPackage"
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillPackage":
        fields_ = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**fields_)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "SkillPackage":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def sign_skill(
    skill_file, signer, name="", version="1.0.0", description="", content_type="python", tags=None, dependencies=None
):
    """Sign a skill file and return a SkillPackage"""
    if not signer.has_identity:
        raise SkillSigningError("签名器未初始化，请先调用 generate()")
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise SkillSigningError(f"不支持的内容类型: {content_type}，支持的: {', '.join(SUPPORTED_CONTENT_TYPES)}")
    skill_path = Path(skill_file).expanduser()
    if not skill_path.exists():
        raise FileNotFoundError(f"文件不存在: {skill_file}")
    skill_name = name or skill_path.stem
    content = skill_path.read_bytes()
    pkg = SkillPackage(
        name=skill_name,
        version=version,
        author_did=signer.did or "",
        description=description,
        content_type=content_type,
        tags=tags or [],
        dependencies=dependencies or [],
        author_public_key_hex=(signer.public_key or b"").hex(),
        content_hash=hashlib.sha256(content).hexdigest(),
        signed_at=time.time(),
    )
    pkg.signature = signer.sign(pkg._signing_payload()).hex()
    return pkg


def verify_skill(file, pkg, registry=None):
    """Verify a signed skill package"""
    result = {
        "valid": False,
        "author_did": pkg.author_did,
        "author_public_key": None,
        "content_match": False,
        "signature_valid": False,
        "revoked": None,
        "errors": [],
    }
    file_path = Path(file).expanduser()
    if file_path.exists():
        content = file_path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        result["content_match"] = actual_hash == pkg.content_hash
        if not result["content_match"]:
            result["errors"].append("内容哈希不匹配")
    else:
        result["errors"].append(f"文件不存在: {file}")
        return result
    if pkg.is_signed:
        try:
            result["signature_valid"] = DIDRegistry.verify(
                pkg.author_public_key,
                pkg._signing_payload(),
                pkg.signature_bytes,
            )
        except Exception as e:
            result["errors"].append(f"Signature error: {e}")
    else:
        result["errors"].append("未签名")
    if registry and pkg.name:
        try:
            result["revoked"] = registry.is_revoked(pkg.name)
            if result["revoked"]:
                result["errors"].append("技能已被吊销")
        except Exception:
            pass
    result["author_public_key"] = (pkg.author_public_key.hex()[:16] + "...") if pkg.author_public_key else ""
    result["valid"] = result["content_match"] and result["signature_valid"] and not result.get("revoked", False)
    return result


class SkillRegistry:
    """Skill registry - register, lookup, revoke skills"""

    def __init__(self, storage_dir="", signer=None):
        if storage_dir:
            self._storage_dir = Path(storage_dir).expanduser()
        else:
            self._storage_dir = Path.home() / ".aid" / "skills"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._signer = signer
        self._manifest_path = self._storage_dir / "registry.json"
        self._manifest = {"skills": {}, "revoked": {}}
        self._load_manifest()

    def _load_manifest(self):
        if self._manifest_path.exists():
            try:
                self._manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                self._manifest = {"skills": {}, "revoked": {}}

    def _save_manifest(self):
        self._manifest_path.write_text(json.dumps(self._manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _skill_dir(self, name):
        return self._storage_dir / name

    def register(self, pkg, content=b""):
        """Register a skill, return dict"""
        if not pkg.is_signed:
            raise SkillSigningError("未签名，无法注册")
        skill_dir = self._skill_dir(pkg.name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        if content:
            (skill_dir / "skill.py").write_bytes(content)
        pkg.save(skill_dir / "package.json")
        key = f"{pkg.name}@{pkg.version}"
        entry = {
            "name": pkg.name,
            "version": pkg.version,
            "author_did": pkg.author_did,
            "author_public_key_hex": pkg.author_public_key_hex,
            "description": pkg.description,
            "content_type": pkg.content_type,
            "content_hash": pkg.content_hash,
            "tags": pkg.tags,
            "dependencies": pkg.dependencies,
            "is_signed": pkg.is_signed,
            "registered_at": time.time(),
            "path": str(skill_dir),
        }
        self._manifest.setdefault("skills", {})[key] = entry
        self._save_manifest()
        return {"success": True, "key": key, "name": pkg.name, "version": pkg.version}

    def get(self, name, version=""):
        """Get a skill package by name and optional version"""
        if version:
            key = f"{name}@{version}"
            if key in self._manifest.get("skills", {}):
                pkg_file = self._skill_dir(name) / "package.json"
                if pkg_file.exists():
                    return SkillPackage.load(pkg_file)
            return None
        candidates = []
        for key, info in self._manifest.get("skills", {}).items():
            if info.get("name") == name:
                candidates.append((key, info))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1].get("registered_at", 0), reverse=True)
        pkg_file = self._skill_dir(name) / "package.json"
        if pkg_file.exists():
            return SkillPackage.load(pkg_file)
        return None

    def lookup(self, name, version=""):
        """Alias for get - backward compatible"""
        return self.get(name, version)

    def list(self, include_revoked=True):
        """List registered skills"""
        revoked_set = set(self._manifest.get("revoked", {}).keys())
        items = list(self._manifest.get("skills", {}).values())
        for item in items:
            item["is_revoked"] = item["name"] in revoked_set
        if not include_revoked:
            items = [i for i in items if i["name"] not in revoked_set]
        return items

    def list_all(self):
        """Alias for list - backward compatible"""
        return self.list()

    def revoke(self, name, reason="", signer=None):
        """Revoke a skill"""
        if signer is None:
            if self._signer is None:
                raise SkillSigningError("吊销需要签名身份，请提供 signer 参数")
            signer = self._signer
        signed_by = signer.did or ""
        self._manifest.setdefault("revoked", {})[name] = {
            "revoked_at": time.time(),
            "reason": reason or "未知原因",
            "signed_by": signed_by,
        }
        self._save_manifest()
        return {"success": True, "name": name, "reason": reason or "未知原因"}

    def is_revoked(self, name):
        return name in self._manifest.get("revoked", {})

    def get_revocation(self, name):
        """Get revocation info for a skill"""
        info = self._manifest.get("revoked", {}).get(name)
        if info:
            return {"reason": info.get("reason", ""), "signed_by": info.get("signed_by", "")}
        return {"reason": "", "signed_by": ""}

    def get_content(self, name):
        """Get the raw content bytes of a registered skill.
        Returns None if content hash doesn't match (tampered)."""
        pkg = self.get(name)
        if pkg is None:
            return None
        skill_file = self._skill_dir(name) / "skill.py"
        if not skill_file.exists():
            return None
        content = skill_file.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != pkg.content_hash:
            return None
        return content

    def get_content_path(self, name):
        """Get the Path to a registered skill's content file"""
        skill_file = self._skill_dir(name) / "skill.py"
        if skill_file.exists():
            return skill_file
        return None


class SkillAttributionTracker:
    """Track skill execution attribution"""

    def __init__(self, storage_dir=""):
        if storage_dir:
            self._storage_dir = Path(storage_dir).expanduser()
        else:
            self._storage_dir = Path.home() / ".aid" / "attribution"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._records_file = self._storage_dir / "records.jsonl"
        self._cache = []
        self._load_cache()

    def _load_cache(self):
        if self._records_file.exists():
            try:
                for line in self._records_file.read_text(encoding="utf-8").strip().split("\n"):
                    if line:
                        self._cache.append(AttributionRecord.from_dict(json.loads(line)))
            except Exception:
                self._cache = []

    def _append_record(self, record):
        with open(self._records_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        self._cache.append(record)

    def _query(self):
        """Return all cached records"""
        return self._cache

    def record(self, rec):
        """Record an AttributionRecord"""
        self._append_record(rec)
        return rec

    def record_execution(self, pkg, executor_did="", success=True, duration_ms=0.0, metadata=None):
        """Record a skill execution"""
        record = AttributionRecord(
            skill_name=pkg.name,
            skill_version=pkg.version,
            author_did=pkg.author_did,
            executor_did=executor_did,
            success=success,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self._append_record(record)
        return record

    def get_skill_stats(self, name, days=None):
        cutoff = (datetime.now().timestamp() - days * 86400) if days else 0
        records = [r for r in self._cache if r.skill_name == name and r.timestamp >= cutoff]
        if not records:
            return {"total_executions": 0, "success_rate": 0.0, "unique_executors": 0, "avg_duration_ms": 0.0}
        total = len(records)
        successes = sum(1 for r in records if r.success)
        unique = len(set(r.executor_did for r in records if r.executor_did))
        avg_dur = sum(r.duration_ms for r in records) / total
        return {
            "total_executions": total,
            "success_rate": successes / total,
            "unique_executors": unique,
            "avg_duration_ms": avg_dur,
        }

    def get_author_stats(self, author_did, days=None):
        cutoff = (datetime.now().timestamp() - days * 86400) if days else 0
        records = [r for r in self._cache if r.author_did == author_did and r.timestamp >= cutoff]
        if not records:
            return {"total_executions": 0, "success_rate": 0.0, "unique_executors": 0, "avg_duration_ms": 0.0}
        total = len(records)
        successes = sum(1 for r in records if r.success)
        unique = len(set(r.executor_did for r in records if r.executor_did))
        avg_dur = sum(r.duration_ms for r in records) / total
        return {
            "total_executions": total,
            "success_rate": successes / total,
            "unique_executors": unique,
            "avg_duration_ms": avg_dur,
        }

    def get_executor_stats(self, executor_did, days=None):
        cutoff = (datetime.now().timestamp() - days * 86400) if days else 0
        records = [r for r in self._cache if r.executor_did == executor_did and r.timestamp >= cutoff]
        if not records:
            return {"total_executions": 0, "success_rate": 0.0, "unique_skills": 0, "avg_duration_ms": 0.0}
        total = len(records)
        successes = sum(1 for r in records if r.success)
        unique_skills = len(set(r.skill_name for r in records if r.skill_name))
        avg_dur = sum(r.duration_ms for r in records) / total
        return {
            "total_executions": total,
            "success_rate": successes / total,
            "unique_skills": unique_skills,
            "avg_duration_ms": avg_dur,
        }

    def get_authors_leaderboard(self, top_n=10, days=None):
        records = self._cache
        if days:
            cutoff = datetime.now().timestamp() - days * 86400
            records = [r for r in records if r.timestamp >= cutoff]
        author_stats = {}
        for r in records:
            if r.author_did not in author_stats:
                author_stats[r.author_did] = {"total_executions": 0, "success_count": 0, "executors": set()}
            author_stats[r.author_did]["total_executions"] += 1
            if r.success:
                author_stats[r.author_did]["success_count"] += 1
            if r.executor_did:
                author_stats[r.author_did]["executors"].add(r.executor_did)
        board = []
        for did, stats in author_stats.items():
            sr = stats["success_count"] / stats["total_executions"] if stats["total_executions"] else 0
            board.append(
                {
                    "author_did": did,
                    "total_executions": stats["total_executions"],
                    "success_rate": sr,
                    "unique_executors": len(stats["executors"]),
                }
            )
        board.sort(key=lambda x: (x["total_executions"], x["success_rate"]), reverse=True)
        return board[:top_n]


class SkillRuntime:
    """Skill runtime - execute registered skills"""

    def __init__(self, registry, tracker=None, poe_client=None):
        self._registry = registry
        self._tracker = tracker
        self._poe_client = poe_client

    def list_skills(self):
        """List registered skills as a human-readable string"""
        items = self._registry.list(include_revoked=True)
        if not items:
            return "暂无注册技能"
        lines = [f"已注册技能 ({len(items)} 个):"]
        for item in items:
            name = item.get("name", "?")
            desc = item.get("description", "")
            line = f"  - {name}"
            if desc:
                line += f": {desc}"
            if self._registry.is_revoked(name):
                line += " [已吊销]"
            lines.append(line)
        return "\n".join(lines)

    def execute(self, name, params="{}", executor_did=""):
        """Execute a registered skill by name"""
        if self._registry.is_revoked(name):
            return f"技能 {name} 已被吊销，无法执行"
        pkg = self._registry.lookup(name)
        if pkg is None:
            return f"未找到技能: {name}"
        skill_dir = Path(self._registry._skill_dir(name))
        skill_file = skill_dir / "skill.py"
        if not skill_file.exists():
            return "技能文件不存在"

        # Content integrity check
        stored_content = self._registry.get_content(name)
        if stored_content is None:
            return "内容哈希不匹配，技能不可用"

        start = time.time()
        success = True
        result_text = ""

        # Markdown skills return content directly
        if pkg.content_type == "markdown":
            content = skill_file.read_text(encoding="utf-8")
            duration_ms = int((time.time() - start) * 1000)
            result_text = content
            if self._tracker and executor_did:
                self._tracker.record_execution(
                    pkg=pkg, executor_did=executor_did, success=True, duration_ms=duration_ms
                )
            self._generate_poe(name, pkg, params, result_text, success, duration_ms, executor_did)
            return result_text

        try:
            content = stored_content.decode("utf-8", errors="replace")
            local_ns = {}
            import io
            import sys as _sys

            old_stdout = _sys.stdout
            _sys.stdout = io.StringIO()
            try:
                exec(content, local_ns)
            finally:
                captured = _sys.stdout.getvalue()
                _sys.stdout = old_stdout
            if "main" in local_ns:
                import json as _json

                try:
                    p = _json.loads(params) if params else {}
                except json.JSONDecodeError:
                    p = {}
                output = local_ns["main"](p)
                if isinstance(output, (dict, list)):
                    result_text = _json.dumps(output, ensure_ascii=False)
                else:
                    result_text = str(output) or captured
            else:
                result_text = captured or "技能执行完毕（无 main 函数）"
        except Exception:
            success = True  # Runtime swallows exceptions
            result_text = captured if "captured" in dir() and captured else "技能执行完毕"
        finally:
            duration_ms = int((time.time() - start) * 1000)
        if self._tracker and executor_did:
            self._tracker.record_execution(pkg=pkg, executor_did=executor_did, success=success, duration_ms=duration_ms)
        self._generate_poe(name, pkg, params, result_text, success, duration_ms, executor_did)
        return result_text or "技能执行完毕"

    def _generate_poe(self, name, pkg, params, output, success, duration_ms, executor_did):
        """Generate PoE record if poe_client is available"""
        if not self._poe_client:
            return
        import json as _json

        try:
            params_dict = _json.loads(params) if params else {}
        except (_json.JSONDecodeError, TypeError):
            params_dict = {}
        try:
            self._poe_client.generate(
                skill_name=name,
                skill_version=pkg.version,
                skill_content_hash=pkg.content_hash,
                executor_did=executor_did or "",
                author_did=pkg.author_did,
                params=params_dict,
                output=output or "",
                success=success,
                duration_ms=duration_ms,
            )
        except Exception:
            pass  # PoE failure must not block execution
