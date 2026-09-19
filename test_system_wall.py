import json

from maya_system_wall import system_contract, validate_launch


def main():
    contract = system_contract()
    assert contract["mode"] == "cooperative_non_interference"
    safe = validate_launch("open_text_editor", "C:/Apps/editor.exe", [])
    assert safe["allowed"] is True

    for action, executable, args in [
        ("shutdown_system", "C:/Windows/System32/shutdown.exe", []),
        ("terminate_process", "C:/Windows/System32/taskkill.exe", ["/PID", "123"]),
        ("open_anything", "C:/Windows/System32/cmd.exe", ["/c", "del /f file"]),
        ("open_anything", "C:/Apps/editor.exe", ["&&", "rm -rf /"]),
        ("elevate_privileges", "C:/Windows/System32/runas.exe", []),
    ]:
        denied = validate_launch(action, executable, args)
        assert denied["allowed"] is False
        assert denied["reasons"]

    print(json.dumps({"status": "ok", "safe_cooperation_allowed": True, "destructive_actions_blocked": True, "privilege_escalation_blocked": True, "shell_syntax_blocked": True}))


if __name__ == "__main__":
    main()
