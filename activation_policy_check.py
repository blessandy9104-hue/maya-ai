import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
policy_path = ROOT / "evolution" / "activation_policy.json"
policy = json.loads(policy_path.read_text())

print(f"mode: {policy.get('mode')}")
print(f"enabled: {policy.get('enabled')}")
print(f"auto_activation_allowed: {policy.get('auto_activation', {}).get('allowed')}")
print(f"max_retry_attempts: {policy.get('max_retry_attempts')}")

required = [
    policy.get("default_requires_approval") is True,
    policy.get("rollback_required") is True,
    policy.get("auto_activation", {}).get("requires_all_tests") is True,
    policy.get("auto_activation", {}).get("requires_backup") is True,
    policy.get("auto_activation", {}).get("requires_rollback_plan") is True,
    policy.get("auto_activation", {}).get("requires_audit_log") is True,
]

if not all(required):
    print("POLICY CHECK: FAIL")
    raise SystemExit(1)

if policy.get("mode") == "approval_only" and policy.get("enabled") is False:
    print("POLICY CHECK: PASS — approval-only mode is active")
else:
    print("POLICY CHECK: REVIEW REQUIRED — automatic mode is configured")
