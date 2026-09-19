from maya_chat import maya_local_command

for command in (":decision patterns", ":prediction limits"):
    output = maya_local_command(command)
    assert isinstance(output, str) and len(output) > 100, command
    print(command, "OK", len(output))

print("router_smoke_test=OK")
