"""
AID Core - Minimal DID (did:aid method)

Core data structures only. Cryptographic operations are in alpha_id.crypto.
"""

import logging

from alpha_id.crypto import CoreDID, DIDDocument, _b58encode

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = ["CoreDID", "DIDDocument", "_b58encode"]
