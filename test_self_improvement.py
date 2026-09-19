import json
from maya_chat import maya_local_command

status = json.loads(maya_local_command(":learning status"))
assert status["source_code_self_rewrite"] is False
assert status["automatic_activation"] is False
assert status["memory_update"] == "not_performed"
proposals = json.loads(maya_local_command(":learning proposals"))
assert "proposals" in proposals
print("self_improvement_status=OK")
print("self_improvement_proposals=OK")
