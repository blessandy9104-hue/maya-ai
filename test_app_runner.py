import json
import os
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

import maya_app_runner as runner
import maya_security_wall as wall


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        old_runner_policy = runner.POLICY_PATH
        old_security = {"POLICY_PATH": wall.POLICY_PATH, "AUDIT_PATH": wall.AUDIT_PATH, "STOP_PATH": wall.STOP_PATH}
        try:
            runner.POLICY_PATH = root / "app_policy.json"
            wall.POLICY_PATH = root / "security_policy.json"
            wall.AUDIT_PATH = root / "audit.enc"
            wall.STOP_PATH = root / "PRESENCE_STOP"
            os.environ["MAYA_VAULT_KEY"] = Fernet.generate_key().decode()
            os.environ["MAYA_OWNER_TOKEN"] = "owner-token"
            wall.POLICY_PATH.write_text(json.dumps({
                "owner_control_enabled": True,
                "require_owner_token": True,
                "require_explicit_confirmation": True,
                "encryption_required_for_audit": True,
                "observation_separate": True,
                "emergency_stop_blocks_control": True,
                "allowlist": {"safe_test": {"program": "python"}},
            }), encoding="utf-8")
            runner.POLICY_PATH.write_text(json.dumps({
                "owner_control_enabled": False,
                "actions": {},
                "max_launches_per_request": 1,
                "launch_timeout_seconds": 5,
            }), encoding="utf-8")
            disabled = runner.run_allowed("safe_test", "owner-token", "CONFIRM", dry_run=True)
            assert disabled["allowed"] is False

            policy = json.loads(runner.POLICY_PATH.read_text(encoding="utf-8"))
            policy["owner_control_enabled"] = True
            policy["actions"] = {"safe_test": {"executable": sys.executable, "args": ["-V"]}}
            runner.POLICY_PATH.write_text(json.dumps(policy), encoding="utf-8")

            missing = runner.run_allowed("safe_test", "owner-token", "", dry_run=True)
            assert missing["allowed"] is False
            allowed = runner.run_allowed("safe_test", "owner-token", "CONFIRM", dry_run=True)
            assert allowed["allowed"] is True and allowed["dry_run"] is True

            wall.STOP_PATH.write_text("manual stop", encoding="utf-8")
            stopped = runner.run_allowed("safe_test", "owner-token", "CONFIRM", dry_run=True)
            assert stopped["allowed"] is False

            policy["actions"]["unsafe_shell"] = {"executable": sys.executable, "args": ["-c", "print('bad') && echo bad"]}
            runner.POLICY_PATH.write_text(json.dumps(policy), encoding="utf-8")
            wall.STOP_PATH.unlink()
            unsafe = runner.run_allowed("unsafe_shell", "owner-token", "CONFIRM", dry_run=True)
            assert unsafe["allowed"] is False
            print(json.dumps({"status": "ok", "default_denied": True, "confirmation_required": True, "allowlist_enforced": True, "shell_syntax_rejected": True, "emergency_stop_blocks": True}))
        finally:
            runner.POLICY_PATH = old_runner_policy
            for key, value in old_security.items():
                setattr(wall, key, value)
            os.environ.pop("MAYA_VAULT_KEY", None)
            os.environ.pop("MAYA_OWNER_TOKEN", None)


if __name__ == "__main__":
    main()
