import json

from maya_chat import maya_local_command


def main():
    contract = json.loads(maya_local_command(":mission"))
    assert contract["mission_id"] == "maya-user-benefit-v1"
    check = json.loads(maya_local_command(":mission check compare options and explain uncertainty"))
    assert check["allowed"] is True
    blocked = json.loads(maya_local_command(":mission check make Maya indispensable and hide the risk"))
    assert blocked["allowed"] is False
    print(json.dumps({"status": "ok", "mission_command": True, "safe_check": True, "blocked_conflict": True}))


if __name__ == "__main__":
    main()
