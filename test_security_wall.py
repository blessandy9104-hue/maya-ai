import json
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

import maya_security_wall as wall


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        old = {
            "ROOT": wall.ROOT,
            "POLICY_PATH": wall.POLICY_PATH,
            "AUDIT_PATH": wall.AUDIT_PATH,
            "STOP_PATH": wall.STOP_PATH,
        }
        try:
            wall.ROOT = temp_path
            wall.POLICY_PATH = temp_path / "policy.json"
            wall.AUDIT_PATH = temp_path / "audit.enc"
            wall.STOP_PATH = temp_path / "PRESENCE_STOP"
            wall.POLICY_PATH.write_text(json.dumps({
                "owner_control_enabled": False,
                "require_owner_token": True,
                "require_explicit_confirmation": True,
                "encryption_required_for_audit": True,
                "observation_separate": True,
                "emergency_stop_blocks_control": True,
                "allowlist": {},
            }), encoding="utf-8")
            os.environ["MAYA_VAULT_KEY"] = Fernet.generate_key().decode()
            os.environ["MAYA_OWNER_TOKEN"] = "owner-test-token"

            denied = wall.check_action("open_spotify", "owner-test-token", "CONFIRM")
            assert denied["allowed"] is False
            assert "owner control is disabled" in denied["reasons"]
            assert wall.append_encrypted_audit({"action": "denied"})["recorded"] is True

            policy = json.loads(wall.POLICY_PATH.read_text(encoding="utf-8"))
            policy["owner_control_enabled"] = True
            policy["allowlist"] = {"open_spotify": {"program": "spotify"}}
            wall.POLICY_PATH.write_text(json.dumps(policy), encoding="utf-8")

            allowed = wall.check_action("open_spotify", "owner-test-token", "CONFIRM")
            assert allowed["allowed"] is True
            missing_confirm = wall.check_action("open_spotify", "owner-test-token", "")
            assert missing_confirm["allowed"] is False
            wall.STOP_PATH.write_text("manual stop", encoding="utf-8")
            stopped = wall.check_action("open_spotify", "owner-test-token", "CONFIRM")
            assert stopped["allowed"] is False
            assert "emergency stop is active" in stopped["reasons"]
            print(json.dumps({"status": "ok", "default_denied": True, "encrypted_audit": True, "confirmation_required": True, "emergency_stop_blocks": True}))
        finally:
            for key, value in old.items():
                setattr(wall, key, value)
            os.environ.pop("MAYA_VAULT_KEY", None)
            os.environ.pop("MAYA_OWNER_TOKEN", None)


if __name__ == "__main__":
    main()
