import maya_chat


def main():
    result = maya_chat.maya_local_command(":emerging")
    assert result is not None
    assert "hypotheses only" in result
    assert "Nothing was saved" in result
    alias_result = maya_chat.maya_local_command("show emerging interests")
    assert alias_result == result
    print("router_safe_extensions_ok")


if __name__ == "__main__":
    main()
