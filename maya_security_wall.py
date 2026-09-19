"""Maya security wall for future owner-approved local controls.

The wall is deny-by-default. It does not execute commands itself. Callers must
provide an owner token, explicit confirmation, an allowlisted action, and a
non-active emergency stop. Encryption keys are supplied out-of-band through
MAYA_VAULT_KEY and are never written beside Maya's data.

This wall governs owner/desktop-control actions only. Web/network host access
is a separate gate owned by evolution/network_policy.json (see ARCHITECTURE.md,
"Policy ownership"). owner_control_enabled=false + require_owner_token=true is
intentional: the token stays armed so enabling owner control always fails
closed until a token is configured.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).parent
POLICY_PATH = ROOT / "maya_security_policy.json"
AUDIT_PATH = ROOT / "maya_control_audit.enc"
STOP_PATH = ROOT / "PRESENCE_STOP"

DEFAULT_POLICY = {
    "owner_control_enabled": False,
    "require_owner_token": True,
    "require_explicit_confirmation": True,
    "encryption_required_for_audit": True,
    "observation_separate": True,
    "emergency_stop_blocks_control": True,
    "allowlist": {},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        POLICY_PATH.write_text(json.dumps(DEFAULT_POLICY, indent=2) + "\n", encoding="utf-8")
        return dict(DEFAULT_POLICY)
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy = dict(DEFAULT_POLICY)
        policy.update(data if isinstance(data, dict) else {})
        return policy
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT_POLICY)


def _fernet() -> Fernet | None:
    raw = os.environ.get("MAYA_VAULT_KEY", "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode("ascii"))
    except Exception:
        return None


def generate_vault_key() -> str:
    """Generate a key for the owner to store outside Maya's project folder."""
    return Fernet.generate_key().decode("ascii")


def encrypt_text(text: str) -> bytes:
    cipher = _fernet()
    if cipher is None:
        raise RuntimeError("MAYA_VAULT_KEY is not configured or is invalid")
    return cipher.encrypt(text.encode("utf-8"))


def decrypt_text(blob: bytes) -> str:
    cipher = _fernet()
    if cipher is None:
        raise RuntimeError("MAYA_VAULT_KEY is not configured or is invalid")
    try:
        return cipher.decrypt(blob).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Encrypted Maya data failed integrity verification") from exc


def _expected_owner_digest() -> str:
    configured = os.environ.get("MAYA_OWNER_TOKEN", "")
    return hashlib.sha256(configured.encode("utf-8")).hexdigest() if configured else ""


def owner_token_valid(token: str) -> bool:
    expected = _expected_owner_digest()
    supplied = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    return bool(expected) and hmac.compare_digest(expected, supplied)


def emergency_stop_active() -> bool:
    return STOP_PATH.exists()


def check_action(action: str, token: str = "", confirmation: str = "") -> dict[str, Any]:
    policy = load_policy()
    reasons: list[str] = []
    if policy.get("owner_control_enabled") is not True:
        reasons.append("owner control is disabled")
    if policy.get("require_owner_token", True) and not owner_token_valid(token):
        reasons.append("owner authentication failed")
    if policy.get("require_explicit_confirmation", True) and confirmation.strip().upper() != "CONFIRM":
        reasons.append("explicit confirmation missing")
    if policy.get("emergency_stop_blocks_control", True) and emergency_stop_active():
        reasons.append("emergency stop is active")
    allowlist = policy.get("allowlist", {})
    if not isinstance(allowlist, dict) or action not in allowlist:
        reasons.append("action is not allowlisted")
    return {"allowed": not reasons, "action": action, "reasons": reasons, "checked_at": utc_now()}


def append_encrypted_audit(event: dict[str, Any]) -> dict[str, Any]:
    policy = load_policy()
    if policy.get("encryption_required_for_audit", True) and _fernet() is None:
        return {"recorded": False, "reason": "MAYA_VAULT_KEY is required before audit data can be written"}
    existing: list[dict[str, Any]] = []
    if AUDIT_PATH.exists():
        try:
            existing = json.loads(decrypt_text(AUDIT_PATH.read_bytes()))
            if not isinstance(existing, list):
                existing = []
        except (OSError, RuntimeError, ValueError, TypeError):
            return {"recorded": False, "reason": "encrypted audit failed integrity verification"}
    existing.append(dict(event, recorded_at=utc_now()))
    AUDIT_PATH.write_bytes(encrypt_text(json.dumps(existing, ensure_ascii=False)))
    return {"recorded": True, "count": len(existing)}


def security_status() -> dict[str, Any]:
    policy = load_policy()
    return {
        "owner_control_enabled": policy.get("owner_control_enabled") is True,
        "owner_token_configured": bool(os.environ.get("MAYA_OWNER_TOKEN")),
        "vault_key_configured": _fernet() is not None,
        "encrypted_audit_exists": AUDIT_PATH.exists(),
        "emergency_stop_active": emergency_stop_active(),
        "observation_separate": policy.get("observation_separate") is True,
        "allowlisted_actions": sorted((policy.get("allowlist") or {}).keys()),
    }


if __name__ == "__main__":
    print(json.dumps(security_status(), indent=2))
