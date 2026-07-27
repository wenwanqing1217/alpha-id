"""
AID — Agent Identity Decentralized Identifier (DID)

最小 DID 实现：did:aid 方法。纯 Python stdlib，零外部依赖。

Ed25519 实现基于 DJB's ref10 (public domain).
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

# ═══════════════════════════════════════════
# 纯 Python Ed25519 (ref10 / public domain)
# ═══════════════════════════════════════════

b = 256
q = 2**255 - 19
l = 2**252 + 27742317777372353535851937790883648493  # noqa: E741
d = -121665 * pow(121666, -1, q) % q
I = pow(2, (q - 1) // 4, q)  # noqa: E741


def _expmod(x, e, m):
    return pow(x, e, m)


def _inv(x):
    return pow(x, -1, q)


def _xrecover(y):
    yy = (y * y) % q
    xx = (yy - 1) * _inv((d * yy + 1) % q) % q
    x = _expmod(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


# ── 扩展坐标 (X, Y, Z, T) ──

Point = tuple[int, int, int, int]


def _to_extended(x, y) -> Point:
    """仿射坐标 → 扩展坐标"""
    return (x % q, y % q, 1, (x * y) % q)


def _to_affine(P: Point) -> tuple:  # noqa: N803
    """扩展坐标 → 仿射坐标"""
    x, y, z, _ = P
    zi = _inv(z)
    return ((x * zi) % q, (y * zi) % q)


def _isoncurve_ext(P: Point) -> bool:  # noqa: N803
    x, y, z, t = P
    lhs = (-x * x + y * y - z * z) % q
    rhs = (d * t * t) % q
    return lhs == rhs


def _edwards_add(P: Point, Q: Point) -> Point:  # noqa: N803
    x1, y1, z1, t1 = P
    x2, y2, z2, t2 = Q
    A = (y1 - x1) * (y2 - x2) % q  # noqa: N806
    B = (y1 + x1) * (y2 + x2) % q  # noqa: N806
    C = t1 * 2 * d * t2 % q  # noqa: N806
    D = z1 * 2 * z2 % q  # noqa: N806
    E = B - A  # noqa: N806
    F = D - C  # noqa: N806
    G = D + C  # noqa: N806
    H = B + A  # noqa: N806
    return (
        E * F % q,
        G * H % q,
        F * G % q,
        E * H % q,
    )


def _scalarmult(P: Point, e: int) -> Point:  # noqa: N803
    if e == 0:
        return (0, 1, 1, 0)
    Q = _scalarmult(P, e // 2)  # noqa: N806
    Q = _edwards_add(Q, Q)  # noqa: N806
    if e & 1:
        Q = _edwards_add(Q, P)  # noqa: N806
    return Q


def _encodepoint(P: Point) -> bytes:  # noqa: N803
    x, y = _to_affine(P)
    bits = [(y >> i) & 1 for i in range(b - 1)] + [x & 1]
    result = bytearray(b // 8)
    for i, bit in enumerate(bits):
        if bit:
            result[i // 8] |= bit << (i % 8)
    return bytes(result)


def _decodepoint(s: bytes) -> Point:
    if len(s) != 32:
        raise ValueError(f"Invalid point encoding length: {len(s)}")
    y = sum(2**i * ((s[i // 8] >> (i % 8)) & 1) for i in range(b - 1))
    x = _xrecover(y)
    if x & 1 != (s[-1] >> 7):
        x = q - x
    return _to_extended(x, y)


# ── 基点（RFC 8032）─ 从标准编码解码验证
# 编码: 5866666666666666666666666666666666666666666666666666666666666666
Bx = 15112221349535400772501151409588531511454012693041857206046113283949847762202
By = 46316835694926478169428394003475163141307993866256225615783033603165251855960
_B = _to_extended(Bx, By)


# ── 哈希标量 ──


def _hash_to_scalar(s: bytes) -> int:
    h = hashlib.sha512(s).digest()
    return int.from_bytes(h, "little") % l


# ── 公开 API ──


def generate_keypair() -> tuple[bytes, bytes]:
    """生成 (私钥seed, 公钥) 对"""
    seed = os.urandom(32)
    pk = public_key_from_secret(seed)
    return seed, pk


def _prune(scalar_bytes: bytes) -> int:
    """Ed25519 标量修剪：清零低3位，设位254"""
    a = int.from_bytes(scalar_bytes, "little")
    # 保留位 3-253，清零位 0-2 和 255，位 254 置 1
    a &= (1 << 255) - 8  # 清零 bit 0-2 和 bit 255
    a |= 1 << 254  # 设 bit 254
    return a


def public_key_from_secret(seed: bytes) -> bytes:
    """从私钥 seed 推导公钥"""
    h = hashlib.sha512(seed).digest()
    a = _prune(h[:32])
    return _encodepoint(_scalarmult(_B, a))


def sign(secret: bytes, msg: bytes) -> bytes:
    """Ed25519 签名，返回 64 字节"""
    h = hashlib.sha512(secret).digest()
    a = _prune(h[:32])
    prefix = h[32:]
    r = _hash_to_scalar(prefix + msg)
    R = _encodepoint(_scalarmult(_B, r))  # noqa: N806
    S = (r + _hash_to_scalar(R + public_key_from_secret(secret) + msg) * a) % l  # noqa: N806
    return R + S.to_bytes(32, "little")


def verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    """Ed25519 验签（含小阶子群攻击防护）"""
    # 长度校验：公钥 32 字节，签名 64 字节
    if len(public) != 32 or len(signature) != 64:
        return False

    # 拒绝全零公钥 — 解码后为 2 阶点（小阶子群），可导致伪造签名绕过
    if public == b"\x00" * 32:
        return False

    R_bytes = signature[:32]  # noqa: N806
    S_bytes = signature[32:]  # noqa: N806
    S = int.from_bytes(S_bytes, "little")  # noqa: N806
    if S >= l:
        return False

    try:
        R = _decodepoint(R_bytes)  # noqa: N806
        A = _decodepoint(public)  # noqa: N806
    except Exception:
        return False

    # 椭圆曲线成员检查：确保 R 和 A 确实在曲线上
    # _decodepoint 不验证曲线方程，无效编码会返回垃圾点，此处拦截
    if not _isoncurve_ext(R) or not _isoncurve_ext(A):
        return False

    # 小阶子群攻击防护：验证公钥不在 8 阶子群中
    # Curve25519 cofactor = 8；若 [8]A == 单位元，则 A 为小阶点
    if _scalarmult(A, 8) == (0, 1, 1, 0):
        return False

    h = _hash_to_scalar(R_bytes + public + msg)
    lhs = _scalarmult(_B, S)
    rhs = _edwards_add(R, _scalarmult(A, h))
    if not _isoncurve_ext(lhs) or not _isoncurve_ext(rhs):
        return False
    # 检查 lhs == rhs (扩展坐标下通过 X1*Z2 == X2*Z1 等判断)
    x1, y1, z1, _ = lhs
    x2, y2, z2, _ = rhs
    return (x1 * z2 - x2 * z1) % q == 0 and (y1 * z2 - y2 * z1) % q == 0


# ═══════════════════════════════════════════
# Base58
# ═══════════════════════════════════════════

ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    if n == 0:
        return "1"
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(ALPHABET[r])
    return "".join(chr(b) for b in reversed(result))


# ═══════════════════════════════════════════
# DID Core
# ═══════════════════════════════════════════


@dataclass
class DIDDocument:
    """最小 DID Document（W3C DID Core 兼容子集）"""

    id: str
    verification_method: list = field(default_factory=list)
    authentication: list = field(default_factory=list)
    service: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # 新增元数据字段

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "DIDDocument":
        data = json.loads(text)
        return cls(**data)


class DIDRegistry:
    """Agent DID 注册表 — 管理身份、签名、验证"""

    def __init__(self):
        self._private_key: Optional[bytes] = None
        self._public_key: Optional[bytes] = None
        self._did: Optional[str] = None

    # ── 身份生成 ──

    def generate(self, metadata=None) -> str:
        """生成新 DID + Ed25519 密钥对"""
        self._private_key, self._public_key = generate_keypair()
        did_hash = hashlib.sha256(self._public_key).digest()[:16]
        self._did = f"did:aid:{_b58encode(did_hash)}"
        if metadata:
            self._metadata = metadata
        return self._did

    def from_private_key_bytes(self, private_bytes: bytes) -> str:
        """从已有私钥恢复身份"""
        self._private_key = private_bytes
        self._public_key = public_key_from_secret(private_bytes)
        did_hash = hashlib.sha256(self._public_key).digest()[:16]
        self._did = f"did:aid:{_b58encode(did_hash)}"
        return self._did

    # ── 属性 ──

    @property
    def did(self) -> Optional[str]:
        return self._did

    @property
    def public_key(self) -> Optional[bytes]:
        return self._public_key

    # ── 序列化 ──

    def export_private_key(self) -> bytes:
        if self._private_key is None:
            raise ValueError("No private key loaded")
        return self._private_key

    def export_public_key(self) -> bytes:
        if self._public_key is None:
            raise ValueError("No public key loaded")
        return self._public_key

    def build_document(self) -> DIDDocument:
        if self._did is None or self._public_key is None:
            raise ValueError("Identity not initialized")
        pub_b58 = _b58encode(self._public_key)
        vm_id = f"{self._did}#key-1"
        return DIDDocument(
            id=self._did,
            verification_method=[
                {
                    "id": vm_id,
                    "type": "Ed25519VerificationKey2018",
                    "controller": self._did,
                    "publicKeyMultibase": "z" + pub_b58,
                }
            ],
            authentication=[vm_id],
            metadata=getattr(self, "_metadata", {}),  # 嵌入元数据
        )

    # ── 签名 & 验证 ──

    def sign(self, payload: bytes) -> bytes:
        if self._private_key is None:
            raise ValueError("No private key loaded")
        return sign(self._private_key, payload)

    @staticmethod
    def verify(public_key_bytes: bytes, payload: bytes, signature: bytes) -> bool:
        return verify(public_key_bytes, payload, signature)

    @staticmethod
    def did_matches_key(did: str, public_key_bytes: bytes) -> bool:
        if not did.startswith("did:aid:"):
            return False
        expected_hash = _b58encode(hashlib.sha256(public_key_bytes).digest()[:16])
        return did == f"did:aid:{expected_hash}"
