"""
Cryptographic operations for Alpha-ID.

This module contains all cryptography-dependent code, keeping core/ free
from external dependencies.
"""

import hashlib
import logging
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

logger = logging.getLogger(__name__)


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    if n == 0:
        return B58[0]
    chars = []
    while n > 0:
        n, r = divmod(n, 58)
        chars.append(B58[r])
    return "".join(reversed(chars))


class CoreDID:
    """Core DID: key management + document building + sign/verify"""

    def __init__(self):
        self._private_key: Optional[Ed25519PrivateKey] = None
        self._did: Optional[str] = None

    @classmethod
    def generate(cls) -> "CoreDID":
        self = cls()
        self._private_key = Ed25519PrivateKey.generate()
        pub_bytes = self._private_key.public_key().public_bytes_raw()
        did_hash = hashlib.sha256(pub_bytes).digest()[:16]
        self._did = "did:aid:" + _b58encode(did_hash)
        logger.info("Generated new DID: %s", self._did)
        return self

    @property
    def did(self) -> Optional[str]:
        return self._did

    @property
    def public_key(self) -> Optional[bytes]:
        if self._private_key is None:
            return None
        return self._private_key.public_key().public_bytes_raw()

    def build_document(self) -> "DIDDocument":
        """Build W3C DID Core compatible document"""
        if self._did is None or self._private_key is None:
            raise ValueError("DID not initialized")
        pub_bytes = self._private_key.public_key().public_bytes_raw()
        vm_id = self._did + "#key-1"
        logger.info("Building DID document for %s", self._did)
        return DIDDocument(
            id=self._did,
            verification_method=[
                {
                    "id": vm_id,
                    "type": "Ed25519VerificationKey2018",
                    "controller": self._did,
                    "publicKeyMultibase": "z" + _b58encode(pub_bytes),
                }
            ],
            authentication=[vm_id],
        )

    def sign(self, payload: bytes) -> bytes:
        if self._private_key is None:
            raise ValueError("DID not initialized")
        logger.debug("Signing payload (%d bytes) with DID %s", len(payload), self._did)
        return self._private_key.sign(payload)

    @staticmethod
    def verify(public_key_bytes: bytes, payload: bytes, signature: bytes) -> bool:
        try:
            pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            pub.verify(signature, payload)
            logger.debug("Signature verified successfully (%d bytes payload)", len(payload))
            return True
        except Exception as e:
            logger.debug("Signature verification failed: %s", e)
            return False

    @staticmethod
    def did_matches_key(did: str, public_key_bytes: bytes) -> bool:
        if not did.startswith("did:aid:"):
            return False
        expected_hash = _b58encode(hashlib.sha256(public_key_bytes).digest()[:16])
        return did == "did:aid:" + expected_hash


class DIDDocument:
    """W3C DID Core compatible document"""

    def __init__(self, id: str, verification_method: list, authentication: list, service: list = None):
        self.id = id
        self.verification_method = verification_method
        self.authentication = authentication
        self.service = service or []

    def to_json(self) -> str:
        import json

        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "DIDDocument":
        import json

        data = json.loads(text)
        return cls(**data)
