"""
AP2-compliant Intent Mandate model with cryptographic signature verification.

Supports ES256 (ECDSA with P-256/SHA-256) signature verification using
the `cryptography` library.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

import base64
import json


class AP2IntentMandate(BaseModel):
    """
    Standard 2026 AP2-compliant Intent Mandate.

    Represents a signed budget authorization that can be cryptographically
    verified before any resources are allocated.
    """
    mandate_id: str
    user_id: str
    max_budget: float = Field(..., description="Max USD for this task cycle")
    currency: str = "USD"
    resource_scope: list[str] = ["inference", "search", "vector_db"]
    expires_at: datetime
    signature: str  # Base64-encoded ES256 signature

    def is_expired(self) -> bool:
        """Check if this mandate has passed its expiry time."""
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now >= expires

    def get_signing_payload(self) -> bytes:
        """
        Returns the canonical byte payload that was signed.

        The payload is a deterministic JSON serialization of the mandate fields
        (excluding the signature itself).
        """
        payload = {
            "mandate_id": self.mandate_id,
            "user_id": self.user_id,
            "max_budget": self.max_budget,
            "currency": self.currency,
            "resource_scope": self.resource_scope,
            "expires_at": self.expires_at.isoformat(),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def verify_signature(self, public_key: ec.EllipticCurvePublicKey) -> bool:
        """
        Verify the ES256 signature against the mandate payload.

        Args:
            public_key: An EC P-256 public key used to verify the signature.

        Returns:
            True if the signature is valid, False otherwise.

        Raises:
            ValueError: If the signature is malformed (not valid base64).
        """
        try:
            signature_bytes = base64.b64decode(self.signature)
        except Exception as e:
            raise ValueError(f"Malformed signature: {e}")

        payload = self.get_signing_payload()

        try:
            public_key.verify(
                signature_bytes,
                payload,
                ec.ECDSA(hashes.SHA256()),
            )
            return True
        except InvalidSignature:
            return False


def sign_mandate(mandate: AP2IntentMandate, private_key: ec.EllipticCurvePrivateKey) -> str:
    """
    Sign an AP2IntentMandate with an ES256 private key.

    This is a utility for creating valid signed mandates (used in tests
    and by the Mintry monitoring plane).

    Args:
        mandate: The mandate to sign.
        private_key: An EC P-256 private key.

    Returns:
        Base64-encoded signature string.
    """
    payload = mandate.get_signing_payload()
    signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature).decode("utf-8")
