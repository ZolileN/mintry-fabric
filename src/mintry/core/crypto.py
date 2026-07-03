"""ES256 (ECDSA with SHA-256) signature verification for policy bundles.

Never called from the enforcement hot path.
Used only during async policy sync to verify control-plane signed bundles.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import cast
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)


def verify_policy_bundle_signature(
    bundle_dict: dict,
    public_key_pem: str | bytes,
) -> bool:
    """Verify ES256 signature on a policy bundle from the control plane.

    Args:
        bundle_dict: The policy bundle payload (must include 'signature' field)
        public_key_pem: ECDSA P-256 public key in PEM format

    Returns:
        True if signature is valid, False otherwise.
    """
    if not bundle_dict.get("signature"):
        logger.warning("Policy bundle has no signature")
        return False

    try:
        # Load the public key
        if isinstance(public_key_pem, str):
            public_key_pem = public_key_pem.encode("utf-8")

        public_key = cast(
            ec.EllipticCurvePublicKey,
            serialization.load_pem_public_key(public_key_pem)
        )

        # Reconstruct the signing payload (bundle without signature)
        signing_payload = {k: v for k, v in bundle_dict.items() if k != "signature"}
        message = json.dumps(signing_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        # Decode the signature from base64
        signature_bytes = base64.b64decode(bundle_dict["signature"])

        # Verify using ES256 (ECDSA with SHA-256)
        public_key.verify(signature_bytes, message, ec.ECDSA(hashes.SHA256()))

        logger.info("Policy bundle signature verified (v%s)", bundle_dict.get("version"))
        return True

    except InvalidSignature:
        logger.warning("Invalid policy bundle signature for v%s", bundle_dict.get("version"))
        return False
    except Exception as exc:
        logger.error("Signature verification failed: %s", exc)
        return False


def sign_policy_bundle(
    bundle_dict: dict,
    private_key_pem: str | bytes,
) -> str:
    """Sign a policy bundle with ES256 (for testing/control-plane only).

    Args:
        bundle_dict: The policy bundle payload (will have signature added)
        private_key_pem: ECDSA P-256 private key in PEM format

    Returns:
        Base64-encoded signature string.
    """
    try:
        if isinstance(private_key_pem, str):
            private_key_pem = private_key_pem.encode("utf-8")

        private_key = cast(
            ec.EllipticCurvePrivateKey,
            serialization.load_pem_private_key(private_key_pem, password=None)
        )

        # Sign the bundle (excluding signature field)
        signing_payload = {k: v for k, v in bundle_dict.items() if k != "signature"}
        message = json.dumps(signing_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        signature_bytes = private_key.sign(message, ec.ECDSA(hashes.SHA256()))

        logger.info("Policy bundle signed (v%s)", bundle_dict.get("version"))
        return base64.b64encode(signature_bytes).decode("utf-8")

    except Exception as exc:
        logger.error("Failed to sign policy bundle: %s", exc)
        raise


def generate_policy_keypair() -> tuple[str, str]:
    """Generate a new ECDSA P-256 keypair for testing.

    Returns:
        Tuple of (private_key_pem, public_key_pem) as strings.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem
